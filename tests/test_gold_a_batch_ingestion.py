from __future__ import annotations

import csv
from pathlib import Path

import pytest

from equity_platform.text_ie.training import (
    AdjudicationStatus,
    AnnotationQualityTier,
    AnnotationReviewItem,
    AnnotationSourceSlice,
    PairProposal,
    TextSpan,
    ingest_gold_a_batch,
    write_annotation_review_queue,
)


SLICES = (
    AnnotationSourceSlice.SEC_10K,
    AnnotationSourceSlice.SEC_10Q,
    AnnotationSourceSlice.IR_PREPARED_REMARKS,
    AnnotationSourceSlice.IR_QA,
)


def _queue_item(source_slice: AnnotationSourceSlice, ordinal: int) -> AnnotationReviewItem:
    text = "Revenue was $10 million."
    return AnnotationReviewItem(
        schema_version="1.0.0",
        queue_item_id=f"pair-{ordinal}",
        candidate_id=f"context-{ordinal}",
        entity=f"ENTITY-{ordinal}",
        source_path=f"D:/source-{ordinal}.htm",
        source_sha256=f"{ordinal + 1:064x}",
        source_slice=source_slice,
        document_char_start=0,
        document_char_end=len(text),
        text=text,
        proposal=PairProposal(
            metric_span=TextSpan(0, 7, "Revenue"),
            quantity_span=TextSpan(12, 23, "$10 million"),
            concept_label="REVENUE",
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


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_completed_batch(tmp_path: Path) -> tuple[Path, Path]:
    items = tuple(_queue_item(source_slice, index) for index, source_slice in enumerate(SLICES))
    queue_path = tmp_path / "queue.jsonl"
    write_annotation_review_queue(queue_path, items)
    pair_rows = []
    context_rows = []
    adjudication_rows = []
    for item in items:
        proposal = item.proposal
        base = {
            "annotation_channel": "A",
            "pair_id": item.queue_item_id,
            "context_id": item.candidate_id,
            "source_slice": item.source_slice.value,
            "entity": item.entity,
            "source_sha256": item.source_sha256,
            "source_path": item.source_path,
            "document_char_start": item.document_char_start,
            "document_char_end": item.document_char_end,
            "text": item.text,
            "metric_candidate_start": proposal.metric_span.char_start,
            "metric_candidate_end": proposal.metric_span.char_end,
            "metric_candidate_literal": proposal.metric_span.literal,
            "quantity_candidate_start": proposal.quantity_span.char_start,
            "quantity_candidate_end": proposal.quantity_span.char_end,
            "quantity_candidate_literal": proposal.quantity_span.literal,
            "quantity_candidate_kind": proposal.quantity_kind,
            "reviewed_metric_start": 0,
            "reviewed_metric_end": 7,
            "reviewed_metric_literal": "Revenue",
            "reviewed_quantity_start": 12,
            "reviewed_quantity_end": 23,
            "reviewed_quantity_literal": "$10 million",
            "reviewed_concept_label": "REVENUE",
            "reviewed_binding_label": "BELONGS_TO",
            "reviewed_role_label": "VALUE_CURRENT",
            "reviewed_scope": "CONSOLIDATED",
            "reviewed_period": "FY2025",
            "reviewed_quantity_kind": "MONEY",
            "annotator_id": "annotator-a",
            "notes": "",
        }
        pair_rows.append(base)
        context_rows.append({
            "annotation_channel": "A",
            "context_id": item.candidate_id,
            "source_slice": item.source_slice.value,
            "entity": item.entity,
            "source_sha256": item.source_sha256,
            "source_path": item.source_path,
            "document_char_start": item.document_char_start,
            "document_char_end": item.document_char_end,
            "text": item.text,
            "candidate_pair_count": 1,
            "candidate_graph_complete": "YES",
            "missing_metric_mentions": "",
            "missing_quantity_mentions": "",
            "missing_pairs": "",
            "annotator_id": "annotator-a",
            "notes": "",
        })
        adjudication_rows.append({
            "pair_id": item.queue_item_id,
            "context_id": item.candidate_id,
            "source_slice": item.source_slice.value,
            "entity": item.entity,
            "source_sha256": item.source_sha256,
            "source_path": item.source_path,
            "text": item.text,
            "metric_candidate_start": 0,
            "metric_candidate_end": 7,
            "metric_candidate_literal": "Revenue",
            "quantity_candidate_start": 12,
            "quantity_candidate_end": 23,
            "quantity_candidate_literal": "$10 million",
            "quantity_candidate_kind": "MONEY",
            **{
                f"annotator_{channel}_{field}": value
                for channel, annotator in (("a", "annotator-a"), ("b", "annotator-b"))
                for field, value in {
                    "id": annotator,
                    "metric_start": 0,
                    "metric_end": 7,
                    "metric_literal": "Revenue",
                    "quantity_start": 12,
                    "quantity_end": 23,
                    "quantity_literal": "$10 million",
                    "concept_label": "REVENUE",
                    "binding_label": "BELONGS_TO",
                    "role_label": "VALUE_CURRENT",
                    "scope": "CONSOLIDATED",
                    "period": "FY2025",
                    "quantity_kind": "MONEY",
                    "notes": "",
                }.items()
            },
            "agreement_status": "AGREED",
            "adjudicator_id": "adjudicator-c",
            "final_metric_start": 0,
            "final_metric_end": 7,
            "final_metric_literal": "Revenue",
            "final_quantity_start": 12,
            "final_quantity_end": 23,
            "final_quantity_literal": "$10 million",
            "final_concept_label": "REVENUE",
            "final_binding_label": "BELONGS_TO",
            "final_role_label": "VALUE_CURRENT",
            "final_scope": "CONSOLIDATED",
            "final_period": "FY2025",
            "final_quantity_kind": "MONEY",
            "adjudication_notes": "",
        })
    _write_csv(tmp_path / "annotator_a_pairs.csv", pair_rows)
    _write_csv(
        tmp_path / "annotator_b_pairs.csv",
        [{**row, "annotation_channel": "B", "annotator_id": "annotator-b"} for row in pair_rows],
    )
    _write_csv(tmp_path / "annotator_a_context_audit.csv", context_rows)
    _write_csv(
        tmp_path / "annotator_b_context_audit.csv",
        [{**row, "annotation_channel": "B", "annotator_id": "annotator-b"} for row in context_rows],
    )
    _write_csv(tmp_path / "adjudication_template.csv", adjudication_rows)
    return tmp_path, queue_path


def test_completed_batch_becomes_double_adjudicated_gold_a(tmp_path) -> None:
    batch_root, queue_path = _write_completed_batch(tmp_path)

    result = ingest_gold_a_batch(
        batch_root=batch_root,
        review_queue_path=queue_path,
        required_contexts_per_slice=1,
    )

    assert len(result.items) == 4
    assert all(item.quality_tier is AnnotationQualityTier.GOLD_A for item in result.items)
    assert all(item.adjudication_status is AdjudicationStatus.ADJUDICATED for item in result.items)
    assert all(len(item.human_annotations) == 2 for item in result.items)
    assert result.context_counts == {source_slice.value: 1 for source_slice in SLICES}


def test_ingestion_rejects_modified_adjudication_source_identity(tmp_path) -> None:
    batch_root, queue_path = _write_completed_batch(tmp_path)
    path = batch_root / "adjudication_template.csv"
    rows = _read_csv(path)
    rows[0]["source_sha256"] = "f" * 64
    _write_csv(path, rows)

    with pytest.raises(ValueError, match="immutable adjudication field changed: source_sha256"):
        ingest_gold_a_batch(
            batch_root=batch_root,
            review_queue_path=queue_path,
            required_contexts_per_slice=1,
        )


def test_incomplete_candidate_graph_is_quarantined_not_promoted(tmp_path) -> None:
    batch_root, queue_path = _write_completed_batch(tmp_path)
    excluded_context = "context-0"
    for name in ("annotator_a_context_audit.csv", "annotator_b_context_audit.csv"):
        path = batch_root / name
        rows = _read_csv(path)
        for row in rows:
            if row["context_id"] == excluded_context:
                row["candidate_graph_complete"] = "FALSE"
                row["missing_metric_mentions"] = "margin@0"
                row["missing_pairs"] = "margin@0 <-> $10 million@12"
        _write_csv(path, rows)

    result = ingest_gold_a_batch(
        batch_root=batch_root,
        review_queue_path=queue_path,
        required_contexts_per_slice=0,
    )

    assert {item.candidate_id for item in result.items} == {
        "context-1", "context-2", "context-3"
    }
    assert result.excluded_context_counts == {"SEC_10K": 1}
    assert len(result.quarantined_items) == 1
    assert result.quarantined_items[0].candidate_id == excluded_context
    assert result.quarantined_items[0].quality_tier is AnnotationQualityTier.GOLD_B
    assert not result.quarantined_items[0].certification_eligible
