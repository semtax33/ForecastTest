from __future__ import annotations

from dataclasses import dataclass

from .annotation import AnnotationQualityTier, AnnotationReviewItem
from .staged_gold import StagedGoldExample


@dataclass(frozen=True)
class ConceptClassificationExample:
    example_id: str
    entity: str
    source_kind: str
    source_sha256: str
    holdout_axis: str
    gold_route: str
    context: str
    marked_context: str
    metric_literal: str
    metric_char_start: int
    metric_char_end: int
    concept_label: str
    annotation_source: str


@dataclass(frozen=True)
class RelationClassificationExample:
    example_id: str
    entity: str
    source_kind: str
    source_sha256: str
    holdout_axis: str
    gold_route: str
    context: str
    marked_context: str
    metric_literal: str
    metric_char_start: int
    metric_char_end: int
    quantity_literal: str
    quantity_char_start: int
    quantity_char_end: int
    quantity_kind: str
    concept_label: str
    binding_label: str
    annotation_source: str


@dataclass(frozen=True)
class RoleClassificationExample:
    example_id: str
    entity: str
    source_kind: str
    source_sha256: str
    holdout_axis: str
    gold_route: str
    context: str
    marked_context: str
    metric_literal: str
    metric_char_start: int
    metric_char_end: int
    quantity_literal: str
    quantity_char_start: int
    quantity_char_end: int
    quantity_kind: str
    concept_label: str
    role_label: str
    annotation_source: str


@dataclass(frozen=True)
class SemanticTrainingDataset:
    concepts: tuple[ConceptClassificationExample, ...]
    relations: tuple[RelationClassificationExample, ...]
    roles: tuple[RoleClassificationExample, ...]
    source_example_count: int
    certification_eligible: bool = False


@dataclass(frozen=True)
class SemanticTrainingReadiness:
    text_context_count: int
    concept_example_count: int
    relation_pair_count: int
    role_example_count: int
    positive_binding_count: int
    negative_binding_count: int
    independently_human_adjudicated: bool
    ready: bool
    reasons: tuple[str, ...]


def _marked_text(
    text: str,
    spans: tuple[tuple[int, int, str, str], ...],
) -> str:
    ordered = tuple(sorted(spans, key=lambda item: (item[0], item[1])))
    if any(left_end > right_start for (_, left_end, _, _), (right_start, _, _, _) in zip(ordered, ordered[1:])):
        raise ValueError("semantic training spans must not overlap")
    output = []
    cursor = 0
    for start, end, opening, closing in ordered:
        if not 0 <= start < end <= len(text):
            raise ValueError("semantic training span is outside the source text")
        output.extend((text[cursor:start], opening, text[start:end], closing))
        cursor = end
    output.append(text[cursor:])
    return "".join(output)


