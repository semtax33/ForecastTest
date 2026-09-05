from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from energy_nowcast.research.v352.validation import clean_component_promotion_gate
from equity_platform.validation.cross_section_metrics import ticker_scorecard, universe_summary


def _scorecard() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": [f"T{i:02d}" for i in range(14)],
        "observations": [8] * 12 + [3, 0],
        "mase": [0.7] * 12 + [1.1, np.nan],
        "improvement_log_points": [1.0] * 9 + [-1.0] * 4 + [np.nan],
        "candidate_mae_log_points": [5.0] * 13 + [np.nan],
        "pi_80_coverage": [0.8] * 13 + [np.nan],
        "directional_hit_rate": [0.75] * 13 + [np.nan],
    })


def _summary(score: pd.DataFrame) -> pd.Series:
    evaluable = score.dropna(subset=["mase"])
    return pd.Series({
        "evaluable_company_count": len(evaluable),
        "median_ticker_mase": float(evaluable["mase"].median()),
        "mean_ticker_mase": float(evaluable["mase"].mean()),
        "mase_below_1_count": int(evaluable["mase"].lt(1).sum()),
        "mase_below_1_share": float(evaluable["mase"].lt(1).mean()),
        "legacy_no_regression_share": float(evaluable["improvement_log_points"].ge(0).mean()),
        "median_improvement_log_points": float(evaluable["improvement_log_points"].median()),
        "mean_pi_80_coverage": 0.80,
    })


def test_gate_uses_same_evaluable_denominator_as_summary() -> None:
    score = _scorecard()
    summary = _summary(score)
    gate = clean_component_promotion_gate(
        score, score, summary, summary,
        ready_company_count=12, registered_company_count=14, live_matches=0,
    )
    detail = gate.loc[
        gate["condition"].eq("time_mase_below_1_share_at_least_70pct"), "detail"
    ].iloc[0]
    assert detail == "12/13 evaluable = 92.3%"


def test_gate_fails_closed_on_summary_denominator_mismatch() -> None:
    score = _scorecard()
    summary = _summary(score)
    summary["mase_below_1_share"] = 12 / 14
    with pytest.raises(AssertionError, match="denominator mismatch"):
        clean_component_promotion_gate(
            score, score, summary, _summary(score),
            ready_company_count=12, registered_company_count=14, live_matches=0,
        )


def test_wape_and_median_ape_are_not_mape() -> None:
    predictions = pd.DataFrame({
        "ticker": ["EOG", "EOG"],
        "actual_log_yoy": [1.0, 1.0],
        "legacy_prediction": [1.0, 1.0],
        "candidate_prediction": [1.0, 1.0],
        "revenue": [100.0, 1.0],
        "candidate_revenue": [90.0, 11.0],
        "candidate_revenue_ape_pct": [10.0, 1000.0],
        "small_denominator_flag": [False, True],
        "covered_80": [True, True],
        "direction_correct": [True, True],
    })
    score = ticker_scorecard(predictions, minimum_observations=2).iloc[0]
    assert np.isclose(score["revenue_wape_pct"], 20 / 101 * 100)
    assert score["revenue_median_ape_pct"] == 505.0
    assert score["revenue_mape_pct_diagnostic"] == 505.0
    assert score["small_denominator_observations"] == 1


def test_universe_summary_reports_explicit_numerators_and_denominators() -> None:
    predictions = pd.DataFrame({
        "ticker": ["A", "B"],
        "candidate_prediction": [1.0, 1.0],
        "candidate_revenue": [100.0, 100.0],
        "revenue": [100.0, 100.0],
        "candidate_revenue_ape_pct": [0.0, 0.0],
        "small_denominator_flag": [False, False],
    })
    score = pd.DataFrame({
        "ticker": ["A", "B", "C"],
        "mase": [0.5, 1.5, np.nan],
        "candidate_mae_log_points": [1.0, 2.0, np.nan],
        "improvement_log_points": [1.0, -1.0, np.nan],
        "pi_80_coverage": [0.8, 0.8, np.nan],
        "directional_hit_rate": [1.0, 0.0, np.nan],
    })
    summary = universe_summary(score, predictions, "TEST").iloc[0]
    assert summary["evaluable_company_count"] == 2
    assert summary["mase_below_1_count"] == 1
    assert summary["mase_below_1_share"] == 0.5
    assert summary["legacy_no_regression_count"] == 1
    assert summary["legacy_no_regression_share"] == 0.5
