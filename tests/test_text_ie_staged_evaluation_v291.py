from __future__ import annotations

import tomllib
from pathlib import Path

from equity_platform.text_ie.staged_evaluation import (
    DEFAULT_STAGED_GATES,
    frame_concepts,
    frame_owner_bindings,
    frame_quantity_roles,
    explicit_quantity_values,
    score_stage,
    summarize_staged_validation,
)
from scripts.architecture.v291_rescore_parser_history import (
    _axis,
    _detector,
    _historical_status,
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, **extra}


def test_staged_signatures_separate_concept_binding_role_and_reduction() -> None:
    expected = _frame("REVENUE", "CHANGE_TO", 1_200_000_000.0, change=200_000_000.0)
    swapped = _frame("REVENUE", "CHANGE_TO", 200_000_000.0, change=1_200_000_000.0)

    assert frame_concepts(expected) == ("REVENUE",)
    assert frame_concepts(swapped) == ("REVENUE",)
    assert frame_owner_bindings(expected) == frame_owner_bindings(swapped)
    assert frame_quantity_roles(expected) != frame_quantity_roles(swapped)


def test_range_midpoint_is_derived_not_a_detected_or_bound_quantity() -> None:
    guidance = _frame(
        "REVENUE_GUIDANCE",
        "RANGE_GUIDANCE",
        150.0,
        lower_value=100.0,
        upper_value=200.0,
    )
    assert explicit_quantity_values(guidance) == (100.0, 200.0)
    assert frame_owner_bindings(guidance) == (
        ("REVENUE", 100.0),
        ("REVENUE", 200.0),
    )
    assert frame_quantity_roles(guidance) == (
        ("REVENUE", "GUIDANCE_LOW", 100.0),
        ("REVENUE", "GUIDANCE_HIGH", 200.0),
    )


def test_score_stage_preserves_duplicate_opportunities() -> None:
    counts = score_stage((1.0, 1.0, 2.0), (1.0, 2.0, 2.0))
    assert counts.true_positive == 2
    assert counts.false_positive == 1
    assert counts.false_negative == 1
    assert counts.precision == 2 / 3
    assert counts.recall == 2 / 3


def test_staged_summary_rewards_observable_abstention_not_silent_miss() -> None:
    expected = [_frame("REVENUE", "ABSOLUTE_VALUE", 100.0)]
    rows = [
        {
            "expected_frames": expected,
            "actual_frames": [],
            "candidate_hits": 1,
            "detected_quantities": [100.0],
            "rejection_count": 1,
            "review_count": 0,
            "gold_route": "TEXT_IE",
            "predicted_table": False,
        },
        {
            "expected_frames": expected,
            "actual_frames": [],
            "candidate_hits": 1,
            "detected_quantities": [100.0],
            "rejection_count": 0,
            "review_count": 0,
            "gold_route": "TEXT_IE",
            "predicted_table": False,
        },
    ]
    summary = summarize_staged_validation(rows)
    assert summary["frame_false_negative"] == 2
    assert summary["observable_abstained_frames"] == 1
    assert summary["silent_frame_miss"] == 1
    assert summary["abstention_coverage"] == 0.5


def test_staged_summary_uses_accepted_precision_and_separate_coverage() -> None:
    expected = [_frame("REVENUE", "CHANGE_TO", 120.0, change=20.0)]
    actual = [_frame("REVENUE", "CHANGE_TO", 20.0, change=120.0)]
    summary = summarize_staged_validation(
        [{
            "expected_frames": expected,
            "actual_frames": actual,
            "candidate_hits": 1,
            "detected_quantities": [20.0, 120.0],
            "rejection_count": 0,
            "review_count": 0,
            "gold_route": "TEXT_IE",
            "predicted_table": False,
        }]
    )
    assert summary["quantity_recall"] == 1.0
    assert summary["concept_precision"] == 1.0
    assert summary["binding_precision"] == 1.0
    assert summary["role_precision"] == 0.0
    assert summary["frame_precision"] == 0.0


def test_staged_summary_never_matches_quantities_across_blocks() -> None:
    expected = [_frame("REVENUE", "ABSOLUTE_VALUE", 100.0)]
    rows = [
        {
            "expected_frames": expected,
            "actual_frames": [],
            "candidate_hits": 0,
            "detected_quantities": [],
            "rejection_count": 0,
            "review_count": 0,
            "gold_route": "TEXT_IE",
            "predicted_table": False,
        },
        {
            "expected_frames": [],
            "actual_frames": [_frame("REVENUE", "ABSOLUTE_VALUE", 100.0)],
            "candidate_hits": 0,
            "detected_quantities": [100.0],
            "rejection_count": 0,
            "review_count": 0,
            "gold_route": "NO_FACT",
            "predicted_table": False,
        },
    ]
    summary = summarize_staged_validation(rows)
    assert summary["quantity_true_positive"] == 0
    assert summary["quantity_false_positive"] == 1
    assert summary["quantity_false_negative"] == 1
    assert summary["concept_true_positive"] == 0


def test_historical_rescore_uses_inherited_detector_without_alias_patch() -> None:
    assert _detector(277).__name__ == "semantic_quantities_v276"


