from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ...validation.cross_section_metrics import ticker_scorecard, universe_summary
from ...validation.universe_backtest import LEGACY_FEATURES, PooledRidge
from .strategy import KPIHierarchicalStrategy


@dataclass(frozen=True)
class V35ValidationResult:
    time_predictions: pd.DataFrame
    loco_predictions: pd.DataFrame
    time_scorecard: pd.DataFrame
    loco_scorecard: pd.DataFrame
    universe_summary: pd.DataFrame
    promotion_gate: pd.DataFrame


def _test_frame(
    panel: pd.DataFrame,
    candidate_history: pd.DataFrame,
    quarters: int,
) -> pd.DataFrame:
    """Select the latest forecastable observations, preserving explicit gaps.

    Selecting the latest panel rows first can silently turn an 8-quarter test
    into a 1-6 observation test when KPI history is sparse. We instead take up
    to eight latest point-in-time candidate rows and fill any shortfall with
    the latest unavailable panel rows so missing coverage remains visible.
    """
    frames: list[pd.DataFrame] = []
    history_keys = candidate_history[["ticker", "quarter"]].drop_duplicates()
    for ticker, company in panel.groupby("ticker", sort=True):
        company = company.sort_values("quarter_ordinal", ascending=False)
        available = company.merge(
            history_keys.loc[history_keys["ticker"].eq(ticker)],
            on=["ticker", "quarter"],
            how="inner",
        ).head(quarters)
        selected_quarters = set(available["quarter"].astype(str))
        fill = company.loc[~company["quarter"].astype(str).isin(selected_quarters)].head(
            max(quarters - len(available), 0)
        )
        frames.append(pd.concat([available, fill], ignore_index=True))
    return pd.concat(frames, ignore_index=True).sort_values(
        ["quarter_ordinal", "ticker"]
    ).reset_index(drop=True)


