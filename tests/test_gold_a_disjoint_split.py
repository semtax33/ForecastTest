from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

import pytest

from equity_platform.text_ie.training import (
    AdjudicationStatus,
    AnnotationQualityTier,
    AnnotationReviewItem,
    AnnotationSourceSlice,
    FinalPairAnnotation,
    HumanPairAnnotation,
    PairProposal,
    TextSpan,
    adjudicate_review_item,
    assign_gold_a_splits,
    partition_pair_gold_b_for_training,
    record_human_annotation,
)


SLICES = (
    AnnotationSourceSlice.SEC_10K,
    AnnotationSourceSlice.SEC_10Q,
    AnnotationSourceSlice.IR_PREPARED_REMARKS,
    AnnotationSourceSlice.IR_QA,
)


def _gold_item(
    entity_number: int,
    source_slice: AnnotationSourceSlice,
    *,
    concept_label: str = "REVENUE",
) -> AnnotationReviewItem:
    text = "Revenue was $10 million."
    suffix = f"{entity_number}-{source_slice.value}"
    final = FinalPairAnnotation(
        metric_span=TextSpan(0, 7, "Revenue"),
        quantity_span=TextSpan(12, 23, "$10 million"),
        concept_label=concept_label,
        binding_label="BELONGS_TO",
        role_label="VALUE_CURRENT",
        scope="CONSOLIDATED",
        period="FY2025",
        quantity_kind="MONEY",
    )
    item = AnnotationReviewItem(
        schema_version="1.0.0",
        queue_item_id=f"pair-{suffix}",
        candidate_id=f"context-{suffix}",
        entity=f"ENTITY-{entity_number:02d}",
        source_path=f"D:/source-{suffix}.htm",
        source_sha256=f"{entity_number * 10 + list(SLICES).index(source_slice) + 1:064x}",
        source_slice=source_slice,
        document_char_start=0,
        document_char_end=len(text),
        text=text,
        proposal=PairProposal(
            metric_span=final.metric_span,
            quantity_span=final.quantity_span,
            concept_label=concept_label,
            binding_hint="UNREVIEWED",
            role_hint=None,
            generator="TEST",
            quantity_kind="MONEY",
        ),
        legacy_route="TEXT_IE",
        legacy_expected_frames=(),
        legacy_annotation_files=("fixture",),
        adjudication_status=AdjudicationStatus.PENDING,
        quality_tier=AnnotationQualityTier.WEAK,
        split="UNASSIGNED",
    )
    item = record_human_annotation(item, HumanPairAnnotation("A", final))
    item = record_human_annotation(item, HumanPairAnnotation("B", final))
    return adjudicate_review_item(item, adjudicator_id="C", final_annotation=final)


def test_gold_a_split_is_deterministic_issuer_and_document_disjoint() -> None:
    items = tuple(
        _gold_item(entity_number, source_slice)
        for entity_number in range(12)
        for source_slice in SLICES
    )

    first = assign_gold_a_splits(
        items,
        train_fraction=0.5,
        calibration_fraction=0.25,
        certification_fraction=0.25,
    )
    second = assign_gold_a_splits(
        tuple(reversed(items)),
        train_fraction=0.5,
        calibration_fraction=0.25,
        certification_fraction=0.25,
    )

    assert {
        item.queue_item_id: item.split for item in first.items
    } == {
        item.queue_item_id: item.split for item in second.items
    }
    entity_splits = defaultdict(set)
    document_splits = defaultdict(set)
    for item in first.items:
        entity_splits[item.entity].add(item.split)
        document_splits[item.source_sha256].add(item.split)
    assert all(len(values) == 1 for values in entity_splits.values())
    assert all(len(values) == 1 for values in document_splits.values())
    for split in ("TRAIN", "CALIBRATION", "CERTIFICATION"):
        assert set(first.context_counts_by_split_source[split]) == {
            source_slice.value for source_slice in SLICES
        }


def test_gold_a_split_fails_closed_when_slice_cannot_cover_three_splits() -> None:
    items = tuple(
        _gold_item(entity_number, AnnotationSourceSlice.SEC_10K)
        for entity_number in range(2)
    )

    with pytest.raises(ValueError, match="SEC_10K.*three issuer-disjoint"):
        assign_gold_a_splits(items)


def test_gold_a_split_keeps_single_issuer_label_support_in_train() -> None:
    items = tuple(
        _gold_item(
            entity_number,
            source_slice,
            concept_label=(
                "RARE_CONCEPT"
                if entity_number == 2 and source_slice is AnnotationSourceSlice.SEC_10K
                else "REVENUE"
            ),
        )
        for entity_number in range(12)
        for source_slice in SLICES
    )

    split = assign_gold_a_splits(items)

    rare = next(
        item for item in split.items
        if item.final_annotation.concept_label == "RARE_CONCEPT"
    )
    assert rare.split == "TRAIN"
    train_concepts = {
        item.final_annotation.concept_label
        for item in split.items
        if item.split == "TRAIN"
    }
    holdout_concepts = {
        item.final_annotation.concept_label
        for item in split.items
        if item.split in {"CALIBRATION", "CERTIFICATION"}
    }
    assert holdout_concepts <= train_concepts


def test_pair_gold_b_is_train_only_and_holdout_issuers_are_excluded() -> None:
    gold_a = assign_gold_a_splits(tuple(
        _gold_item(entity_number, source_slice)
        for entity_number in range(12)
        for source_slice in SLICES
    )).items
    train_entity = next(item.entity for item in gold_a if item.split == "TRAIN")
    holdout_entity = next(
        item.entity for item in gold_a if item.split == "CERTIFICATION"
    )
    train_template = next(item for item in gold_a if item.entity == train_entity)
    holdout_template = next(item for item in gold_a if item.entity == holdout_entity)
    pair_gold_b = (
        replace(
            train_template,
            queue_item_id="pair-gold-b-train",
            candidate_id="context-gold-b-train",
            entity=train_entity,
            quality_tier=AnnotationQualityTier.GOLD_B,
            split="UNASSIGNED",
        ),
        replace(
            holdout_template,
            queue_item_id="pair-gold-b-holdout",
            candidate_id="context-gold-b-holdout",
            entity=holdout_entity,
            quality_tier=AnnotationQualityTier.GOLD_B,
            split="UNASSIGNED",
        ),
    )

    partition = partition_pair_gold_b_for_training(
        pair_gold_b,
        gold_a_items=gold_a,
    )

    assert [item.queue_item_id for item in partition.train_items] == [
        "pair-gold-b-train"
    ]
    assert partition.train_items[0].split == "TRAIN"
    assert [item.queue_item_id for item in partition.holdout_issuer_exclusions] == [
        "pair-gold-b-holdout"
    ]
