from __future__ import annotations

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
    annotation_review_item_from_dict,
    adjudicate_review_item,
    load_annotation_review_queue,
    record_human_annotation,
    write_annotation_review_queue,
)


def _pending_item() -> AnnotationReviewItem:
    text = "Revenue was $10 million while EBITDA was $3 million."
    return AnnotationReviewItem(
        schema_version="1.0.0",
        queue_item_id="queue-1",
        candidate_id="candidate-1",
        entity="TEST",
        source_path="D:/source.htm",
        source_sha256="a" * 64,
        source_slice=AnnotationSourceSlice.IR_UNSPECIFIED,
        document_char_start=100,
        document_char_end=100 + len(text),
        text=text,
        proposal=PairProposal(
            metric_span=TextSpan(0, 7, "Revenue"),
            quantity_span=TextSpan(12, 23, "$10 million"),
            concept_label="REVENUE",
            binding_hint="BELONGS_TO",
            role_hint="VALUE_CURRENT",
            generator="LEGACY_FRAME_VALUE_MATCH",
        ),
        legacy_route="TEXT_IE",
        legacy_expected_frames=({"concept": "REVENUE", "value": 10_000_000.0},),
        legacy_annotation_files=("v290_annotations.jsonl",),
        adjudication_status=AdjudicationStatus.PENDING,
        quality_tier=AnnotationQualityTier.WEAK,
        split="UNASSIGNED",
    )


def test_pending_review_item_round_trips_without_becoming_gold() -> None:
    item = _pending_item()

    restored = annotation_review_item_from_dict(item.to_dict())

    assert restored == item
    assert restored.quality_tier is AnnotationQualityTier.WEAK
    assert restored.final_annotation is None


def test_gold_a_requires_double_annotation_and_adjudicated_final_pair() -> None:
    pending = _pending_item()
    final = FinalPairAnnotation(
        metric_span=pending.proposal.metric_span,
        quantity_span=pending.proposal.quantity_span,
        concept_label="REVENUE",
        binding_label="BELONGS_TO",
        role_label="VALUE_CURRENT",
        scope="CONSOLIDATED",
        period="2026Q2",
    )

    with pytest.raises(ValueError, match="two independent annotators"):
        replace(
            pending,
            adjudication_status=AdjudicationStatus.ADJUDICATED,
            quality_tier=AnnotationQualityTier.GOLD_A,
            human_annotations=(HumanPairAnnotation("annotator-a", final),),
            adjudicator_id="adjudicator-c",
            final_annotation=final,
        )

    gold = replace(
        pending,
        adjudication_status=AdjudicationStatus.ADJUDICATED,
        quality_tier=AnnotationQualityTier.GOLD_A,
        human_annotations=(
            HumanPairAnnotation("annotator-a", final),
            HumanPairAnnotation("annotator-b", final),
        ),
        adjudicator_id="adjudicator-c",
        final_annotation=final,
    )
    assert gold.certification_eligible

    with pytest.raises(ValueError, match="separate from annotators"):
        replace(gold, adjudicator_id="annotator-a")


def test_unrelated_final_pair_cannot_receive_a_numeric_role() -> None:
    pending = _pending_item()

    with pytest.raises(ValueError, match="NOT_RELATED"):
        FinalPairAnnotation(
            metric_span=pending.proposal.metric_span,
            quantity_span=pending.proposal.quantity_span,
            concept_label="REVENUE",
            binding_label="NOT_RELATED",
            role_label="VALUE_CURRENT",
            scope="CONSOLIDATED",
            period="2026Q2",
        )

    unrelated = FinalPairAnnotation(
        metric_span=pending.proposal.metric_span,
        quantity_span=pending.proposal.quantity_span,
        concept_label="REVENUE",
        binding_label="NOT_RELATED",
        role_label=None,
        scope="",
        period="",
    )
    assert unrelated.scope == ""
    assert unrelated.period == ""


def test_review_queue_jsonl_is_deterministic_and_validated_on_load(tmp_path) -> None:
    output = tmp_path / "review_queue.jsonl"
    item = _pending_item()

    write_annotation_review_queue(output, (item,))

    assert load_annotation_review_queue(output) == (item,)
    assert output.read_text(encoding="utf-8").endswith("\n")


def test_independent_disagreement_requires_separate_adjudication() -> None:
    pending = _pending_item()
    proposal = pending.proposal

    def final(binding: str) -> FinalPairAnnotation:
        return FinalPairAnnotation(
            metric_span=proposal.metric_span,
            quantity_span=proposal.quantity_span,
            concept_label="REVENUE",
            binding_label=binding,
            role_label="VALUE_CURRENT" if binding == "BELONGS_TO" else None,
            scope="CONSOLIDATED",
            period="2026Q2",
            quantity_kind="MONEY",
        )

    once = record_human_annotation(
        pending,
        HumanPairAnnotation("annotator-a", final("BELONGS_TO")),
    )
    assert once.quality_tier is AnnotationQualityTier.GOLD_B
    assert once.adjudication_status is AdjudicationStatus.HUMAN_VERIFIED

    disagreed = record_human_annotation(
        once,
        HumanPairAnnotation("annotator-b", final("NOT_RELATED")),
    )
    assert disagreed.adjudication_status is AdjudicationStatus.DISAGREEMENT
    assert disagreed.quality_tier is AnnotationQualityTier.WEAK
    assert disagreed.final_annotation is None

    resolved = adjudicate_review_item(
        disagreed,
        adjudicator_id="adjudicator-c",
        final_annotation=final("BELONGS_TO"),
    )
    assert resolved.quality_tier is AnnotationQualityTier.GOLD_A
    assert resolved.certification_eligible
