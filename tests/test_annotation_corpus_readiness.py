from __future__ import annotations

from dataclasses import replace

from equity_platform.text_ie.training import (
    AdjudicationStatus,
    AnnotationQualityTier,
    AnnotationReviewItem,
    AnnotationSourceSlice,
    FinalPairAnnotation,
    HumanPairAnnotation,
    PairProposal,
    TextSpan,
    assess_annotation_corpus,
)


def _gold_item(
    candidate_id: str,
    *,
    binding: str,
    second_binding: str | None = None,
) -> AnnotationReviewItem:
    text = "Revenue was $10 million."
    metric = TextSpan(0, 7, "Revenue")
    quantity = TextSpan(12, 23, "$10 million")

    def annotation(label: str) -> FinalPairAnnotation:
        return FinalPairAnnotation(
            metric_span=metric,
            quantity_span=quantity,
            concept_label="REVENUE",
            binding_label=label,
            role_label="VALUE_CURRENT" if label == "BELONGS_TO" else None,
            scope="CONSOLIDATED",
            period="2026Q2",
        )

    final = annotation(binding)
    return AnnotationReviewItem(
        schema_version="1.0.0",
        queue_item_id=f"queue-{candidate_id}",
        candidate_id=candidate_id,
        entity="TEST",
        source_path=f"D:/{candidate_id}.htm",
        source_sha256=("a" if candidate_id == "one" else "b") * 64,
        source_slice=AnnotationSourceSlice.SEC_10K,
        document_char_start=0,
        document_char_end=len(text),
        text=text,
        proposal=PairProposal(
            metric,
            quantity,
            "REVENUE",
            binding,
            final.role_label,
            "TEST_FIXTURE",
        ),
        legacy_route="TEXT_IE",
        legacy_expected_frames=(),
        legacy_annotation_files=("v290.jsonl",),
        adjudication_status=AdjudicationStatus.ADJUDICATED,
        quality_tier=AnnotationQualityTier.GOLD_A,
        split="CERTIFICATION",
        human_annotations=(
            HumanPairAnnotation("annotator-a", annotation(binding)),
            HumanPairAnnotation(
                "annotator-b",
                annotation(second_binding or binding),
            ),
        ),
        adjudicator_id="adjudicator-c",
        final_annotation=final,
    )


def test_source_slice_readiness_counts_positive_negative_roles_and_iaa() -> None:
    items = (
        _gold_item("one", binding="BELONGS_TO"),
        _gold_item("two", binding="NOT_RELATED"),
    )

    result = assess_annotation_corpus(
        items,
        minimum_research_contexts=2,
        minimum_gold_a_contexts=2,
        minimum_positive_bindings=1,
        minimum_negative_bindings=1,
        minimum_role_examples=1,
        minimum_binding_agreement=0.80,
    )

    ten_k = result.by_source_slice[AnnotationSourceSlice.SEC_10K]
    assert ten_k.research_contexts == 2
    assert ten_k.gold_a_contexts == 2
    assert ten_k.positive_bindings == 1
    assert ten_k.negative_bindings == 1
    assert ten_k.role_examples == 1
    assert ten_k.binding_agreement == 1.0
    assert ten_k.binding_kappa == 1.0
    assert ten_k.ready_for_source_benchmark
    assert not result.all_benchmark_slices_ready


def test_disagreement_is_measured_instead_of_hidden_by_final_adjudication() -> None:
    items = (
        _gold_item("one", binding="BELONGS_TO"),
        _gold_item(
            "two",
            binding="NOT_RELATED",
            second_binding="BELONGS_TO",
        ),
    )

    result = assess_annotation_corpus(
        items,
        minimum_research_contexts=1,
        minimum_gold_a_contexts=1,
        minimum_positive_bindings=0,
        minimum_negative_bindings=0,
        minimum_role_examples=0,
        minimum_binding_agreement=0.80,
    )

    ten_k = result.by_source_slice[AnnotationSourceSlice.SEC_10K]
    assert ten_k.binding_agreement == 0.5
    assert ten_k.binding_kappa == 0.0
    assert not ten_k.ready_for_source_benchmark
    assert "LOW_BINDING_AGREEMENT" in ten_k.reasons


def test_unadjudicated_disagreement_still_contributes_to_iaa() -> None:
    disagreed = replace(
        _gold_item(
            "one",
            binding="NOT_RELATED",
            second_binding="BELONGS_TO",
        ),
        adjudication_status=AdjudicationStatus.DISAGREEMENT,
        quality_tier=AnnotationQualityTier.WEAK,
        adjudicator_id=None,
        final_annotation=None,
        split="UNASSIGNED",
    )

    result = assess_annotation_corpus(
        (disagreed,),
        minimum_research_contexts=0,
        minimum_gold_a_contexts=0,
        minimum_positive_bindings=0,
        minimum_negative_bindings=0,
        minimum_role_examples=0,
        minimum_binding_agreement=0.80,
    )

    ten_k = result.by_source_slice[AnnotationSourceSlice.SEC_10K]
    assert ten_k.double_annotated_pairs == 1
    assert ten_k.binding_agreement == 0.0
    assert "LOW_BINDING_AGREEMENT" in ten_k.reasons
