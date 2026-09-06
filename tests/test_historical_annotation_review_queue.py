from __future__ import annotations

import csv
import json

from equity_platform.text_ie.training import (
    AnnotationSourceSlice,
    build_historical_review_queue,
)


def _write_candidates(path) -> None:
    fields = [
        "candidate_id",
        "ticker",
        "source_path",
        "source_sha256",
        "char_start",
        "char_end",
        "text",
    ]
    text = "Revenue was $10 million and adjusted EBITDA was $3 million."
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({
            "candidate_id": "candidate-1",
            "ticker": "TEST",
            "source_path": "D:/Arcana/data-lake/bronze/sec/fillings/ir/TEST/release.htm",
            "source_sha256": "a" * 64,
            "char_start": 100,
            "char_end": 100 + len(text),
            "text": text,
        })


def _write_annotation(path, revenue_value: float) -> None:
    row = {
        "candidate_id": "candidate-1",
        "ticker": "TEST",
        "gold_route": "TEXT_IE",
        "expected_frames": [
            {
                "concept": "REVENUE",
                "frame": "ABSOLUTE_VALUE",
                "value": revenue_value,
                "tier": "CRITICAL",
            },
            {
                "concept": "ADJUSTED_EBITDA",
                "frame": "ABSOLUTE_VALUE",
                "value": 3_000_000.0,
                "tier": "CRITICAL",
            },
        ],
        "annotation_note": "legacy review",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_review_queue_recovers_full_local_pair_cross_product_and_latest_lineage(tmp_path) -> None:
    candidates = tmp_path / "holdout_candidates.csv"
    older = tmp_path / "v280_holdout_annotations.jsonl"
    corrected = tmp_path / "v281_corrected_annotations.jsonl"
    _write_candidates(candidates)
    _write_annotation(older, 9_000_000.0)
    _write_annotation(corrected, 10_000_000.0)

    queue = build_historical_review_queue(
        candidate_csvs=(candidates,),
        annotation_files=(older, corrected),
    )

    assert queue.unique_candidate_count == 1
    assert queue.superseded_annotation_rows == 1
    assert queue.missing_candidate_ids == ()
    assert queue.selected_expected_frames == 2
    assert queue.matched_expected_frames == 2
    assert queue.unmatched_expected_frames == 0
    assert len(queue.items) == 4
    assert all(item.source_slice is AnnotationSourceSlice.IR_UNSPECIFIED for item in queue.items)
    assert all(item.legacy_annotation_files == (older.name, corrected.name) for item in queue.items)
    pairs = {
        (
            item.proposal.metric_span.literal,
            item.proposal.quantity_span.literal,
        ): (item.proposal.binding_hint, item.proposal.role_hint)
        for item in queue.items
    }
    assert pairs == {
        ("Revenue", "$10 million"): ("BELONGS_TO", "VALUE_CURRENT"),
        ("Revenue", "$3 million"): ("NOT_RELATED", None),
        ("adjusted EBITDA", "$10 million"): ("NOT_RELATED", None),
        ("adjusted EBITDA", "$3 million"): ("BELONGS_TO", "VALUE_CURRENT"),
    }


def test_table_route_is_archived_outside_the_narrative_pair_queue(tmp_path) -> None:
    candidates = tmp_path / "holdout_candidates.csv"
    text = "Revenue 2026 2025 100 90"
    with candidates.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "candidate_id",
                "ticker",
                "source_path",
                "source_sha256",
                "char_start",
                "char_end",
                "text",
            ),
        )
        writer.writeheader()
        writer.writerow({
            "candidate_id": "table-1",
            "ticker": "TEST",
            "source_path": "D:/Arcana/data-lake/bronze/sec/fillings/10-k/TEST.htm",
            "source_sha256": "b" * 64,
            "char_start": 0,
            "char_end": len(text),
            "text": text,
        })
    annotation = tmp_path / "v290_annotations.jsonl"
    annotation.write_text(json.dumps({
        "candidate_id": "table-1",
        "ticker": "TEST",
        "gold_route": "TABLE_DSL",
        "expected_frames": [],
        "annotation_note": "positional table",
    }) + "\n", encoding="utf-8")

    queue = build_historical_review_queue(
        candidate_csvs=(candidates,),
        annotation_files=(annotation,),
    )

    assert len(queue.items) == 1
    assert queue.items[0].proposal is None
    assert queue.items[0].adjudication_status == "ARCHIVE_ONLY"
    assert queue.archived_table_contexts == 1