def _candidate_history(strategy: KPIHierarchicalStrategy, panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, target in panel.sort_values(["quarter_ordinal", "ticker"]).iterrows():
        prediction = strategy.predict(str(target["ticker"]), str(target["quarter"]))
        if prediction is None:
            continue
        rows.append({
            "ticker": target["ticker"],
            "quarter": target["quarter"],
            "quarter_ordinal": target["quarter_ordinal"],
            "actual_log_yoy": target["actual_log_yoy"],
            "candidate_prediction": prediction["prediction_log_yoy"],
        })
    result = pd.DataFrame(rows)
    if not result.empty:
        result["residual"] = result["actual_log_yoy"] - result["candidate_prediction"]
    return result


def _attach_intervals(
    row: dict[str, object],
    candidate_history: pd.DataFrame,
    excluded_ticker: str | None,
) -> None:
    history = candidate_history.loc[
        candidate_history["quarter_ordinal"].lt(int(row["quarter_ordinal"]))
    ]
    if excluded_ticker:
        history = history.loc[history["ticker"].ne(excluded_ticker)]
    residuals = history["residual"].dropna().abs()
    row["calibration_observations"] = len(residuals)
    for level in (0.80, 0.95):
        label = int(level * 100)
        radius = float(residuals.quantile(level)) if len(residuals) >= 20 else np.nan
        prediction = float(row["candidate_prediction"])
        actual = float(row["actual_log_yoy"])
        row[f"lower_{label}_log_yoy"] = prediction - radius
        row[f"upper_{label}_log_yoy"] = prediction + radius
        row[f"covered_{label}"] = bool(prediction - radius <= actual <= prediction + radius) if np.isfinite(radius) else np.nan


def _prediction_row(
    target: pd.Series,
    candidate: dict[str, object] | None,
    legacy_prediction: float,
    training_observations: int,
    validation: str,
    candidate_history: pd.DataFrame,
    excluded_ticker: str | None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": str(target["ticker"]),
        "quarter": str(target["quarter"]),
        "quarter_ordinal": int(target["quarter_ordinal"]),
        "actual_log_yoy": float(target["actual_log_yoy"]),
        "revenue": float(target["revenue"]),
        "prior_year_revenue": float(target["prior_year_revenue"]),
        "rolling_median_revenue_8q": pd.to_numeric(
            target.get("rolling_median_revenue_8q"), errors="coerce"
        ),
        "small_denominator_flag": bool(target.get("small_denominator_flag", False)),
        "legacy_prediction": legacy_prediction,
        "candidate_prediction": np.nan,
        "validation": validation,
        "training_observations": training_observations,
        "candidate_status": "NO_POINT_IN_TIME_KPI_PREDICTION",
    }
    if candidate is None:
        return row
    row.update({
        "candidate_prediction": float(candidate["prediction_log_yoy"]),
        "candidate_status": "AVAILABLE",
        **{key: value for key, value in candidate.items() if key not in {"ticker", "quarter", "prediction_log_yoy"}},
    })
    _attach_intervals(row, candidate_history, excluded_ticker)
    row["candidate_revenue"] = float(row["prior_year_revenue"]) * np.exp(float(row["candidate_prediction"]) / 100.0)
    row["candidate_revenue_ape_pct"] = abs(float(row["candidate_revenue"]) / float(row["revenue"]) - 1.0) * 100.0
    row["direction_correct"] = bool(
        np.sign(float(row["candidate_prediction"])) == np.sign(float(row["actual_log_yoy"]))
    )
    return row


def run_time_holdout(
    strategy: KPIHierarchicalStrategy,
    panel: pd.DataFrame,
    holdout_quarters: int = 8,
    alpha: float = 8.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidate_history = _candidate_history(strategy, panel)
    test = _test_frame(panel, candidate_history, holdout_quarters)
    first_test = int(test["quarter_ordinal"].min())
    train = panel.loc[panel["quarter_ordinal"].lt(first_test)].copy()
    legacy_model = PooledRidge(alpha)
    outputs = []
    for _, target in test.sort_values(["quarter_ordinal", "ticker"]).iterrows():
        candidate = strategy.predict(str(target["ticker"]), str(target["quarter"]))
        legacy = float(legacy_model.predict(train, target.to_frame().T, LEGACY_FEATURES)[0])
        outputs.append(_prediction_row(
            target, candidate, legacy, len(train), "TIME_HOLDOUT_8Q",
            candidate_history, None,
        ))
    return pd.DataFrame(outputs), candidate_history


def run_loco(
    strategy: KPIHierarchicalStrategy,
    panel: pd.DataFrame,
    candidate_history: pd.DataFrame,
    holdout_quarters: int = 8,
    alpha: float = 8.0,
) -> pd.DataFrame:
    test = _test_frame(panel, candidate_history, holdout_quarters)
    legacy_model = PooledRidge(alpha)
    outputs = []
    for _, target in test.sort_values(["quarter_ordinal", "ticker"]).iterrows():
        ticker = str(target["ticker"])
        train = panel.loc[
            panel["ticker"].ne(ticker)
            & panel["quarter_ordinal"].lt(int(target["quarter_ordinal"]))
        ].copy()
        candidate = strategy.predict(ticker, str(target["quarter"]), excluded_ticker=ticker)
        legacy = float(legacy_model.predict(train, target.to_frame().T, LEGACY_FEATURES)[0])
        outputs.append(_prediction_row(
            target, candidate, legacy, len(train), "LOCO_TIME_SAFE_8Q",
            candidate_history, ticker,
        ))
    return pd.DataFrame(outputs)


def v35_promotion_gate(
    loco_score: pd.DataFrame,
    loco_summary: pd.Series,
    ready_company_count: int,
    live_matches: int,
) -> pd.DataFrame:
    evaluable = loco_score.dropna(subset=["mase"]).copy()
    qualified = loco_score.loc[loco_score["observations"].ge(8)].copy()
    company_count = len(loco_score)
    evaluable_count = len(evaluable)
    mase_count = int(evaluable["mase"].lt(1.0).sum())
    legacy_count = int(evaluable["improvement_log_points"].ge(0.0).sum())
    mase_share = float(mase_count / evaluable_count) if evaluable_count else 0.0
    legacy_share = float(legacy_count / evaluable_count) if evaluable_count else 0.0
    pi_coverage = float(loco_summary["mean_pi_80_coverage"])
    research_rows = [
        ("standardized_kpi_coverage", ready_company_count >= 12, f"{ready_company_count}/14 ready"),
        ("minimum_8_forecasts_per_ticker", len(qualified) >= 12, f"{len(qualified)}/{company_count} registered tickers"),
        ("median_loco_mase_below_0_80", float(loco_summary["median_ticker_mase"]) < 0.80, str(loco_summary["median_ticker_mase"])),
        ("mean_loco_mase_below_0_90", float(loco_summary["mean_ticker_mase"]) < 0.90, str(loco_summary["mean_ticker_mase"])),
        ("mase_below_1_share_at_least_70pct", mase_share >= 0.70, f"{mase_count}/{evaluable_count} evaluable = {mase_share:.1%}"),
        ("legacy_no_regression_at_least_70pct", legacy_share >= 0.70, f"{legacy_count}/{evaluable_count} evaluable = {legacy_share:.1%}"),
        ("median_candidate_improvement_positive", float(evaluable["improvement_log_points"].median()) > 0 if len(evaluable) else False, str(evaluable["improvement_log_points"].median() if len(evaluable) else np.nan)),
        ("pi_80_coverage_between_75_85pct", 0.75 <= pi_coverage <= 0.85, f"{pi_coverage:.1%}"),
        ("no_severe_ticker_regression", bool(evaluable["improvement_log_points"].ge(-2.0).all()) if len(evaluable) else False, f"{int(evaluable['improvement_log_points'].lt(-2.0).sum())}/{evaluable_count} below -2.0"),
    ]
    research_pass = all(passed for _, passed, _ in research_rows)
    rows = research_rows + [
        ("macro_overlay_unlock", research_pass, "Requires every KPI component research gate"),
        ("live_20_match_model_change_lock", live_matches >= 20, f"{live_matches}/20 matched"),
    ]
    result = pd.DataFrame(rows, columns=["condition", "passed", "detail"])
    result["research_component_gate"] = research_pass
    result["macro_overlay_enabled"] = research_pass
    result["champion_promotion"] = research_pass and live_matches >= 20
    return result


def validate_v35(
    strategy: KPIHierarchicalStrategy,
    panel: pd.DataFrame,
    ready_company_count: int,
    live_matches: int = 0,
) -> V35ValidationResult:
    time_predictions, history = run_time_holdout(strategy, panel)
    loco_predictions = run_loco(strategy, panel, history)
    time_score = ticker_scorecard(time_predictions, minimum_observations=8)
    loco_score = ticker_scorecard(loco_predictions, minimum_observations=8)
    summaries = pd.concat([
        universe_summary(time_score, time_predictions, "TIME_HOLDOUT_8Q"),
        universe_summary(loco_score, loco_predictions, "LOCO_TIME_SAFE_8Q"),
    ], ignore_index=True)
    gate = v35_promotion_gate(loco_score, summaries.iloc[1], ready_company_count, live_matches)
    promotion = bool(gate["champion_promotion"].iloc[0])
    time_score["promoted"] = time_score["company_gate_pass"] & promotion
    loco_score["promoted"] = loco_score["company_gate_pass"] & promotion
    return V35ValidationResult(
        time_predictions, loco_predictions, time_score, loco_score, summaries, gate
    )
