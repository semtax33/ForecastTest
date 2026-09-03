from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import numpy as np
import pandas as pd

from ...validation.cross_section_metrics import ticker_scorecard, universe_summary
from ...validation.universe_backtest import LEGACY_FEATURES, PooledRidge
from equity_platform.sectors.energy.research.revenue.v35.strategy import KPIHierarchicalStrategy
from equity_platform.sectors.energy.research.revenue.v35.taxonomy import E_AND_P_GROUPS, group_for_ticker
from equity_platform.sectors.energy.research.revenue.v35.validation import run_loco, run_time_holdout


@dataclass(frozen=True)
class V353GroupedValidationResult:
    time_predictions: pd.DataFrame
    loco_predictions: pd.DataFrame
    time_scorecard: pd.DataFrame
    loco_scorecard: pd.DataFrame
    universe_summary: pd.DataFrame
    clean_time_scorecard: pd.DataFrame
    clean_loco_scorecard: pd.DataFrame
    group_promotion: pd.DataFrame
    grouped_success_gate: pd.DataFrame
    candidate_history: pd.DataFrame


def _rolling_legacy_history(
    panel: pd.DataFrame,
    candidate_history: pd.DataFrame,
    excluded_ticker: str | None,
    alpha: float = 8.0,
) -> pd.DataFrame:
    """Replace gas rows with time-safe legacy forecasts for PI calibration."""
    history = candidate_history.copy()
    model = PooledRidge(alpha)
    panel_lookup = panel.set_index(["ticker", "quarter"], drop=False)
    for index, row in history.iterrows():
        ticker = str(row["ticker"])
        if group_for_ticker(ticker) != "gas_heavy":
            continue
        target = panel_lookup.loc[(ticker, str(row["quarter"]))]
        if isinstance(target, pd.DataFrame):
            target = target.iloc[-1]
        train = panel.loc[panel["quarter_ordinal"].lt(int(row["quarter_ordinal"]))]
        if excluded_ticker is not None:
            train = train.loc[train["ticker"].ne(excluded_ticker)]
        if train.empty:
            history.loc[index, "candidate_prediction"] = np.nan
            continue
        history.loc[index, "candidate_prediction"] = float(
            model.predict(train, target.to_frame().T, LEGACY_FEATURES)[0]
        )
    history["residual"] = history["actual_log_yoy"] - history["candidate_prediction"]
    return history


def _selected_history(
    panel: pd.DataFrame,
    candidate_history: pd.DataFrame,
    excluded_ticker: str | None,
) -> pd.DataFrame:
    result = _rolling_legacy_history(panel, candidate_history, excluded_ticker)
    if excluded_ticker is not None:
        result = result.loc[result["ticker"].ne(excluded_ticker)]
    return result


def _recalculate_intervals(
    row: pd.Series,
    history: pd.DataFrame,
) -> dict[str, object]:
    group = group_for_ticker(str(row["ticker"]))
    prior = history.loc[
        history["quarter_ordinal"].lt(int(row["quarter_ordinal"]))
        & history["ticker"].map(group_for_ticker).eq(group),
        "residual",
    ].dropna().abs()
    values: dict[str, object] = {"calibration_observations": len(prior)}
    prediction = float(row["candidate_prediction"])
    actual = float(row["actual_log_yoy"])
    for level in (0.80, 0.95):
        label = int(level * 100)
        radius = float(prior.quantile(level)) if len(prior) >= 20 else np.nan
        values[f"lower_{label}_log_yoy"] = prediction - radius
        values[f"upper_{label}_log_yoy"] = prediction + radius
        values[f"covered_{label}"] = (
            bool(prediction - radius <= actual <= prediction + radius)
            if np.isfinite(radius)
            else np.nan
        )
    return values


