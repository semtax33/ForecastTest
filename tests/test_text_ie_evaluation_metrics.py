from __future__ import annotations

from equity_platform.text_ie.evaluation import count_semantic_duplicate_frames


def test_opposite_polarities_are_distinct_semantic_frames() -> None:
    payloads = [[
        {
            "concept": "REVENUE",
            "frame": "CHANGE_BY",
            "value": 7.0,
            "change": None,
            "lower_value": None,
            "upper_value": None,
            "polarity": "POSITIVE",
        },
        {
            "concept": "REVENUE",
            "frame": "CHANGE_BY",
            "value": 7.0,
            "change": None,
            "lower_value": None,
            "upper_value": None,
            "polarity": "NEGATIVE",
        },
    ]]
    assert count_semantic_duplicate_frames(payloads) == 0


def test_identical_semantic_frames_are_counted_as_duplicates() -> None:
    frame = {
        "concept": "REVENUE",
        "frame": "CHANGE_BY",
        "value": 7.0,
        "change": None,
        "lower_value": None,
        "upper_value": None,
        "polarity": "POSITIVE",
    }
    assert count_semantic_duplicate_frames([[frame, dict(frame)]]) == 1