def test_certification_config_and_runtime_gate_defaults_are_identical() -> None:
    config = Path("configs/certification/platform_v291_staged_validation.toml")
    with config.open("rb") as stream:
        criteria = tomllib.load(stream)
    configured = criteria["gates"]
    assert configured == DEFAULT_STAGED_GATES
    assert criteria["native_stage_gold_required_for_certification"] is True
    assert criteria["native_pre_reducer_role_telemetry_required_for_certification"] is True
    assert criteria["post_disclosure_diagnostic_replay_is_certification_eligible"] is False


def test_legacy_holdout_is_not_retroactively_claimed_as_native_abc_axis() -> None:
    assert _axis(Path("twenty_fifth_c_holdout_evaluation.csv")) == (
        "LEGACY_HOLDOUT_NOT_NATIVE_ABC"
    )


def test_historical_numeric_pass_is_never_labeled_certification_pass() -> None:
    assert _historical_status(True) == (
        "HISTORICAL_PROXY_NUMERIC_PASS_NOT_CERTIFICATION_ELIGIBLE"
    )
    assert _historical_status(False) == "HISTORICAL_PROXY_HOLD"


def test_native_role_telemetry_is_scored_separately_from_bad_reducer_output() -> None:
    expected = _frame("REVENUE", "CHANGE_TO", 120.0, change=20.0)
    bad_reduction = _frame("REVENUE", "CHANGE_TO", 20.0, change=120.0)

    summary = summarize_staged_validation(
        [{
            "expected_frames": [expected],
            "actual_frames": [bad_reduction],
            "candidate_hits": 1,
            "detected_quantities": [120.0, 20.0],
            "detected_concepts": ["REVENUE"],
            "detected_bindings": [("REVENUE", 120.0), ("REVENUE", 20.0)],
            "detected_roles": [
                ("REVENUE", "VALUE_CURRENT", 120.0),
                ("REVENUE", "DELTA", 20.0),
            ],
            "rejection_count": 0,
            "review_count": 0,
            "gold_route": "TEXT_IE",
            "predicted_table": False,
        }]
    )

    assert summary["role_precision"] == 1.0
    assert summary["role_recall"] == 1.0
    assert summary["frame_precision"] == 0.0


def test_native_frame_level_abstention_does_not_cover_unrelated_miss() -> None:
    summary = summarize_staged_validation(
        [{
            "expected_frames": [
                _frame("REVENUE", "ABSOLUTE_VALUE", 100.0),
                _frame("CASH", "ABSOLUTE_VALUE", 50.0),
            ],
            "actual_frames": [_frame("REVENUE", "ABSOLUTE_VALUE", 100.0)],
            "candidate_hits": 2,
            "detected_quantities": [100.0, 50.0],
            "rejection_count": 1,
            "review_count": 0,
            "observable_abstained_frames": 0,
            "gold_route": "TEXT_IE",
            "predicted_table": False,
        }]
    )

    assert summary["frame_false_negative"] == 1
    assert summary["observable_abstained_frames"] == 0
    assert summary["silent_frame_miss"] == 1


def test_native_stage_gold_scores_explicit_graph_instead_of_frame_proxy() -> None:
    revenue = _frame("REVENUE", "ABSOLUTE_VALUE", 100.0)
    summary = summarize_staged_validation(
        [{
            "expected_frames": [revenue],
            "actual_frames": [revenue],
            "candidate_expected": 2,
            "candidate_hits": 2,
            "expected_quantities": [
                ("MONEY", 100.0, 12, 16),
                ("PERCENT", 20.0, 30, 33),
            ],
            "detected_quantities": [
                ("MONEY", 100.0, 12, 16),
                ("PERCENT", 20.0, 30, 33),
            ],
            "expected_concepts": [
                ("REVENUE", 0, 7),
                ("OPERATING_MARGIN", 18, 27),
            ],
            "detected_concepts": [
                ("REVENUE", 0, 7),
                ("OPERATING_MARGIN", 18, 27),
            ],
            "expected_bindings": [
                ("REVENUE", 0, 7, "MONEY", 100.0, 12, 16),
                ("OPERATING_MARGIN", 18, 27, "PERCENT", 20.0, 30, 33),
            ],
            "detected_bindings": [
                ("REVENUE", 0, 7, "MONEY", 100.0, 12, 16),
                ("OPERATING_MARGIN", 18, 27, "PERCENT", 20.0, 30, 33),
            ],
            "expected_roles": [
                ("REVENUE", 0, 7, "VALUE_CURRENT", "MONEY", 100.0, 12, 16),
                ("OPERATING_MARGIN", 18, 27, "VALUE_CURRENT", "PERCENT", 20.0, 30, 33),
            ],
            "detected_roles": [
                ("REVENUE", 0, 7, "VALUE_CURRENT", "MONEY", 100.0, 12, 16),
                ("OPERATING_MARGIN", 18, 27, "VALUE_CURRENT", "PERCENT", 20.0, 30, 33),
            ],
            "rejection_count": 0,
            "review_count": 0,
            "gold_route": "TEXT_IE",
            "predicted_table": False,
        }]
    )

    assert summary["expected_candidates"] == 2
    assert summary["candidate_recall"] == 1.0
    assert summary["quantity_precision"] == 1.0
    assert summary["concept_precision"] == 1.0
    assert summary["binding_precision"] == 1.0
    assert summary["role_precision"] == 1.0
