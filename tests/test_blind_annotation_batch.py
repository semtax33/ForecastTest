from __future__ import annotations

from equity_platform.text_ie.training import (
    AdjudicationStatus,
    AnnotationQualityTier,
    AnnotationReviewItem,
    AnnotationSourceSlice,
    PairProposal,
    TextSpan,
    build_blind_annotation_batch,
)


def _item(
    *,
    source_slice: AnnotationSourceSlice,
    context_number: int,
    entity: str,
    pair_number: int,
) -> AnnotationReviewItem:
    text = "Revenue was $10 million and margin was 12%."
    spans = (
        (TextSpan(0, 7, "Revenue"), TextSpan(12, 23, "$10 million"), "REVENUE"),
        (TextSpan(28, 34, "margin"), TextSpan(39, 42, "12%"), "MARGIN"),
    )
    metric, quantity, concept = spans[pair_number]
    candidate_id = f"{source_slice.value}-{context_number}"
    return AnnotationReviewItem(
        schema_version="1.0.0",
        queue_item_id=f"pair-{source_slice.value}-{context_number}-{pair_number}",
        candidate_id=candidate_id,
        entity=entity,
        source_path=f"D:/{candidate_id}.htm",
        source_sha256=f"{context_number + 1:064x}",
        source_slice=source_slice,
        document_char_start=0,
        document_char_end=len(text),
        text=text,
        proposal=PairProposal(
            metric_span=metric,
            quantity_span=quantity,
            concept_label=concept,
            binding_hint="BELONGS_TO",
            role_hint="VALUE_CURRENT",
            generator="TEST_HINT_MUST_BE_HIDDEN",
            quantity_kind="MONEY" if pair_number == 0 else "PERCENT",
        ),
        legacy_route="TEXT_IE",
        legacy_expected_frames=(),
        legacy_annotation_files=("test.jsonl",),
        adjudication_status=AdjudicationStatus.PENDING,
        quality_tier=AnnotationQualityTier.WEAK,
        split="UNASSIGNED",
    )


def _items() -> tuple[AnnotationReviewItem, ...]:
    rows = []
    for source_slice in (
        AnnotationSourceSlice.SEC_10K,
        AnnotationSourceSlice.SEC_10Q,
        AnnotationSourceSlice.IR_PREPARED_REMARKS,
        AnnotationSourceSlice.IR_QA,
    ):
        for context_number, entity in enumerate(("A", "A", "B")):
            for pair_number in range(2):
                rows.append(_item(
                    source_slice=source_slice,
                    context_number=context_number,
                    entity=entity,
                    pair_number=pair_number,
                ))
    return tuple(rows)


def test_blind_batch_has_complete_pairs_and_entity_balanced_contexts() -> None:
    batch = build_blind_annotation_batch(_items(), contexts_per_slice=2)

    assert len(batch.context_rows) == 8
    assert len(batch.pair_rows) == 16
    for source_slice in (
        "SEC_10K", "SEC_10Q", "IR_PREPARED_REMARKS", "IR_QA"
    ):
        selected = [
            row for row in batch.context_rows if row["source_slice"] == source_slice
        ]
        assert len(selected) == 2
        assert {row["entity"] for row in selected} == {"A", "B"}


def test_blind_assignments_hide_every_machine_label_and_shuffle_independently() -> None:
    batch = build_blind_annotation_batch(_items(), contexts_per_slice=2)

    assert {row["pair_id"] for row in batch.annotator_a_rows} == {
        row["pair_id"] for row in batch.annotator_b_rows
    }
    assert [row["pair_id"] for row in batch.annotator_a_rows] != [
        row["pair_id"] for row in batch.annotator_b_rows
    ]
    forbidden = {
        "concept_label", "binding_hint", "role_hint", "generator",
        "legacy_expected_frames",
    }
    assert not forbidden.intersection(batch.annotator_a_rows[0])
    assert batch.annotator_a_rows[0]["reviewed_binding_label"] == ""
    assert batch.annotator_a_rows[0]["reviewed_role_label"] == ""


def test_blind_batch_fails_closed_when_a_source_slice_is_too_small() -> None:
    items = tuple(
        item for item in _items()
        if not (
            item.source_slice is AnnotationSourceSlice.SEC_10K
            and item.entity == "B"
        )
    )

    try:
        build_blind_annotation_batch(items, contexts_per_slice=3)
    except ValueError as exc:
        assert "SEC_10K" in str(exc)
    else:
        raise AssertionError("insufficient source slice must fail closed")