def apply_group_selection(
    predictions: pd.DataFrame,
    panel: pd.DataFrame,
    candidate_history: pd.DataFrame,
    active_models: dict[str, str],
    validation: str,
) -> pd.DataFrame:
    """Apply group-specific champion selection without changing test keys."""
    result = predictions.copy()
    result["group"] = result["ticker"].map(group_for_ticker)
    result["clean_component_prediction"] = result["candidate_prediction"]
    result["selected_model"] = result["group"].map(active_models)
    legacy = result["selected_model"].eq("LEGACY")
    result.loc[legacy, "candidate_prediction"] = result.loc[legacy, "legacy_prediction"]
    result.loc[legacy, "candidate_status"] = "AVAILABLE"
    result["group_selection_applied"] = legacy

    histories: dict[str | None, pd.DataFrame] = {}
    for index, row in result.iterrows():
        if not np.isfinite(pd.to_numeric(row["candidate_prediction"], errors="coerce")):
            continue
        excluded = str(row["ticker"]) if validation.startswith("LOCO") else None
        if excluded not in histories:
            histories[excluded] = _selected_history(panel, candidate_history, excluded)
        interval_values = _recalculate_intervals(row, histories[excluded])
        for column, value in interval_values.items():
            result.loc[index, column] = value
        prediction = float(result.loc[index, "candidate_prediction"])
        revenue = float(result.loc[index, "revenue"])
        candidate_revenue = float(result.loc[index, "prior_year_revenue"]) * np.exp(
            prediction / 100.0
        )
        result.loc[index, "candidate_revenue"] = candidate_revenue
        result.loc[index, "candidate_revenue_ape_pct"] = (
            abs(candidate_revenue / revenue - 1.0) * 100.0
        )
        result.loc[index, "direction_correct"] = bool(
            np.sign(prediction) == np.sign(float(result.loc[index, "actual_log_yoy"]))
        )
    return result


def _group_metrics(score: pd.DataFrame, group: str) -> dict[str, object]:
    expected = len(E_AND_P_GROUPS[group])
    selected = score.loc[score["ticker"].map(group_for_ticker).eq(group)]
    valid = selected.dropna(subset=["mase"])
    denominator = len(valid)
    mase_count = int(valid["mase"].lt(1.0).sum())
    no_regression = int(valid["improvement_log_points"].ge(0.0).sum())
    severe = int(valid["improvement_log_points"].lt(-2.0).sum())
    mase_share = mase_count / denominator if denominator else 0.0
    no_regression_share = no_regression / denominator if denominator else 0.0
    return {
        "registered_tickers": expected,
        "evaluable_tickers": denominator,
        "coverage_pass": denominator >= max(3, ceil(expected * 0.75)),
        "median_mase": float(valid["mase"].median()) if denominator else np.nan,
        "mean_mase": float(valid["mase"].mean()) if denominator else np.nan,
        "mase_below_1_count": mase_count,
        "mase_below_1_share": mase_count / denominator if denominator else np.nan,
        "legacy_no_regression_count": no_regression,
        "legacy_no_regression_share": no_regression / denominator if denominator else np.nan,
        "severe_regression_count": severe,
        "median_improvement_log_points": (
            float(valid["improvement_log_points"].median()) if denominator else np.nan
        ),
        "pi_80_coverage": float(valid["pi_80_coverage"].mean()) if denominator else np.nan,
        "directional_hit_rate": (
            float(valid["directional_hit_rate"].mean()) if denominator else np.nan
        ),
    }