def build_semantic_training_dataset(
    examples: tuple[StagedGoldExample, ...],
) -> SemanticTrainingDataset:
    """Convert staged text gold into concept and pair-classification tasks.

    Positional tables are deliberately excluded.  Negative relation examples
    are the unbound concept/quantity cross-product inside a fully annotated
    TEXT_IE clause, never synthetic cross-document pairs.
    """

    concepts = []
    relations = []
    roles = []
    for example in examples:
        if example.gold_route == "TABLE_DSL":
            continue
        concept_by_id = {item.node_id: item for item in example.concepts}
        quantity_by_id = {item.node_id: item for item in example.quantities}
        binding_pairs = {
            (edge.concept_id, edge.quantity_id)
            for edge in example.binding_edges
        }
        role_by_pair = {
            (edge.concept_id, edge.quantity_id): edge.role
            for edge in example.role_edges
        }
        for concept in example.concepts:
            concepts.append(ConceptClassificationExample(
                example_id=example.example_id,
                entity=example.entity,
                source_kind=example.source_kind,
                source_sha256=example.source_sha256,
                holdout_axis=example.holdout_axis.value,
                gold_route=example.gold_route,
                context=example.text,
                marked_context=_marked_text(example.text, ((
                    concept.char_start,
                    concept.char_end,
                    "[METRIC]",
                    "[/METRIC]",
                ),)),
                metric_literal=example.text[concept.char_start:concept.char_end],
                metric_char_start=concept.char_start,
                metric_char_end=concept.char_end,
                concept_label=concept.concept,
                annotation_source=example.annotation_source,
            ))
        if example.gold_route != "TEXT_IE":
            continue
        for concept_id, concept in concept_by_id.items():
            for quantity_id, quantity in quantity_by_id.items():
                pair = (concept_id, quantity_id)
                relations.append(RelationClassificationExample(
                    example_id=example.example_id,
                    entity=example.entity,
                    source_kind=example.source_kind,
                    source_sha256=example.source_sha256,
                    holdout_axis=example.holdout_axis.value,
                    gold_route=example.gold_route,
                    context=example.text,
                    marked_context=_marked_text(example.text, (
                        (
                            concept.char_start,
                            concept.char_end,
                            "[METRIC]",
                            "[/METRIC]",
                        ),
                        (
                            quantity.char_start,
                            quantity.char_end,
                            "[QTY]",
                            "[/QTY]",
                        ),
                    )),
                    metric_literal=example.text[concept.char_start:concept.char_end],
                    metric_char_start=concept.char_start,
                    metric_char_end=concept.char_end,
                    quantity_literal=example.text[quantity.char_start:quantity.char_end],
                    quantity_char_start=quantity.char_start,
                    quantity_char_end=quantity.char_end,
                    quantity_kind=quantity.kind,
                    concept_label=concept.concept,
                    binding_label=(
                        "BELONGS_TO" if pair in binding_pairs else "NOT_RELATED"
                    ),
                    annotation_source=example.annotation_source,
                ))
                if pair in binding_pairs:
                    role = role_by_pair.get(pair)
                    if role is None:
                        raise ValueError(
                            "bound semantic training pairs require an explicit role"
                        )
                    roles.append(RoleClassificationExample(
                        example_id=example.example_id,
                        entity=example.entity,
                        source_kind=example.source_kind,
                        source_sha256=example.source_sha256,
                        holdout_axis=example.holdout_axis.value,
                        gold_route=example.gold_route,
                        context=example.text,
                        marked_context=_marked_text(example.text, (
                            (
                                concept.char_start,
                                concept.char_end,
                                "[METRIC]",
                                "[/METRIC]",
                            ),
                            (
                                quantity.char_start,
                                quantity.char_end,
                                "[QTY]",
                                "[/QTY]",
                            ),
                        )),
                        metric_literal=example.text[concept.char_start:concept.char_end],
                        metric_char_start=concept.char_start,
                        metric_char_end=concept.char_end,
                        quantity_literal=example.text[quantity.char_start:quantity.char_end],
                        quantity_char_start=quantity.char_start,
                        quantity_char_end=quantity.char_end,
                        quantity_kind=quantity.kind,
                        concept_label=concept.concept,
                        role_label=role,
                        annotation_source=example.annotation_source,
                    ))
    return SemanticTrainingDataset(
        concepts=tuple(concepts),
        relations=tuple(relations),
        roles=tuple(roles),
        source_example_count=len(examples),
    )


def assess_semantic_training_readiness(
    dataset: SemanticTrainingDataset,
    *,
    minimum_text_contexts: int = 300,
    minimum_concept_examples: int = 300,
    minimum_relation_pairs: int = 500,
    minimum_role_examples: int = 200,
    minimum_positive_bindings: int = 200,
    minimum_negative_bindings: int = 200,
) -> SemanticTrainingReadiness:
    """Fail closed before fine-tuning on a small or non-independent corpus."""

    context_ids = {
        item.example_id for item in (*dataset.concepts, *dataset.relations, *dataset.roles)
    }
    annotations = {
        item.annotation_source for item in (*dataset.concepts, *dataset.relations, *dataset.roles)
    }
    independent = bool(annotations) and all(
        "INDEPENDENT_HUMAN" in source for source in annotations
    )
    positive = sum(
        item.binding_label == "BELONGS_TO" for item in dataset.relations
    )
    negative = len(dataset.relations) - positive
    reasons = []
    if len(context_ids) < minimum_text_contexts:
        reasons.append("INSUFFICIENT_TEXT_CONTEXTS")
    if len(dataset.concepts) < minimum_concept_examples:
        reasons.append("INSUFFICIENT_CONCEPT_EXAMPLES")
    if len(dataset.relations) < minimum_relation_pairs:
        reasons.append("INSUFFICIENT_RELATION_PAIRS")
    if len(dataset.roles) < minimum_role_examples:
        reasons.append("INSUFFICIENT_ROLE_EXAMPLES")
    if positive < minimum_positive_bindings:
        reasons.append("INSUFFICIENT_POSITIVE_BINDINGS")
    if negative < minimum_negative_bindings:
        reasons.append("INSUFFICIENT_NEGATIVE_BINDINGS")
    if not independent:
        reasons.append("NO_INDEPENDENT_HUMAN_ADJUDICATION")
    return SemanticTrainingReadiness(
        text_context_count=len(context_ids),
        concept_example_count=len(dataset.concepts),
        relation_pair_count=len(dataset.relations),
        role_example_count=len(dataset.roles),
        positive_binding_count=positive,
        negative_binding_count=negative,
        independently_human_adjudicated=independent,
        ready=not reasons,
        reasons=tuple(reasons),
    )


