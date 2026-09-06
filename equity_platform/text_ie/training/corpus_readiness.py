from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .annotation import (
    AnnotationQualityTier,
    AnnotationReviewItem,
    AnnotationSourceSlice,
)


BENCHMARK_SOURCE_SLICES = (
    AnnotationSourceSlice.SEC_10K,
    AnnotationSourceSlice.SEC_10Q,
    AnnotationSourceSlice.IR_PREPARED_REMARKS,
    AnnotationSourceSlice.IR_QA,
)


@dataclass(frozen=True)
class SourceSliceReadiness:
    source_slice: AnnotationSourceSlice
    research_contexts: int
    gold_a_contexts: int
    positive_bindings: int
    negative_bindings: int
    role_examples: int
    double_annotated_pairs: int
    binding_agreement: float | None
    binding_kappa: float | None
    exact_pair_agreement: float | None
    ready_for_source_benchmark: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AnnotationCorpusAssessment:
    item_count: int
    unique_context_count: int
    quality_tier_counts: Mapping[AnnotationQualityTier, int]
    by_source_slice: Mapping[AnnotationSourceSlice, SourceSliceReadiness]
    all_benchmark_slices_ready: bool


def _agreement(
    items: tuple[AnnotationReviewItem, ...],
) -> tuple[int, float | None, float | None, float | None]:
    paired = tuple(item for item in items if len(item.human_annotations) >= 2)
    if not paired:
        return 0, None, None, None
    first = [item.human_annotations[0].annotation for item in paired]
    second = [item.human_annotations[1].annotation for item in paired]
    binding_agreement = sum(
        left.binding_label == right.binding_label
        for left, right in zip(first, second, strict=True)
    ) / len(paired)
    labels = {item.binding_label for item in (*first, *second)}
    first_counts = Counter(item.binding_label for item in first)
    second_counts = Counter(item.binding_label for item in second)
    expected = sum(
        (first_counts[label] / len(paired)) * (second_counts[label] / len(paired))
        for label in labels
    )
    if expected == 1.0:
        kappa = 1.0 if binding_agreement == 1.0 else 0.0
    else:
        kappa = (binding_agreement - expected) / (1.0 - expected)
    exact = sum(
        left == right for left, right in zip(first, second, strict=True)
    ) / len(paired)
    return len(paired), binding_agreement, kappa, exact


def assess_annotation_corpus(
    items: tuple[AnnotationReviewItem, ...],
    *,
    minimum_research_contexts: int = 50,
    minimum_gold_a_contexts: int = 50,
    minimum_positive_bindings: int = 30,
    minimum_negative_bindings: int = 30,
    minimum_role_examples: int = 30,
    minimum_binding_agreement: float = 0.80,
) -> AnnotationCorpusAssessment:
    by_slice: dict[AnnotationSourceSlice, SourceSliceReadiness] = {}
    for source_slice in AnnotationSourceSlice:
        selected = tuple(item for item in items if item.source_slice is source_slice)
        research = tuple(
            item
            for item in selected
            if item.quality_tier in {
                AnnotationQualityTier.GOLD_A,
                AnnotationQualityTier.GOLD_B,
            }
        )
        gold_a = tuple(
            item for item in selected if item.quality_tier is AnnotationQualityTier.GOLD_A
        )
        finals = tuple(
            item.final_annotation
            for item in gold_a
            if item.final_annotation is not None
        )
        positives = sum(item.binding_label == "BELONGS_TO" for item in finals)
        negatives = sum(item.binding_label == "NOT_RELATED" for item in finals)
        roles = sum(item.binding_label == "BELONGS_TO" for item in finals)
        # Agreement measures the independent judgments themselves, including
        # unresolved disagreements that have not (and must not) become gold.
        pair_count, agreement, kappa, exact = _agreement(selected)
        reasons = []
        if len({item.candidate_id for item in research}) < minimum_research_contexts:
            reasons.append("INSUFFICIENT_RESEARCH_CONTEXTS")
        if len({item.candidate_id for item in gold_a}) < minimum_gold_a_contexts:
            reasons.append("INSUFFICIENT_GOLD_A_CONTEXTS")
        if positives < minimum_positive_bindings:
            reasons.append("INSUFFICIENT_POSITIVE_BINDINGS")
        if negatives < minimum_negative_bindings:
            reasons.append("INSUFFICIENT_NEGATIVE_BINDINGS")
        if roles < minimum_role_examples:
            reasons.append("INSUFFICIENT_ROLE_EXAMPLES")
        if agreement is None:
            reasons.append("NO_DOUBLE_ANNOTATED_PAIRS")
        elif agreement < minimum_binding_agreement:
            reasons.append("LOW_BINDING_AGREEMENT")
        by_slice[source_slice] = SourceSliceReadiness(
            source_slice=source_slice,
            research_contexts=len({item.candidate_id for item in research}),
            gold_a_contexts=len({item.candidate_id for item in gold_a}),
            positive_bindings=positives,
            negative_bindings=negatives,
            role_examples=roles,
            double_annotated_pairs=pair_count,
            binding_agreement=agreement,
            binding_kappa=kappa,
            exact_pair_agreement=exact,
            ready_for_source_benchmark=not reasons,
            reasons=tuple(reasons),
        )
    tier_counts = Counter(item.quality_tier for item in items)
    return AnnotationCorpusAssessment(
        item_count=len(items),
        unique_context_count=len({item.candidate_id for item in items}),
        quality_tier_counts=MappingProxyType({
            tier: tier_counts[tier] for tier in AnnotationQualityTier
        }),
        by_source_slice=MappingProxyType(by_slice),
        all_benchmark_slices_ready=all(
            by_slice[source_slice].ready_for_source_benchmark
            for source_slice in BENCHMARK_SOURCE_SLICES
        ),
    )


__all__ = [
    "AnnotationCorpusAssessment",
    "BENCHMARK_SOURCE_SLICES",
    "SourceSliceReadiness",
    "assess_annotation_corpus",
]
