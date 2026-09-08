from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from hashlib import sha256
from math import isclose

from .annotation import (
    AdjudicationStatus,
    AnnotationQualityTier,
    AnnotationReviewItem,
)


_SPLITS = ("TRAIN", "CALIBRATION", "CERTIFICATION")


@dataclass(frozen=True)
class GoldADisjointSplit:
    items: tuple[AnnotationReviewItem, ...]
    entity_counts: dict[str, int]
    context_counts_by_split_source: dict[str, dict[str, int]]


@dataclass(frozen=True)
class TrainingOnlyGoldBPartition:
    train_items: tuple[AnnotationReviewItem, ...]
    holdout_issuer_exclusions: tuple[AnnotationReviewItem, ...]


def _stable_key(seed: str, value: str) -> str:
    return sha256(f"{seed}|{value}".encode()).hexdigest()


def _semantic_label_keys(item: AnnotationReviewItem) -> frozenset[str]:
    final = item.final_annotation
    if final is None:
        return frozenset()
    labels = {
        f"CONCEPT:{final.concept_label}",
        f"BINDING:{final.binding_label}",
    }
    if final.role_label is not None:
        labels.add(f"ROLE:{final.role_label}")
    return frozenset(labels)


def assign_gold_a_splits(
    items: tuple[AnnotationReviewItem, ...],
    *,
    train_fraction: float = 0.70,
    calibration_fraction: float = 0.15,
    certification_fraction: float = 0.15,
    seed: str = "TEXT_IE_GOLD_A_SPLIT_V1",
) -> GoldADisjointSplit:
    """Assign GOLD_A by issuer, with document leakage impossible by contract."""

    fractions = {
        "TRAIN": train_fraction,
        "CALIBRATION": calibration_fraction,
        "CERTIFICATION": certification_fraction,
    }
    if any(value <= 0 for value in fractions.values()) or not isclose(
        sum(fractions.values()), 1.0, abs_tol=1e-9
    ):
        raise ValueError("GOLD_A split fractions must be positive and sum to one")
    if not items:
        raise ValueError("cannot split an empty GOLD_A corpus")
    if any(
        item.quality_tier is not AnnotationQualityTier.GOLD_A
        or item.adjudication_status is not AdjudicationStatus.ADJUDICATED
        or item.final_annotation is None
        for item in items
    ):
        raise ValueError("only adjudicated GOLD_A items may be split")

    contexts: dict[str, list[AnnotationReviewItem]] = defaultdict(list)
    document_entities: dict[str, str] = {}
    for item in items:
        contexts[item.candidate_id].append(item)
        prior = document_entities.setdefault(item.source_sha256, item.entity)
        if prior != item.entity:
            raise ValueError("one source document cannot belong to multiple issuers")
    context_rows = {}
    for context_id, rows in contexts.items():
        identities = {
            (row.entity, row.source_sha256, row.source_slice.value) for row in rows
        }
        if len(identities) != 1:
            raise ValueError("one annotation context cannot cross issuer/document/source slice")
        context_rows[context_id] = rows[0]

    entity_contexts: dict[str, list[AnnotationReviewItem]] = defaultdict(list)
    for row in context_rows.values():
        entity_contexts[row.entity].append(row)
    source_slices = tuple(sorted({row.source_slice.value for row in context_rows.values()}))
    supporting_entities = {
        source_slice: {
            entity
            for entity, rows in entity_contexts.items()
            if any(row.source_slice.value == source_slice for row in rows)
        }
        for source_slice in source_slices
    }
    for source_slice, entities in supporting_entities.items():
        if len(entities) < len(_SPLITS):
            raise ValueError(
                f"{source_slice} requires three issuer-disjoint source examples; "
                f"found {len(entities)} issuers"
            )

    vectors = {
        entity: Counter(row.source_slice.value for row in rows)
        for entity, rows in entity_contexts.items()
    }
    entity_labels = {
        entity: frozenset(
            label
            for item in items
            if item.entity == entity
            for label in _semantic_label_keys(item)
        )
        for entity in entity_contexts
    }
    supporting_entities_by_label = {
        label: {
            entity for entity, labels in entity_labels.items() if label in labels
        }
        for label in {
            label for labels in entity_labels.values() for label in labels
        }
    }
    totals = Counter(row.source_slice.value for row in context_rows.values())
    assignments: dict[str, str] = {}
    counts = {split: Counter() for split in _SPLITS}

    # Split construction may inspect labels before the holdouts are sealed. Pin
    # at least one supporting issuer for every task label to TRAIN so no
    # calibration/certification label is impossible for the fitted head.
    covered_train_labels: set[str] = set()
    for label in sorted(
        supporting_entities_by_label,
        key=lambda value: (len(supporting_entities_by_label[value]), value),
    ):
        if label in covered_train_labels:
            continue
        candidates = tuple(
            entity
            for entity in supporting_entities_by_label[label]
            if entity not in assignments or assignments[entity] == "TRAIN"
        )
        if not candidates:
            raise ValueError(f"cannot reserve TRAIN support for semantic label: {label}")
        entity = min(
            candidates,
            key=lambda value: (
                0 if assignments.get(value) == "TRAIN" else 1,
                -len(entity_labels[value] - covered_train_labels),
                _stable_key(seed, value),
            ),
        )
        if entity not in assignments:
            assignments[entity] = "TRAIN"
            counts["TRAIN"].update(vectors[entity])
        covered_train_labels.update(entity_labels[entity])

    # Seed every observed source slice into every split before ratio fitting.
    for source_slice in sorted(source_slices, key=lambda value: len(supporting_entities[value])):
        for split in _SPLITS:
            if counts[split][source_slice]:
                continue
            candidates = tuple(
                entity
                for entity in supporting_entities[source_slice]
                if entity not in assignments or assignments[entity] == split
            )
            if not candidates:
                raise ValueError(
                    f"cannot construct issuer-disjoint coverage for {source_slice} in {split}"
                )
            entity = min(
                candidates,
                key=lambda value: (
                    0 if assignments.get(value) == split else 1,
                    -sum(
                        counts[split][candidate_slice] == 0
                        for candidate_slice in vectors[value]
                    ),
                    _stable_key(seed, value),
                ),
            )
            if entity not in assignments:
                assignments[entity] = split
                counts[split].update(vectors[entity])

    targets = {
        split: {
            source_slice: totals[source_slice] * fractions[split]
            for source_slice in source_slices
        }
        for split in _SPLITS
    }
    remaining = sorted(
        set(entity_contexts) - set(assignments),
        key=lambda value: (-sum(vectors[value].values()), _stable_key(seed, value)),
    )
    for entity in remaining:
        vector = vectors[entity]

        def cost(split: str) -> tuple[float, str]:
            squared_error = sum(
                (
                    (counts[split][source_slice] + vector[source_slice])
                    - targets[split][source_slice]
                ) ** 2
                / max(targets[split][source_slice], 1.0) ** 2
                for source_slice in source_slices
            )
            return squared_error, split

        selected = min(_SPLITS, key=cost)
        assignments[entity] = selected
        counts[selected].update(vector)

    for split in _SPLITS:
        for source_slice in source_slices:
            if not counts[split][source_slice]:
                raise ValueError(
                    f"split coverage invariant failed: {split}/{source_slice}"
                )
    split_items = tuple(
        replace(item, split=assignments[item.entity])
        for item in sorted(items, key=lambda row: row.queue_item_id)
    )
    return GoldADisjointSplit(
        items=split_items,
        entity_counts=dict(sorted(Counter(assignments.values()).items())),
        context_counts_by_split_source={
            split: dict(sorted(counts[split].items())) for split in _SPLITS
        },
    )