def build_semantic_training_dataset_from_review_queue(
    items: tuple[AnnotationReviewItem, ...],
    *,
    minimum_quality: AnnotationQualityTier = AnnotationQualityTier.GOLD_B,
) -> SemanticTrainingDataset:
    """Build task datasets only from human-verified review-queue pairs."""

    rank = {
        AnnotationQualityTier.WEAK: 0,
        AnnotationQualityTier.SILVER: 1,
        AnnotationQualityTier.GOLD_B: 2,
        AnnotationQualityTier.GOLD_A: 3,
    }
    selected = tuple(
        item
        for item in items
        if rank[item.quality_tier] >= rank[minimum_quality]
        and item.final_annotation is not None
    )
    concept_rows: dict[tuple[str, int, int], ConceptClassificationExample] = {}
    concept_labels: dict[tuple[str, int, int], str] = {}
    relations = []
    roles = []
    for item in selected:
        final = item.final_annotation
        annotation_source = (
            "INDEPENDENT_HUMAN_GOLD_A"
            if item.quality_tier is AnnotationQualityTier.GOLD_A
            else "SINGLE_HUMAN_GOLD_B"
        )
        concept_key = (
            item.source_sha256,
            final.metric_span.char_start,
            final.metric_span.char_end,
        )
        prior_label = concept_labels.setdefault(concept_key, final.concept_label)
        if prior_label != final.concept_label:
            raise ValueError("one metric span cannot receive conflicting concept labels")
        concept_rows.setdefault(concept_key, ConceptClassificationExample(
            example_id=item.candidate_id,
            entity=item.entity,
            source_kind=item.source_slice.value,
            source_sha256=item.source_sha256,
            holdout_axis=item.split,
            gold_route="TEXT_IE",
            context=item.text,
            marked_context=_marked_text(item.text, ((
                final.metric_span.char_start,
                final.metric_span.char_end,
                "[METRIC]",
                "[/METRIC]",
            ),)),
            metric_literal=final.metric_span.literal,
            metric_char_start=final.metric_span.char_start,
            metric_char_end=final.metric_span.char_end,
            concept_label=final.concept_label,
            annotation_source=annotation_source,
        ))
        marked = _marked_text(item.text, (
            (
                final.metric_span.char_start,
                final.metric_span.char_end,
                "[METRIC]",
                "[/METRIC]",
            ),
            (
                final.quantity_span.char_start,
                final.quantity_span.char_end,
                "[QTY]",
                "[/QTY]",
            ),
        ))
        quantity_kind = final.quantity_kind
        relation = RelationClassificationExample(
            example_id=item.queue_item_id,
            entity=item.entity,
            source_kind=item.source_slice.value,
            source_sha256=item.source_sha256,
            holdout_axis=item.split,
            gold_route="TEXT_IE",
            context=item.text,
            marked_context=marked,
            metric_literal=final.metric_span.literal,
            metric_char_start=final.metric_span.char_start,
            metric_char_end=final.metric_span.char_end,
            quantity_literal=final.quantity_span.literal,
            quantity_char_start=final.quantity_span.char_start,
            quantity_char_end=final.quantity_span.char_end,
            quantity_kind=quantity_kind,
            concept_label=final.concept_label,
            binding_label=final.binding_label,
            annotation_source=annotation_source,
        )
        relations.append(relation)
        if final.binding_label == "BELONGS_TO":
            roles.append(RoleClassificationExample(
                example_id=relation.example_id,
                entity=relation.entity,
                source_kind=relation.source_kind,
                source_sha256=relation.source_sha256,
                holdout_axis=relation.holdout_axis,
                gold_route=relation.gold_route,
                context=relation.context,
                marked_context=relation.marked_context,
                metric_literal=relation.metric_literal,
                metric_char_start=relation.metric_char_start,
                metric_char_end=relation.metric_char_end,
                quantity_literal=relation.quantity_literal,
                quantity_char_start=relation.quantity_char_start,
                quantity_char_end=relation.quantity_char_end,
                quantity_kind=relation.quantity_kind,
                concept_label=relation.concept_label,
                role_label=str(final.role_label),
                annotation_source=annotation_source,
            ))
    return SemanticTrainingDataset(
        concepts=tuple(concept_rows.values()),
        relations=tuple(relations),
        roles=tuple(roles),
        source_example_count=len({item.candidate_id for item in selected}),
        certification_eligible=(
            bool(selected)
            and all(
                item.quality_tier is AnnotationQualityTier.GOLD_A
                and item.certification_eligible
                and item.split == "CERTIFICATION"
                for item in selected
            )
        ),
    )


__all__ = [
    "ConceptClassificationExample",
    "RelationClassificationExample",
    "RoleClassificationExample",
    "SemanticTrainingDataset",
    "SemanticTrainingReadiness",
    "assess_semantic_training_readiness",
    "build_semantic_training_dataset",
    "build_semantic_training_dataset_from_review_queue",
]
