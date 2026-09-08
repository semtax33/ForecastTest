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
    assess_semantic_training_readiness,
    build_semantic_training_dataset_from_review_queue,
)


def _reviewed_pair(
    queue_id: str,
    *,
    quantity: TextSpan,
    binding: str,
) -> AnnotationReviewItem:
    text = "Revenue was $10 million and EBITDA was $3 million."
    metric = TextSpan(0, 7, "Revenue")
    final = FinalPairAnnotation(
        metric_span=metric,
        quantity_span=quantity,
        concept_label="REVENUE",
        binding_label=binding,
        role_label="VALUE_CURRENT" if binding == "BELONGS_TO" else None,
        scope="CONSOLIDATED",
        period="2026Q2",
    )
    return AnnotationReviewItem(
        schema_version="1.0.0",
        queue_item_id=queue_id,
        candidate_id="context-1",
        entity="TEST",
        source_path="D:/10-k.htm",
        source_sha256="a" * 64,
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
            HumanPairAnnotation("annotator-a", final),
            HumanPairAnnotation("annotator-b", final),
        ),
        adjudicator_id="adjudicator-c",
        final_annotation=final,
    )


def test_adjudicated_queue_builds_deduplicated_three_head_training_data() -> None:
    items = (
        _reviewed_pair(
            "pair-positive",
            quantity=TextSpan(12, 23, "$10 million"),
            binding="BELONGS_TO",
        ),
        _reviewed_pair(
            "pair-negative",
            quantity=TextSpan(39, 49, "$3 million"),
            binding="NOT_RELATED",
        ),
    )

    dataset = build_semantic_training_dataset_from_review_queue(items)

    assert dataset.source_example_count == 1
    assert len(dataset.spans) == 1
    assert dataset.spans[0].metric_literal == "Revenue"
    assert dataset.spans[0].concept_label == "REVENUE"
    assert len(dataset.concepts) == 1
    assert len(dataset.relations) == 2
    assert len(dataset.roles) == 1
    assert {item.binding_label for item in dataset.relations} == {
        "BELONGS_TO",
        "NOT_RELATED",
    }
    assert dataset.roles[0].role_label == "VALUE_CURRENT"
    assert dataset.certification_eligible


def test_same_local_span_in_two_document_contexts_is_not_collapsed() -> None:
    first = _reviewed_pair(
        "pair-one",
        quantity=TextSpan(12, 23, "$10 million"),
        binding="BELONGS_TO",
    )
    second = replace(
        first,
        queue_item_id="pair-two",
        candidate_id="context-2",
        document_char_start=100,
        document_char_end=100 + len(first.text),
    )

    dataset = build_semantic_training_dataset_from_review_queue((first, second))

    assert dataset.source_example_count == 2
    assert len(dataset.concepts) == 2

    readiness = assess_semantic_training_readiness(
        dataset,
        minimum_text_contexts=3,
        minimum_concept_examples=1,
        minimum_relation_pairs=1,
        minimum_role_examples=1,
        minimum_positive_bindings=1,
        minimum_negative_bindings=1,
    )
    assert readiness.text_context_count == 2
    assert "INSUFFICIENT_TEXT_CONTEXTS" in readiness.reasons


def test_pair_adjudicated_in_incomplete_context_is_training_only_independent_gold_b() -> None:
    item = replace(
        _reviewed_pair(
            "pair-training-only",
            quantity=TextSpan(12, 23, "$10 million"),
            binding="BELONGS_TO",
        ),
        quality_tier=AnnotationQualityTier.GOLD_B,
        split="TRAIN",
    )

    dataset = build_semantic_training_dataset_from_review_queue(
        (item,), minimum_quality=AnnotationQualityTier.GOLD_B
    )

    assert dataset.relations[0].annotation_source == (
        "INDEPENDENT_HUMAN_ADJUDICATED_GOLD_B_INCOMPLETE_GRAPH"
    )
    assert not dataset.certification_eligible
