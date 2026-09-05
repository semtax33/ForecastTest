from __future__ import annotations

import json

from equity_platform.text_ie.training.staged_gold import load_staged_gold
from scripts.architecture.v291_native_abc_replay import (
    ANNOTATIONS,
    _canonical_document,
    _grouped_summaries,
    verify_frozen_inputs,
)


def test_native_abc_replay_uses_exact_frozen_annotation_text() -> None:
    example = load_staged_gold(ANNOTATIONS)[0]

    document = _canonical_document(example)

    assert document.text == example.text
    assert len(document.sentences) == 1
    assert document.sentences[0].char_start == 0
    assert document.sentences[0].char_end == len(example.text)
    assert document.source.sha256 == example.source_sha256
    assert document.source.available_at == example.available_at


def test_native_abc_replay_verifies_pre_prediction_freezes() -> None:
    manifest = verify_frozen_inputs()

    assert manifest["annotation_snapshot"]["parser_predictions_generated_before_freeze"] is False
    assert manifest["pre_annotation_schema_bugfix"]["parser_inference_changed"] is False


def test_grouped_summary_preserves_axis_and_route_specific_rows() -> None:
    payload = {
        "expected_frames": [
            {"concept": "REVENUE", "frame": "ABSOLUTE_VALUE", "value": 50.0}
        ],
        "actual_frames": [
            {"concept": "REVENUE", "frame": "ABSOLUTE_VALUE", "value": 50.0}
        ],
        "candidate_expected": 1,
        "candidate_hits": 1,
        "expected_quantities": (("MONEY", 50.0, 8, 11),),
        "detected_quantities": (("MONEY", 50.0, 8, 11),),
        "expected_concepts": (("REVENUE", 0, 7),),
        "detected_concepts": (("REVENUE", 0, 7),),
        "expected_bindings": (("REVENUE", 0, 7, "MONEY", 50.0, 8, 11),),
        "detected_bindings": (("REVENUE", 0, 7, "MONEY", 50.0, 8, 11),),
        "expected_roles": (
            ("REVENUE", 0, 7, "VALUE_CURRENT", "MONEY", 50.0, 8, 11),
        ),
        "detected_roles": (
            ("REVENUE", 0, 7, "VALUE_CURRENT", "MONEY", 50.0, 8, 11),
        ),
        "rejection_count": 0,
        "review_count": 0,
        "observable_abstained_frames": 0,
        "gold_route": "NO_FACT",
        "predicted_table": False,
    }
    records = [
        {"axis": "A", "source_kind": "10-Q", "payload": json.dumps(payload)},
        {"axis": "C", "source_kind": "IR", "payload": json.dumps(payload)},
    ]

    summary = _grouped_summaries(records)

    assert {"ALL", "AXIS", "SOURCE_KIND"} <= set(summary["group_type"])
    assert {"A", "C"} <= set(summary.loc[summary["group_type"] == "AXIS", "group"])
    all_row = summary.loc[summary["group_type"] == "ALL"].iloc[0]
    assert all_row.quantity_recall == 1.0
    assert all_row.binding_precision == 1.0
