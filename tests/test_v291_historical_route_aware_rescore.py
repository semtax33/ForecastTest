from __future__ import annotations

from scripts.architecture.v291_rescore_parser_history import (
    _summarize_historical_rows,
)


def test_historical_rescore_does_not_grade_table_bypass_as_text_frame_miss() -> None:
    summary = _summarize_historical_rows(
        [
            {
                "expected_frames": [
                    {"concept": "CASH", "frame": "ABSOLUTE_VALUE", "value": 100.0}
                ],
                "actual_frames": [],
                "candidate_hits": 0,
                "detected_quantities": [],
                "rejection_count": 0,
                "review_count": 0,
                "gold_route": "TABLE_DSL",
                "predicted_table": True,
            }
        ]
    )

    assert summary["evaluated_frame_opportunities"] == 0
    assert summary["table_expected_frames_not_evaluated"] == 1
    assert summary["silent_frame_miss"] == 0

