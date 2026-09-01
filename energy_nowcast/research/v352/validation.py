from __future__ import annotations

import numpy as np
import pandas as pd

from ...validation.cross_section_metrics import ticker_scorecard, universe_summary
from ..v35.strategy import KPIHierarchicalStrategy
from ..v35.validation import V35ValidationResult, run_loco, run_time_holdout


def _score_counts(scorecard: pd.DataFrame) -> dict[str, object]:
    evaluable = scorecard.dropna(subset=["mase"]).copy()
    return {
        "evaluable": evaluable,
        "evaluable_count": len(evaluable),
        "mase_below_1_count": int(evaluable["mase"].lt(1.0).sum()),
        "legacy_no_regression_count": int(
            evaluable["improvement_log_points"].ge(0.0).sum()
        ),
        "severe_regression_count": int(
            evaluable["improvement_log_points"].lt(-2.0).sum()
        ),
    }


def _assert_summary_consistency(scorecard: pd.DataFrame, summary: pd.Series) -> None:
    counts = _score_counts(scorecard)
    denominator = int(counts["evaluable_count"])
    if int(summary["evaluable_company_count"]) != denominator:
        raise AssertionError("Summary evaluable-company denominator differs from scorecard")
    if int(summary["mase_below_1_count"]) != int(counts["mase_below_1_count"]):
        raise AssertionError("Summary MASE<1 numerator differs from scorecard")
    expected_mase_share = float(counts["mase_below_1_count"]) / denominator if denominator else np.nan
    expected_legacy_share = float(counts["legacy_no_regression_count"]) / denominator if denominator else np.nan
    if not np.isclose(float(summary["mase_below_1_share"]), expected_mase_share):
        raise AssertionError("Summary MASE<1 share has a denominator mismatch")
    if not np.isclose(float(summary["legacy_no_regression_share"]), expected_legacy_share):
        raise AssertionError("Summary legacy share has a denominator mismatch")


def clean_component_promotion_gate(
    time_score: pd.DataFrame,
    loco_score: pd.DataFrame,
    time_summary: pd.Series,
    loco_summary: pd.Series,
    ready_company_count: int,
    registered_company_count: int,
    live_matches: int,
) -> pd.DataFrame:
    _assert_summary_consistency(time_score, time_summary)
    _assert_summary_consistency(loco_score, loco_summary)
    time_counts = _score_counts(time_score)
    loco_counts = _score_counts(loco_score)
    time_n = int(time_counts["evaluable_count"])
    loco_n = int(loco_counts["evaluable_count"])
    time_qualified = int(time_score["observations"].ge(8).sum())
    loco_qualified = int(loco_score["observations"].ge(8).sum())

    rows: list[tuple[str, str, bool, str]] = [
        ("shared", "standardized_kpi_coverage", ready_company_count >= 12, f"{ready_company_count}/{registered_company_count} registered"),
        ("shared", "minimum_8_time_forecasts", time_qualified >= 12, f"{time_qualified}/{registered_company_count} registered"),
        ("shared", "minimum_8_loco_forecasts", loco_qualified >= 12, f"{loco_qualified}/{registered_company_count} registered"),
        ("time_primary", "time_median_mase_below_0_80", float(time_summary["median_ticker_mase"]) < 0.80, str(time_summary["median_ticker_mase"])),
        ("time_primary", "time_mean_mase_below_0_90", float(time_summary["mean_ticker_mase"]) < 0.90, str(time_summary["mean_ticker_mase"])),
        ("time_primary", "time_mase_below_1_share_at_least_70pct", float(time_summary["mase_below_1_share"]) >= 0.70, f"{int(time_counts['mase_below_1_count'])}/{time_n} evaluable = {float(time_summary['mase_below_1_share']):.1%}"),
        ("time_primary", "time_median_improvement_positive", float(time_summary["median_improvement_log_points"]) > 0.0, str(time_summary["median_improvement_log_points"])),
        ("time_primary", "time_legacy_no_regression_at_least_70pct", float(time_summary["legacy_no_regression_share"]) >= 0.70, f"{int(time_counts['legacy_no_regression_count'])}/{time_n} evaluable = {float(time_summary['legacy_no_regression_share']):.1%}"),
        ("time_primary", "time_no_severe_ticker_regression", int(time_counts["severe_regression_count"]) == 0, f"{int(time_counts['severe_regression_count'])}/{time_n} below -2.0"),
        ("time_primary", "time_pi_80_coverage_between_75_85pct", 0.75 <= float(time_summary["mean_pi_80_coverage"]) <= 0.85, f"{float(time_summary['mean_pi_80_coverage']):.1%}"),
        ("loco_cold_start", "loco_median_mase_at_most_0_80", float(loco_summary["median_ticker_mase"]) <= 0.80, str(loco_summary["median_ticker_mase"])),
        ("loco_cold_start", "loco_mean_mase_at_most_0_90", float(loco_summary["mean_ticker_mase"]) <= 0.90, str(loco_summary["mean_ticker_mase"])),
        ("loco_cold_start", "loco_mase_below_1_share_at_least_70pct", float(loco_summary["mase_below_1_share"]) >= 0.70, f"{int(loco_counts['mase_below_1_count'])}/{loco_n} evaluable = {float(loco_summary['mase_below_1_share']):.1%}"),
    ]
    time_pass = all(passed for scope, _, passed, _ in rows if scope in {"shared", "time_primary"})
    loco_pass = all(passed for scope, _, passed, _ in rows if scope in {"shared", "loco_cold_start"})
    research_pass = time_pass and loco_pass
    rows.extend([
        ("unlock", "company_basis_overlay", False, "Disabled by default; requires a separate ticker-level nested walk-forward promotion"),
        ("unlock", "macro_overlay_unlock", research_pass, "Requires both primary time and cold-start gates"),
        ("production", "live_20_match_model_change_lock", live_matches >= 20, f"{live_matches}/20 matched"),
    ])
    result = pd.DataFrame(rows, columns=["scope", "condition", "passed", "detail"])
    result["time_primary_gate"] = time_pass
    result["loco_cold_start_gate"] = loco_pass
    result["research_component_gate"] = research_pass
    result["macro_overlay_enabled"] = research_pass
    result["champion_promotion"] = research_pass and live_matches >= 20
    return result


def validate_v352(
    strategy: KPIHierarchicalStrategy,
    panel: pd.DataFrame,
    ready_company_count: int,
    registered_company_count: int = 14,
    live_matches: int = 0,
) -> V35ValidationResult:
    time_predictions, history = run_time_holdout(strategy, panel, holdout_quarters=8)
    loco_predictions = run_loco(strategy, panel, history, holdout_quarters=8)
    time_score = ticker_scorecard(time_predictions, minimum_observations=8)
    loco_score = ticker_scorecard(loco_predictions, minimum_observations=8)
    summaries = pd.concat([
        universe_summary(time_score, time_predictions, "TIME_HOLDOUT_8Q_PRIMARY"),
        universe_summary(loco_score, loco_predictions, "LOCO_TIME_SAFE_8Q_COLD_START"),
    ], ignore_index=True)
    gate = clean_component_promotion_gate(
        time_score,
        loco_score,
        summaries.iloc[0],
        summaries.iloc[1],
        ready_company_count,
        registered_company_count,
        live_matches,
    )
    promotion = bool(gate["champion_promotion"].iloc[0])
    time_score["promoted"] = time_score["company_gate_pass"] & promotion
    loco_score["promoted"] = loco_score["company_gate_pass"] & promotion
    return V35ValidationResult(
        time_predictions, loco_predictions, time_score, loco_score, summaries, gate
    )
