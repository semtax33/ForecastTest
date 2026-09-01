from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data.cutoff import quarter_cutoff_date
from ..integrated.model import predict_integrated
from ..midstream.model import predict_midstream
from ..refining.model import predict_refiner
from ..research.v351.revenue import load_companyfacts_quarterly_revenue
from ..services.model import predict_services
from ..validation.cross_section_metrics import ticker_scorecard, universe_summary
from .taxonomy import SUBINDUSTRY_TICKERS, phase_for_subindustry, subindustry_for_ticker


MODEL_FUNCTIONS = {
    "integrated": predict_integrated,
    "refining": predict_refiner,
    "midstream": predict_midstream,
    "services": predict_services,
}


@dataclass(frozen=True)
class StructuralValidationResult:
    time_predictions: pd.DataFrame
    loco_predictions: pd.DataFrame
    time_scorecard: pd.DataFrame
    loco_scorecard: pd.DataFrame
    summary: pd.DataFrame
    gate: pd.DataFrame


def _quarter_ordinal(value: str) -> int:
    return int(pd.Period(value, freq="Q").ordinal)


def _revenue_base(
    companyfacts_root,
    tickers: tuple[str, ...],
    cutoff_day: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    audit = load_companyfacts_quarterly_revenue(companyfacts_root, tickers)
    audit = audit.loc[audit["revenue"].gt(0)].copy()
    revenue_lookup = {
        (str(row["ticker"]), str(row["quarter"])): float(row["revenue"])
        for _, row in audit.iterrows()
    }
    filing_lookup = {
        (str(row["ticker"]), str(row["quarter"])): pd.Timestamp(row["filing_date"])
        for _, row in audit.iterrows()
    }
    panel = audit.copy()
    panel["prior_year_quarter"] = panel["quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 4)
    )
    panel["previous_quarter"] = panel["quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 1)
    )
    panel["prior_year_revenue"] = [
        revenue_lookup.get((str(row["ticker"]), str(row["prior_year_quarter"])), np.nan)
        for _, row in panel.iterrows()
    ]
    valid = panel["revenue"].gt(0) & panel["prior_year_revenue"].gt(0)
    panel["actual_log_yoy"] = np.nan
    panel.loc[valid, "actual_log_yoy"] = 100.0 * np.log(
        panel.loc[valid, "revenue"] / panel.loc[valid, "prior_year_revenue"]
    )
    actual_lookup = {
        (str(row["ticker"]), str(row["quarter"])): float(row["actual_log_yoy"])
        for _, row in panel.dropna(subset=["actual_log_yoy"]).iterrows()
    }
    panel["lag_revenue_log_yoy"] = [
        actual_lookup.get((str(row["ticker"]), str(row["previous_quarter"])), np.nan)
        for _, row in panel.iterrows()
    ]
    panel["lag_report_date"] = [
        filing_lookup.get((str(row["ticker"]), str(row["previous_quarter"])), pd.NaT)
        for _, row in panel.iterrows()
    ]
    panel["forecast_cutoff_date"] = panel["quarter"].map(
        lambda value: quarter_cutoff_date(value, cutoff_day)
    )
    panel["quarter_ordinal"] = panel["quarter"].map(_quarter_ordinal)
    panel["subindustry"] = panel["ticker"].map(subindustry_for_ticker)
    panel["phase"] = panel["subindustry"].map(phase_for_subindustry)
    panel["pit_lag_revenue_available"] = pd.to_datetime(
        panel["lag_report_date"], errors="coerce"
    ).le(panel["forecast_cutoff_date"])
    return panel, audit


def _apply_structural_models(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        output = row.to_dict()
        try:
            prediction = MODEL_FUNCTIONS[str(row["subindustry"])](row)
            output.update(prediction)
            output["raw_structural_prediction"] = output["candidate_prediction"]
            output["structural_feature_status"] = (
                "AVAILABLE"
                if np.isfinite(pd.to_numeric(output["candidate_prediction"], errors="coerce"))
                else "MISSING_STRUCTURAL_FEATURE"
            )
        except (KeyError, TypeError, ValueError):
            output["candidate_prediction"] = np.nan
            output["raw_structural_prediction"] = np.nan
            output["structural_feature_status"] = "MISSING_STRUCTURAL_FEATURE"
        output["legacy_prediction"] = row.get("lag_revenue_log_yoy", np.nan)
        rows.append(output)
    return pd.DataFrame(rows)


def _fit_structural_weight(
    history: pd.DataFrame,
    prior_observations: int = 20,
) -> float:
    valid = history.dropna(subset=[
        "actual_log_yoy", "legacy_prediction", "raw_structural_prediction"
    ])
    if len(valid) < 4:
        return 0.0
    delta = (
        valid["raw_structural_prediction"] - valid["legacy_prediction"]
    ).to_numpy(dtype=float)
    target = (
        valid["actual_log_yoy"] - valid["legacy_prediction"]
    ).to_numpy(dtype=float)
    denominator = float(delta @ delta)
    if denominator <= 1e-12:
        return 0.0
    coefficient = float(delta @ target / denominator)
    reliability = len(valid) / (len(valid) + prior_observations)
    return float(np.clip(coefficient * reliability, 0.0, 1.0))


def build_structural_panel(
    companyfacts_root,
    point_in_time_steo: pd.DataFrame,
    rig_features: pd.DataFrame,
    tickers: tuple[str, ...],
    cutoff_day: int = 61,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel, audit = _revenue_base(companyfacts_root, tickers, cutoff_day)
    steo = point_in_time_steo.rename(columns={"target_quarter": "quarter"}).copy()
    rigs = rig_features.rename(columns={"target_quarter": "quarter"}).copy()
    overlap = [
        column for column in ("forecast_cutoff_date",) if column in steo and column in panel
    ]
    panel = panel.drop(columns=overlap).merge(steo, on="quarter", how="left")
    panel = panel.merge(rigs, on="quarter", how="left")
    panel["forecast_cutoff_date"] = panel["quarter"].map(
        lambda value: quarter_cutoff_date(value, cutoff_day)
    )
    panel = panel.loc[
        panel["actual_log_yoy"].notna()
        & panel["lag_revenue_log_yoy"].notna()
        & panel["pit_lag_revenue_available"]
        & pd.to_datetime(panel["available_at"], errors="coerce").le(
            panel["forecast_cutoff_date"]
        )
    ].copy()
    result = _apply_structural_models(panel)
    return result.sort_values(["ticker", "quarter_ordinal"]).reset_index(drop=True), audit


def build_latest_unobserved_nowcasts(
    audit: pd.DataFrame,
    point_in_time_steo: pd.DataFrame,
    rig_features: pd.DataFrame,
    panel: pd.DataFrame,
    cutoff_day: int = 61,
) -> pd.DataFrame:
    revenue_lookup = {
        (str(row["ticker"]), str(row["quarter"])): float(row["revenue"])
        for _, row in audit.loc[audit["revenue"].gt(0)].iterrows()
    }
    filing_lookup = {
        (str(row["ticker"]), str(row["quarter"])): pd.Timestamp(row["filing_date"])
        for _, row in audit.iterrows()
    }
    rows: list[dict[str, object]] = []
    for ticker, company in audit.groupby("ticker", sort=True):
        latest = company.sort_values("quarter_ordinal").iloc[-1]
        target = str(pd.Period(str(latest["quarter"]), freq="Q") + 1)
        prior_year = str(pd.Period(target, freq="Q") - 4)
        previous = str(pd.Period(target, freq="Q") - 1)
        previous_prior_year = str(pd.Period(previous, freq="Q") - 4)
        previous_revenue = revenue_lookup.get((ticker, previous), np.nan)
        previous_prior = revenue_lookup.get((ticker, previous_prior_year), np.nan)
        rows.append({
            "ticker": ticker,
            "quarter": target,
            "quarter_ordinal": _quarter_ordinal(target),
            "subindustry": subindustry_for_ticker(ticker),
            "phase": phase_for_subindustry(subindustry_for_ticker(ticker)),
            "revenue": np.nan,
            "actual_log_yoy": np.nan,
            "prior_year_revenue": revenue_lookup.get((ticker, prior_year), np.nan),
            "lag_revenue_log_yoy": (
                100.0 * np.log(previous_revenue / previous_prior)
                if previous_revenue > 0 and previous_prior > 0
                else np.nan
            ),
            "lag_report_date": filing_lookup.get((ticker, previous), pd.NaT),
            "forecast_cutoff_date": quarter_cutoff_date(target, cutoff_day),
            "forecast_status": "LATEST_UNOBSERVED_IN_LOCAL_SEC_SNAPSHOT",
        })
    nowcasts = pd.DataFrame(rows)
    steo = point_in_time_steo.rename(columns={"target_quarter": "quarter"})
    rigs = rig_features.rename(columns={"target_quarter": "quarter"})
    nowcasts = nowcasts.drop(columns=["forecast_cutoff_date"]).merge(
        steo, on="quarter", how="left"
    ).merge(rigs, on="quarter", how="left")
    nowcasts["forecast_cutoff_date"] = nowcasts["quarter"].map(
        lambda value: quarter_cutoff_date(value, cutoff_day)
    )
    nowcasts = _apply_structural_models(nowcasts)
    calibrated: list[dict[str, object]] = []
    for _, row in nowcasts.iterrows():
        history = panel.loc[
            panel["subindustry"].eq(row["subindustry"])
            & panel["quarter_ordinal"].lt(int(row["quarter_ordinal"]))
        ].dropna(subset=["candidate_prediction", "actual_log_yoy"])
        output = row.to_dict()
        weight = _fit_structural_weight(history)
        output["structural_shrinkage_weight"] = weight
        output["candidate_prediction"] = (
            float(output["legacy_prediction"])
            + weight
            * (
                float(output["raw_structural_prediction"])
                - float(output["legacy_prediction"])
            )
        )
        adjusted_history = (
            history["legacy_prediction"]
            + weight
            * (
                history["raw_structural_prediction"]
                - history["legacy_prediction"]
            )
        )
        residuals = (
            history.assign(_adjusted_prediction=adjusted_history)
            .sort_values(["quarter_ordinal", "ticker"])
            .assign(
                _absolute_residual=lambda frame: (
                    frame["actual_log_yoy"] - frame["_adjusted_prediction"]
                ).abs()
            )["_absolute_residual"]
            .dropna()
            .tail(24)
        )
        output["calibration_observations"] = len(residuals)
        for level in (0.80, 0.95):
            label = int(level * 100)
            radius = float(residuals.quantile(level)) if len(residuals) >= 20 else np.nan
            output[f"lower_{label}_log_yoy"] = output["candidate_prediction"] - radius
            output[f"upper_{label}_log_yoy"] = output["candidate_prediction"] + radius
        output["candidate_revenue"] = (
            float(output["prior_year_revenue"])
            * np.exp(float(output["candidate_prediction"]) / 100.0)
            if np.isfinite(output["candidate_prediction"])
            and np.isfinite(output["prior_year_revenue"])
            else np.nan
        )
        output["baseline_revenue"] = (
            float(output["prior_year_revenue"])
            * np.exp(float(output["legacy_prediction"]) / 100.0)
            if np.isfinite(output["legacy_prediction"])
            and np.isfinite(output["prior_year_revenue"])
            else np.nan
        )
        calibrated.append(output)
    return pd.DataFrame(calibrated).sort_values(["phase", "subindustry", "ticker"])


def _test_rows(panel: pd.DataFrame, quarters: int) -> pd.DataFrame:
    return (
        panel.sort_values(["ticker", "quarter_ordinal"], ascending=[True, False])
        .groupby("ticker", sort=False)
        .head(quarters)
        .sort_values(["quarter_ordinal", "ticker"])
        .reset_index(drop=True)
    )


def _prediction_rows(
    panel: pd.DataFrame,
    subindustry: str,
    validation: str,
    quarters: int,
) -> pd.DataFrame:
    company_panel = panel.loc[panel["subindustry"].eq(subindustry)].copy()
    test = _test_rows(company_panel, quarters)
    first_test = int(test["quarter_ordinal"].min())
    fixed_time_history = company_panel.loc[
        company_panel["quarter_ordinal"].lt(first_test)
    ]
    outputs: list[dict[str, object]] = []
    for _, row in test.iterrows():
        if validation.startswith("LOCO"):
            history = company_panel.loc[
                company_panel["quarter_ordinal"].lt(int(row["quarter_ordinal"]))
            ]
            history = history.loc[history["ticker"].ne(row["ticker"])]
        else:
            history = fixed_time_history
        weight = _fit_structural_weight(history)
        candidate_prediction = (
            float(row["legacy_prediction"])
            + weight
            * (
                float(row["raw_structural_prediction"])
                - float(row["legacy_prediction"])
            )
        )
        adjusted_history = (
            history["legacy_prediction"]
            + weight
            * (
                history["raw_structural_prediction"]
                - history["legacy_prediction"]
            )
        )
        residuals = (
            history.assign(_adjusted_prediction=adjusted_history)
            .sort_values(["quarter_ordinal", "ticker"])
            .assign(
                _absolute_residual=lambda frame: (
                    frame["actual_log_yoy"] - frame["_adjusted_prediction"]
                ).abs()
            )["_absolute_residual"]
            .dropna()
            .tail(24)
        )
        output = row.to_dict()
        output["candidate_prediction"] = candidate_prediction
        output["structural_shrinkage_weight"] = weight
        output["validation"] = validation
        output["training_observations"] = len(history)
        output["calibration_observations"] = len(residuals)
        for level in (0.80, 0.95):
            label = int(level * 100)
            radius = float(residuals.quantile(level)) if len(residuals) >= 20 else np.nan
            prediction = candidate_prediction
            actual = float(row["actual_log_yoy"])
            output[f"lower_{label}_log_yoy"] = prediction - radius
            output[f"upper_{label}_log_yoy"] = prediction + radius
            output[f"covered_{label}"] = (
                bool(prediction - radius <= actual <= prediction + radius)
                if np.isfinite(radius)
                else np.nan
            )
        output["candidate_revenue"] = float(row["prior_year_revenue"]) * np.exp(
            candidate_prediction / 100.0
        )
        output["candidate_revenue_ape_pct"] = (
            abs(output["candidate_revenue"] / float(row["revenue"]) - 1.0) * 100.0
        )
        output["direction_correct"] = bool(
            np.sign(candidate_prediction)
            == np.sign(float(row["actual_log_yoy"]))
        )
        outputs.append(output)
    return pd.DataFrame(outputs)


def structural_gate(
    scorecard: pd.DataFrame,
    summary: pd.Series,
    subindustry: str,
    minimum_forecasts: int = 8,
) -> pd.DataFrame:
    registered = SUBINDUSTRY_TICKERS[subindustry]
    score = scorecard.loc[scorecard["ticker"].isin(registered)].copy()
    valid = score.dropna(subset=["mase"])
    count = len(valid)
    mase_below = int(valid["mase"].lt(1.0).sum())
    no_regression = int(valid["improvement_log_points"].ge(0.0).sum())
    severe = int(valid["improvement_log_points"].lt(-2.0).sum())
    checks = {
        "minimum_8_forecasts_per_ticker": (
            len(score) == len(registered)
            and score["observations"].ge(minimum_forecasts).all()
        ),
        "median_time_mase_below_0_80": float(summary["median_ticker_mase"]) < 0.80,
        "mean_time_mase_below_0_90": float(summary["mean_ticker_mase"]) < 0.90,
        "mase_below_1_share_at_least_70pct": (
            count > 0 and mase_below / count >= 0.70
        ),
        "baseline_no_regression_at_least_80pct": (
            count > 0 and no_regression / count >= 0.80
        ),
        "severe_regression_count_zero": severe == 0,
        "pi80_between_75_85pct": (
            np.isfinite(summary["mean_pi_80_coverage"])
            and 0.75 <= float(summary["mean_pi_80_coverage"]) <= 0.85
        ),
        "directional_hit_at_least_65pct": (
            np.isfinite(summary["mean_directional_hit_rate"])
            and float(summary["mean_directional_hit_rate"]) >= 0.65
        ),
    }
    return pd.DataFrame([{
        "phase": phase_for_subindustry(subindustry),
        "subindustry": subindustry,
        "registered_tickers": len(registered),
        "evaluable_tickers": count,
        "mase_below_1_count": mase_below,
        "baseline_no_regression_count": no_regression,
        "severe_regression_count": severe,
        **checks,
        "research_gate": all(checks.values()),
        "production_eligible": False,
        "live_matched_observations": 0,
    }])


def validate_subindustry(
    panel: pd.DataFrame,
    subindustry: str,
    quarters: int = 8,
) -> StructuralValidationResult:
    time = _prediction_rows(
        panel, subindustry, "TIME_HOLDOUT_8Q_PRIMARY", quarters
    )
    loco = _prediction_rows(
        panel, subindustry, "LOCO_TIME_SAFE_8Q_COLD_START", quarters
    )
    time_score = ticker_scorecard(time, minimum_observations=quarters)
    loco_score = ticker_scorecard(loco, minimum_observations=quarters)
    time_summary = universe_summary(
        time_score, time, f"TIME_HOLDOUT_8Q_{subindustry.upper()}"
    )
    loco_summary = universe_summary(
        loco_score, loco, f"LOCO_TIME_SAFE_8Q_{subindustry.upper()}"
    )
    summary = pd.concat([time_summary, loco_summary], ignore_index=True)
    gate = structural_gate(time_score, time_summary.iloc[0], subindustry, quarters)
    return StructuralValidationResult(
        time, loco, time_score, loco_score, summary, gate
    )