def partition_pair_gold_b_for_training(
    items: tuple[AnnotationReviewItem, ...],
    *,
    gold_a_items: tuple[AnnotationReviewItem, ...],
) -> TrainingOnlyGoldBPartition:
    """Keep incomplete-graph pair gold in TRAIN without holdout leakage."""

    if any(
        item.quality_tier is not AnnotationQualityTier.GOLD_B
        or item.adjudication_status is not AdjudicationStatus.ADJUDICATED
        or item.final_annotation is None
        or len({row.annotator_id for row in item.human_annotations}) < 2
        or item.adjudicator_id is None
        for item in items
    ):
        raise ValueError(
            "training-only pair GOLD_B requires independent A/B adjudication"
        )
    if any(
        item.quality_tier is not AnnotationQualityTier.GOLD_A
        or item.split not in _SPLITS
        for item in gold_a_items
    ):
        raise ValueError("pair GOLD_B partition requires assigned GOLD_A splits")
    document_entities = {}
    for item in (*gold_a_items, *items):
        prior = document_entities.setdefault(item.source_sha256, item.entity)
        if prior != item.entity:
            raise ValueError("one source document cannot belong to multiple issuers")
    holdout_entities = {
        item.entity
        for item in gold_a_items
        if item.split in {"CALIBRATION", "CERTIFICATION"}
    }
    included = tuple(
        replace(item, split="TRAIN")
        for item in sorted(items, key=lambda row: row.queue_item_id)
        if item.entity not in holdout_entities
    )
    excluded = tuple(
        item
        for item in sorted(items, key=lambda row: row.queue_item_id)
        if item.entity in holdout_entities
    )
    return TrainingOnlyGoldBPartition(included, excluded)


__all__ = [
    "GoldADisjointSplit",
    "TrainingOnlyGoldBPartition",
    "assign_gold_a_splits",
    "partition_pair_gold_b_for_training",
]
