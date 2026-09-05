from __future__ import annotations

import json

from equity_platform.text_ie.staged_evaluation import (
    summarize_route_aware_staged_validation,
)
from equity_platform.text_ie.training.staged_gold import load_staged_gold


def test_table_route_can_be_exhaustive_without_supported_kpi_nodes(tmp_path) -> None:
    row = {
        "example_id": "C-TABLE-NON-TARGET-001",
        "entity": "TEST",
        "holdout_axis": "C",
        "source_kind": "IR",
        "source_sha256": "a" * 64,
        "available_at": "2026-09-05",
        "document_period": "2026Q2",
        "text": "Maturity schedule 2026 100 2027 200",
        "gold_route": "TABLE_DSL",
        "quantities": [],
        "concepts": [],
        "candidate_edges": [],
        "binding_edges": [],
        "role_edges": [],
        "expected_frames": [],
        "annotation_source": "CODEX_MANUAL_RESEARCH_REVIEW",
    }
    path = tmp_path / "table-no-target.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    corpus = load_staged_gold(path)

    assert corpus[0].gold_route == "TABLE_DSL"
    assert corpus[0].concepts == ()


def test_route_aware_summary_excludes_table_bypass_from_text_graph_metrics() -> None:
    rows = [
        {
            "expected_frames": [
                {"concept": "CASH", "frame": "ABSOLUTE_VALUE", "value": 100.0}
            ],
            "actual_frames": [
                {"concept": "CASH", "frame": "ABSOLUTE_VALUE", "value": 100.0}
            ],
            "candidate_expected": 1,
            "candidate_hits": 0,
            "expected_quantities": [("MONEY", 100.0, 5, 9)],
            "detected_quantities": [],
            "expected_concepts": [("CASH", 0, 4)],
            "detected_concepts": [],
            "expected_bindings": [("CASH", 0, 4, "MONEY", 100.0, 5, 9)],
            "detected_bindings": [],
            "expected_roles": [
                ("CASH", 0, 4, "VALUE_CURRENT", "MONEY", 100.0, 5, 9)
            ],
            "detected_roles": [],
            "gold_route": "TABLE_DSL",
            "predicted_table": True,
            "rejection_count": 0,
            "review_count": 0,
        },
        {
            "expected_frames": [
                {"concept": "REVENUE", "frame": "ABSOLUTE_VALUE", "value": 50.0}
            ],
            "actual_frames": [
                {"concept": "REVENUE", "frame": "ABSOLUTE_VALUE", "value": 50.0}
            ],
            "candidate_expected": 1,
            "candidate_hits": 1,
            "expected_quantities": [("MONEY", 50.0, 8, 11)],
            "detected_quantities": [("MONEY", 50.0, 8, 11)],
            "expected_concepts": [("REVENUE", 0, 7)],
            "detected_concepts": [("REVENUE", 0, 7)],
            "expected_bindings": [("REVENUE", 0, 7, "MONEY", 50.0, 8, 11)],
            "detected_bindings": [("REVENUE", 0, 7, "MONEY", 50.0, 8, 11)],
            "expected_roles": [
                ("REVENUE", 0, 7, "VALUE_CURRENT", "MONEY", 50.0, 8, 11)
            ],
            "detected_roles": [
                ("REVENUE", 0, 7, "VALUE_CURRENT", "MONEY", 50.0, 8, 11)
            ],
            "gold_route": "TEXT_IE",
            "predicted_table": False,
            "rejection_count": 0,
            "review_count": 0,
        },
    ]

    summary = summarize_route_aware_staged_validation(rows)

    assert summary["candidate_recall"] == 1.0
    assert summary["binding_recall"] == 1.0
    assert summary["role_recall"] == 1.0
    assert summary["frame_recall"] == 1.0
    assert summary["table_frame_recall"] == 1.0
    assert summary["text_ie_frame_recall"] == 1.0
    assert summary["table_route_accuracy"] == 1.0

