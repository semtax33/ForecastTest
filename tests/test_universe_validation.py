import numpy as np
import pandas as pd

from equity_platform.validation.cross_section_metrics import ticker_scorecard, universe_summary
from equity_platform.validation.promotion_gate import (
    seven_condition_promotion_gate,
    universe_promotion_gate,
)
from energy_nowcast.validation.universe_backtest import UniverseBacktester


def _synthetic_panel() -> pd.DataFrame:
    rows = []
    for ticker_index, ticker in enumerate(("AAA", "BBB", "CCC")):
        for quarter in range(12):
            wti = float(quarter - 5)
            henry = float((quarter % 4) - 1)
            propane = float(quarter / 2)
            lag_revenue = float(quarter + ticker_index)
            lag_basis = float(ticker_index - quarter / 10)
            actual = 0.6 * wti + 0.3 * henry + 0.2 * propane + 0.1 * lag_revenue + 0.4 * lag_basis
            rows.append({
                "ticker": ticker,
                "quarter": f"202{quarter // 4}Q{quarter % 4 + 1}",
                "quarter_ordinal": quarter,
                "actual_log_yoy": actual,
                "revenue": 100.0 * np.exp(actual / 100.0),
                "prior_year_revenue": 100.0,
                "forecast_cutoff_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=quarter),
                "lag_report_date": pd.Timestamp("2025-12-01") + pd.Timedelta(days=quarter),
                "wti_log_yoy": wti,
                "henry_log_yoy": henry,
                "propane_log_yoy": propane,
                "lag_revenue_log_yoy": lag_revenue,
                "lag_implied_volume_basis_log_yoy": lag_basis,
            })
    return pd.DataFrame(rows)


def test_loco_predictions_do_not_use_heldout_company_labels():
    panel = _synthetic_panel()
    backtester = UniverseBacktester(alpha=1.0, test_quarters=2, minimum_train_rows=5)
    original = backtester.run_loco(panel)
    changed = panel.copy()
    changed.loc[changed["ticker"].eq("AAA"), "actual_log_yoy"] += 10_000.0
    perturbed = backtester.run_loco(changed)
    original_aaa = original.loc[original["ticker"].eq("AAA"), "candidate_prediction"].to_numpy()
    perturbed_aaa = perturbed.loc[perturbed["ticker"].eq("AAA"), "candidate_prediction"].to_numpy()
    assert np.allclose(original_aaa, perturbed_aaa)
    assert len(original) == 6


def test_cross_section_outputs_required_counts_and_promotion_lock():
    backtester = UniverseBacktester(alpha=1.0, test_quarters=2, minimum_train_rows=5)
    predictions = backtester.run_time_holdout(_synthetic_panel())
    score = ticker_scorecard(predictions, minimum_observations=2)
    summary = universe_summary(score, predictions, "TIME_HOLDOUT")
    assert summary.loc[0, "company_count"] == 3
    assert summary.loc[0, "quarter_forecasts"] == 6
    assert {"mase_below_1_count", "beats_naive_pct", "beats_legacy_pct"}.issubset(summary.columns)

    consensus = {"matched_observations": 19, "model_mae": 1.0, "consensus_mae": 2.0}
    gate = seven_condition_promotion_gate(
        {"mase": 1.0, "revenue_mape_pct": 10.0},
        {"mase": 0.9, "revenue_mape_pct": 9.0, "observations": 30, "untouched_not_worse": True, "pi_80_coverage": 0.8},
        score.assign(improvement_log_points=1.0),
        consensus,
    )
    assert gate["passed"].all()
    assert not gate["promotion_eligible"].any()
    assert gate["model_change_lock"].eq("LOCKED").all()


def test_universe_gate_requires_live_forward_and_loco_pass():
    score = pd.DataFrame({
        "improvement_log_points": [1.0, 1.0, -1.0, 1.0],
        "company_gate_pass": [True, True, False, True],
    })
    gate = universe_promotion_gate(score, score, live_forward_not_worse=None)
    assert not gate["universe_promotion"].any()
    assert not bool(gate.loc[gate["condition"].eq("live_forward_not_worse"), "passed"].iloc[0])