def group_promotion_table(
    clean_time_score: pd.DataFrame,
    clean_loco_score: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate the clean component by group; TIME is the promotion gate."""
    rows: list[dict[str, object]] = []
    for group in E_AND_P_GROUPS:
        time = _group_metrics(clean_time_score, group)
        loco = _group_metrics(clean_loco_score, group)
        checks = {
            "time_coverage_pass": bool(time["coverage_pass"]),
            "time_median_mase_pass": float(time["median_mase"]) < 0.80,
            "time_mean_mase_pass": float(time["mean_mase"]) < 0.90,
            "time_mase_below_1_share_pass": float(time["mase_below_1_share"]) >= 0.70,
            "time_legacy_no_regression_pass": (
                float(time["legacy_no_regression_share"]) >= 0.70
            ),
            "time_median_improvement_pass": (
                float(time["median_improvement_log_points"]) > 0.0
            ),
            "time_severe_regression_pass": int(time["severe_regression_count"]) == 0,
        }
        passed = all(checks.values())
        row: dict[str, object] = {
            "group": group,
            **{f"time_{key}": value for key, value in time.items()},
            **{f"loco_{key}": value for key, value in loco.items()},
            **checks,
            "group_component_gate": passed,
            "promotion_status": (
                "PROMOTED_TO_RESEARCH_BRANCH" if passed else "REJECTED_LEGACY_RETAINED"
            ),
            "active_model": "CLEAN_COMPONENT" if passed else "LEGACY",
            "macro_research_unlocked": passed,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def grouped_success_gate(
    time_score: pd.DataFrame,
    time_summary: pd.Series,
    live_matches: int,
) -> pd.DataFrame:
    valid = time_score.dropna(subset=["mase"])
    denominator = len(valid)
    mase_count = int(valid["mase"].lt(1.0).sum())
    no_regression = int(valid["improvement_log_points"].ge(0.0).sum())
    severe = int(valid["improvement_log_points"].lt(-2.0).sum())
    mase_share = mase_count / denominator if denominator else 0.0
    no_regression_share = no_regression / denominator if denominator else 0.0
    rows = [
        ("time_median_mase_at_most_0_72", float(time_summary["median_ticker_mase"]) <= 0.72, f"{float(time_summary['median_ticker_mase']):.4f}"),
        ("time_mean_mase_at_most_0_75", float(time_summary["mean_ticker_mase"]) <= 0.75, f"{float(time_summary['mean_ticker_mase']):.4f}"),
        ("time_mase_below_1_share_at_least_85pct", mase_share >= 0.85, f"{mase_count}/{denominator} evaluable = {mase_share:.1%}"),
        ("time_legacy_no_regression_at_least_85pct", no_regression_share >= 0.85, f"{no_regression}/{denominator} evaluable = {no_regression_share:.1%}"),
        ("time_severe_regression_at_most_1", severe <= 1, f"{severe}/{denominator} below -2.0"),
        ("time_pi_80_coverage_between_75_85pct", 0.75 <= float(time_summary["mean_pi_80_coverage"]) <= 0.85, f"{float(time_summary['mean_pi_80_coverage']):.1%}"),
        ("time_directional_hit_at_least_65pct", float(time_summary["mean_directional_hit_rate"]) >= 0.65, f"{float(time_summary['mean_directional_hit_rate']):.1%}"),
    ]
    research_pass = all(passed for _, passed, _ in rows)
    rows.extend([
        ("live_20_match_model_change_lock", live_matches >= 20, f"{live_matches}/20 matched"),
        ("v3_4_production_champion_frozen", True, "Research selection does not mutate V3.4"),
    ])
    result = pd.DataFrame(rows, columns=["condition", "passed", "detail"])
    result["grouped_component_gate"] = research_pass
    result["production_eligible"] = research_pass and live_matches >= 20
    result["production_champion_changed"] = False
    return result


def validate_grouped_component(
    strategy: KPIHierarchicalStrategy,
    panel: pd.DataFrame,
    live_matches: int = 0,
) -> V353GroupedValidationResult:
    clean_time, history = run_time_holdout(strategy, panel, holdout_quarters=8)
    clean_loco = run_loco(strategy, panel, history, holdout_quarters=8)
    clean_time_score = ticker_scorecard(clean_time, minimum_observations=8)
    clean_loco_score = ticker_scorecard(clean_loco, minimum_observations=8)
    promotion = group_promotion_table(clean_time_score, clean_loco_score)
    active_models = promotion.set_index("group")["active_model"].to_dict()

    time = apply_group_selection(
        clean_time, panel, history, active_models, "TIME_HOLDOUT_8Q_PRIMARY"
    )
    loco = apply_group_selection(
        clean_loco, panel, history, active_models, "LOCO_TIME_SAFE_8Q_COLD_START"
    )
    time["validation"] = "TIME_HOLDOUT_8Q_PRIMARY_GROUPED"
    loco["validation"] = "LOCO_TIME_SAFE_8Q_COLD_START_GROUPED"
    time_score = ticker_scorecard(time, minimum_observations=8)
    loco_score = ticker_scorecard(loco, minimum_observations=8)
    summary = pd.concat([
        universe_summary(time_score, time, "TIME_HOLDOUT_8Q_PRIMARY_GROUPED"),
        universe_summary(loco_score, loco, "LOCO_TIME_SAFE_8Q_COLD_START_GROUPED"),
    ], ignore_index=True)
    gate = grouped_success_gate(time_score, summary.iloc[0], live_matches)
    return V353GroupedValidationResult(
        time,
        loco,
        time_score,
        loco_score,
        summary,
        clean_time_score,
        clean_loco_score,
        promotion,
        gate,
        history,
    )
