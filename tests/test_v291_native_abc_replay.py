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
        "expected_frames": [],
        "actual_frames": [],
        "candidate_expected": 0,
        "candidate_hits": 0,
        "expected_quantities": (),
        "detected_quantities": (),
        "expected_concepts": (),
        "detected_concepts": (),
        "expected_bindings": (),
        "detected_bindings": (),
        "expected_roles": (),
        "detected_roles": (),
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

