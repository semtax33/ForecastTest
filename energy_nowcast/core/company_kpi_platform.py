from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..integrated.company_kpi import predict_integrated_company_kpi
from ..midstream.company_kpi import predict_midstream_company_kpi
from ..refining.company_kpi import predict_refiner_company_kpi
from ..services.company_kpi import predict_services_company_kpi
from ..validation.cross_section_metrics import ticker_scorecard, universe_summary
from .calibration import interval_score, pooled_conformal_interval
from .platform import _fit_structural_weight, _test_rows
from .taxonomy import SUBINDUSTRY_TICKERS, phase_for_subindustry


COMPANY_MODEL_FUNCTIONS = {
    "integrated": predict_integrated_company_kpi,
    "refining": predict_refiner_company_kpi,
    "midstream": predict_midstream_company_kpi,
    "services": predict_services_company_kpi,
}

LAG_MACRO_COLUMNS = (
    "us_crude_production_log_yoy",
    "us_dry_gas_production_log_yoy",
    "refinery_crude_input_log_yoy",
    "total_rigs_log_yoy",
    "world_liquids_production_log_yoy",
)


@dataclass(frozen=True)
class CompanyKPIValidationResult:
    time_predictions: pd.DataFrame
    loco_predictions: pd.DataFrame
    time_scorecard: pd.DataFrame
    loco_scorecard: pd.DataFrame
    summary: pd.DataFrame
    gates: pd.DataFrame


def _apply_company_models(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        output = row.to_dict()
        prediction = COMPANY_MODEL_FUNCTIONS[str(row["subindustry"])](row)
        output.update(prediction)
        output["raw_structural_prediction"] = output["candidate_prediction"]
        output["structural_feature_status"] = (
            "COMPANY_KPI_AVAILABLE"
            if int(output.get("company_kpi_feature_count", 0)) > 0
            else "PROXY_FALLBACK"
        )
        rows.append(output)
    return pd.DataFrame(rows)


def _add_lag_macro_features(
    frame: pd.DataFrame,
    macro_history: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()
    previous_quarter = result["quarter"].map(
        lambda value: str(pd.Period(value, freq="Q") - 1)
    )
    quarterly = macro_history.drop_duplicates("quarter").set_index("quarter")
    for column in LAG_MACRO_COLUMNS:
        lookup = quarterly[column].to_dict()
        result[f"lag_{column}"] = previous_quarter.map(lookup)
    return result


def build_company_kpi_panel(
    proxy_panel: pd.DataFrame,
    company_kpi_features: pd.DataFrame,
) -> pd.DataFrame:
    panel = proxy_panel.copy().rename(
        columns={
            "raw_structural_prediction": "benchmark_raw_structural_prediction",
            "structural_model": "benchmark_structural_model",
        }
    )
    panel = _add_lag_macro_features(panel, proxy_panel)
    features = company_kpi_features.drop(
        columns=["forecast_cutoff_date"], errors="ignore"
    )
    panel = panel.merge(features, on=["ticker", "quarter"], how="left")
    pit_valid = pd.to_datetime(
        panel["company_kpi_available_at"], errors="coerce"
    ).dt.normalize().le(
        pd.to_datetime(panel["forecast_cutoff_date"], errors="coerce").dt.normalize()
    )
    panel["company_kpi_pit_valid"] = pit_valid.fillna(False)
    kpi_columns = [column for column in panel if column.endswith("_log_yoy")]
    company_columns = [
        column
        for column in kpi_columns
        if column not in proxy_panel.columns and column != "actual_log_yoy"
    ]
    panel.loc[~panel["company_kpi_pit_valid"], company_columns] = np.nan
    return _apply_company_models(panel).sort_values(
        ["ticker", "quarter_ordinal"]
    ).reset_index(drop=True)


def _fit_point_weights(
    history: pd.DataFrame,
    company_mode: bool,
    overlay_prior: int = 12,
) -> tuple[float, float, int]:
    if not company_mode:
        return _fit_structural_weight(history), 0.0, 0
    proxy_history = history.copy()
    proxy_history["raw_structural_prediction"] = proxy_history[
        "benchmark_raw_structural_prediction"
    ]
    proxy_weight = _fit_structural_weight(proxy_history)
    valid = history.dropna(subset=[
        "actual_log_yoy", "legacy_prediction", "benchmark_raw_structural_prediction",
        "raw_structural_prediction",
    ]).copy()
    if valid.empty:
        return proxy_weight, 0.0, 0
    valid["_proxy_prediction"] = valid["legacy_prediction"] + proxy_weight * (
        valid["benchmark_raw_structural_prediction"] - valid["legacy_prediction"]
    )
    valid["_company_effect"] = (
        valid["raw_structural_prediction"]
        - valid["benchmark_raw_structural_prediction"]
    )
    valid = valid.loc[valid["_company_effect"].abs().gt(1e-9)]
    observations = len(valid)
    if observations < 4:
        return proxy_weight, 0.0, observations
    effect = valid["_company_effect"].to_numpy(dtype=float)
    target = (
        valid["actual_log_yoy"] - valid["_proxy_prediction"]
    ).to_numpy(dtype=float)
    denominator = float(effect @ effect)
    if denominator <= 1e-12:
        return proxy_weight, 0.0, observations
    coefficient = float(effect @ target / denominator)
    reliability = observations / (observations + overlay_prior)
    return proxy_weight, float(np.clip(coefficient * reliability, 0.0, 1.0)), observations


def _point_predictions(
    frame: pd.DataFrame,
    proxy_weight: float,
    company_overlay_weight: float,
    company_mode: bool,
) -> pd.Series:
    proxy_raw = (
        frame["benchmark_raw_structural_prediction"]
        if company_mode
        else frame["raw_structural_prediction"]
    )
    prediction = frame["legacy_prediction"] + proxy_weight * (
        proxy_raw - frame["legacy_prediction"]
    )
    if company_mode:
        prediction = prediction + company_overlay_weight * (
            frame["raw_structural_prediction"]
            - frame["benchmark_raw_structural_prediction"]
        )
    return prediction


def _prediction_rows(
    panel: pd.DataFrame,
    subindustry: str,
    validation: str,
    quarters: int,
) -> pd.DataFrame:
    company_panel = panel.loc[panel["subindustry"].eq(subindustry)].copy()
    company_mode = "benchmark_raw_structural_prediction" in company_panel
    test = _test_rows(company_panel, quarters)
    first_test = int(test["quarter_ordinal"].min())
    fixed_time_history = company_panel.loc[
        company_panel["quarter_ordinal"].lt(first_test)
    ]
    outputs: list[dict[str, object]] = []
    for _, row in test.iterrows():
        is_loco = validation.startswith("LOCO")
        if is_loco:
            point_history = company_panel.loc[
                company_panel["quarter_ordinal"].lt(int(row["quarter_ordinal"]))
                & company_panel["ticker"].ne(row["ticker"])
            ]
        else:
            point_history = fixed_time_history
        proxy_weight, overlay_weight, overlay_observations = _fit_point_weights(
            point_history, company_mode
        )
        prediction = float(_point_predictions(
            row.to_frame().T,
            proxy_weight,
            overlay_weight,
            company_mode,
        ).iloc[0])
        calibration_history = company_panel.loc[
            company_panel["quarter_ordinal"].lt(int(row["quarter_ordinal"]))
            & pd.to_datetime(company_panel["filing_date"], errors="coerce").le(
                pd.Timestamp(row["forecast_cutoff_date"])
            )
        ].copy()
        if is_loco:
            calibration_history = calibration_history.loc[
                calibration_history["ticker"].ne(row["ticker"])
            ]
        calibration_view = calibration_history.copy()
        calibration_view["raw_structural_prediction"] = _point_predictions(
            calibration_history,
            proxy_weight,
            overlay_weight,
            company_mode,
        )
        calibration_view["legacy_prediction"] = calibration_view[
            "raw_structural_prediction"
        ]
        output = row.to_dict()
        output.update(
            {
                "candidate_prediction": prediction,
                "structural_shrinkage_weight": proxy_weight,
                "company_kpi_overlay_weight": overlay_weight,
                "company_kpi_overlay_training_observations": overlay_observations,
                "validation": validation,
                "training_observations": len(point_history),
            }
        )
        actual = float(row["actual_log_yoy"])
        for level in (0.80, 0.95):
            label = int(level * 100)
            calibrated = pooled_conformal_interval(
                calibration_view,
                str(row["ticker"]),
                prediction,
                0.0,
                level,
                allow_ticker_history=not is_loco,
            )
            lower = float(calibrated["lower"])
            upper = float(calibrated["upper"])
            output[f"lower_{label}_log_yoy"] = lower
            output[f"upper_{label}_log_yoy"] = upper
            output[f"interval_{label}_radius"] = calibrated["radius"]
            output[f"interval_{label}_group_radius"] = calibrated["group_radius"]
            output[f"interval_{label}_ticker_radius"] = calibrated["ticker_radius"]
            output[f"interval_{label}_ticker_reliability"] = calibrated[
                "ticker_reliability"
            ]
            output[f"calibration_{label}_group_observations"] = calibrated[
                "group_observations"
            ]
            output[f"calibration_{label}_ticker_observations"] = calibrated[
                "ticker_observations"
            ]
            output[f"covered_{label}"] = (
                bool(lower <= actual <= upper)
                if np.isfinite(lower) and np.isfinite(upper)
                else np.nan
            )
            output[f"interval_{label}_score"] = interval_score(
                actual, lower, upper, level
            )
        output["calibration_observations"] = output[
            "calibration_80_group_observations"
        ]
        output["candidate_revenue"] = float(row["prior_year_revenue"]) * np.exp(
            prediction / 100.0
        )
        output["candidate_revenue_ape_pct"] = abs(
            output["candidate_revenue"] / float(row["revenue"]) - 1.0
        ) * 100.0
        output["direction_correct"] = bool(
            np.sign(prediction) == np.sign(float(row["actual_log_yoy"]))
        )
        outputs.append(output)
    return pd.DataFrame(outputs)


def _score(
    predictions: pd.DataFrame,
    validation: str,
    quarters: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    score = ticker_scorecard(predictions, minimum_observations=quarters)
    extra = (
        predictions.groupby("ticker", as_index=False)
        .agg(
            pi_95_coverage=("covered_95", lambda values: values.eq(True).mean()),  # noqa: E712
            mean_interval_80_score=("interval_80_score", "mean"),
            mean_interval_95_score=("interval_95_score", "mean"),
            mean_interval_80_width=("interval_80_radius", lambda values: 2 * values.mean()),
            mean_interval_95_width=("interval_95_radius", lambda values: 2 * values.mean()),
        )
    )
    score = score.merge(extra, on="ticker", how="left")
    summary = universe_summary(score, predictions, validation)
    summary["mean_pi_95_coverage"] = float(score["pi_95_coverage"].mean())
    for column in (
        "mean_interval_80_score",
        "mean_interval_95_score",
        "mean_interval_80_width",
        "mean_interval_95_width",
    ):
        summary[column] = float(score[column].mean())
    return score, summary


def split_gates(
    scorecard: pd.DataFrame,
    summary: pd.Series,
    subindustry: str,
    minimum_forecasts: int = 8,
) -> pd.DataFrame:
    registered = SUBINDUSTRY_TICKERS[subindustry]
    valid = scorecard.loc[scorecard["ticker"].isin(registered)].dropna(subset=["mase"])
    point_checks = {
        "minimum_8_forecasts_per_ticker": (
            len(valid) == len(registered)
            and valid["observations"].ge(minimum_forecasts).all()
        ),
        "median_time_mase_below_0_80": float(summary["median_ticker_mase"]) < 0.80,
        "mean_time_mase_below_0_90": float(summary["mean_ticker_mase"]) < 0.90,
        "mase_below_1_share_at_least_70pct": valid["mase"].lt(1.0).mean() >= 0.70,
        "baseline_no_regression_at_least_80pct": (
            valid["improvement_log_points"].ge(0.0).mean() >= 0.80
        ),
        "severe_regression_count_zero": valid["improvement_log_points"].lt(-2.0).sum() == 0,
        "directional_hit_at_least_65pct": (
            float(summary["mean_directional_hit_rate"]) >= 0.65
        ),
    }
    uncertainty_checks = {
        "pi80_between_75_85pct": (
            0.75 <= float(summary["mean_pi_80_coverage"]) <= 0.85
        ),
        "pi95_between_90_100pct": (
            0.90 <= float(summary["mean_pi_95_coverage"]) <= 1.00
        ),
        "interval_80_score_finite": np.isfinite(summary["mean_interval_80_score"]),
        "interval_95_score_finite": np.isfinite(summary["mean_interval_95_score"]),
    }
    point_gate = all(bool(value) for value in point_checks.values())
    uncertainty_gate = all(bool(value) for value in uncertainty_checks.values())
    return pd.DataFrame(
        [
            {
                "phase": phase_for_subindustry(subindustry),
                "subindustry": subindustry,
                **point_checks,
                **uncertainty_checks,
                "point_model_gate": point_gate,
                "uncertainty_gate": uncertainty_gate,
                "combined_research_gate": point_gate and uncertainty_gate,
                "macro_research_unlocked": point_gate,
                "production_promotion_eligible": False,
                "live_matched_observations": 0,
            }
        ]
    )


def validate_company_kpi_subindustry(
    panel: pd.DataFrame,
    subindustry: str,
    quarters: int = 8,
) -> CompanyKPIValidationResult:
    time = _prediction_rows(panel, subindustry, "TIME_HOLDOUT_8Q_PRIMARY", quarters)
    loco = _prediction_rows(panel, subindustry, "LOCO_TIME_SAFE_8Q_COLD_START", quarters)
    time_score, time_summary = _score(
        time, f"TIME_HOLDOUT_8Q_{subindustry.upper()}", quarters
    )
    loco_score, loco_summary = _score(
        loco, f"LOCO_TIME_SAFE_8Q_{subindustry.upper()}", quarters
    )
    summary = pd.concat([time_summary, loco_summary], ignore_index=True)
    gates = split_gates(time_score, time_summary.iloc[0], subindustry, quarters)
    return CompanyKPIValidationResult(
        time, loco, time_score, loco_score, summary, gates
    )


def build_latest_company_kpi_nowcasts(
    proxy_nowcasts: pd.DataFrame,
    company_kpi_features: pd.DataFrame,
    candidate_panel: pd.DataFrame,
) -> pd.DataFrame:
    frame = proxy_nowcasts.copy().rename(
        columns={
            "raw_structural_prediction": "benchmark_raw_structural_prediction",
            "structural_model": "benchmark_structural_model",
        }
    )
    frame = _add_lag_macro_features(frame, candidate_panel)
    features = company_kpi_features.drop(
        columns=["forecast_cutoff_date"], errors="ignore"
    )
    frame = frame.merge(features, on=["ticker", "quarter"], how="left")
    frame["company_kpi_pit_valid"] = pd.to_datetime(
        frame["company_kpi_available_at"], errors="coerce"
    ).dt.normalize().le(
        pd.to_datetime(frame["forecast_cutoff_date"], errors="coerce").dt.normalize()
    )
    frame = _apply_company_models(frame)
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        history = candidate_panel.loc[
            candidate_panel["subindustry"].eq(row["subindustry"])
            & candidate_panel["quarter_ordinal"].lt(int(row["quarter_ordinal"]))
        ]
        proxy_weight, overlay_weight, overlay_observations = _fit_point_weights(
            history, company_mode=True
        )
        prediction = float(_point_predictions(
            row.to_frame().T,
            proxy_weight,
            overlay_weight,
            company_mode=True,
        ).iloc[0])
        output = row.to_dict()
        output["structural_shrinkage_weight"] = proxy_weight
        output["company_kpi_overlay_weight"] = overlay_weight
        output["company_kpi_overlay_training_observations"] = overlay_observations
        output["candidate_prediction"] = prediction
        calibration_view = history.copy()
        calibration_view["raw_structural_prediction"] = _point_predictions(
            history,
            proxy_weight,
            overlay_weight,
            company_mode=True,
        )
        calibration_view["legacy_prediction"] = calibration_view[
            "raw_structural_prediction"
        ]
        for level in (0.80, 0.95):
            label = int(level * 100)
            calibrated = pooled_conformal_interval(
                calibration_view,
                str(row["ticker"]),
                prediction,
                0.0,
                level,
                allow_ticker_history=True,
            )
            output[f"lower_{label}_log_yoy"] = calibrated["lower"]
            output[f"upper_{label}_log_yoy"] = calibrated["upper"]
            output[f"interval_{label}_radius"] = calibrated["radius"]
        output["candidate_revenue"] = float(row["prior_year_revenue"]) * np.exp(
            prediction / 100.0
        )
        output["selected_model"] = "LAG_REVENUE_BASELINE"
        output["selected_prediction"] = float(row["legacy_prediction"])
        output["selected_revenue"] = float(row["baseline_revenue"])
        output["production_selection_reason"] = "LIVE_FORWARD_GATE_0_OF_20"
        rows.append(output)
    return pd.DataFrame(rows).sort_values(["phase", "subindustry", "ticker"])


def build_latest_proxy_recalibrated_nowcasts(
    proxy_nowcasts: pd.DataFrame,
    proxy_panel: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in proxy_nowcasts.iterrows():
        history = proxy_panel.loc[
            proxy_panel["subindustry"].eq(row["subindustry"])
            & proxy_panel["quarter_ordinal"].lt(int(row["quarter_ordinal"]))
        ].copy()
        proxy_weight, _, _ = _fit_point_weights(history, company_mode=False)
        prediction = float(_point_predictions(
            row.to_frame().T,
            proxy_weight,
            0.0,
            company_mode=False,
        ).iloc[0])
        calibration_view = history.copy()
        calibration_view["raw_structural_prediction"] = _point_predictions(
            history,
            proxy_weight,
            0.0,
            company_mode=False,
        )
        calibration_view["legacy_prediction"] = calibration_view[
            "raw_structural_prediction"
        ]
        output = row.to_dict()
        output["candidate_prediction"] = prediction
        output["structural_shrinkage_weight"] = proxy_weight
        for level in (0.80, 0.95):
            label = int(level * 100)
            calibrated = pooled_conformal_interval(
                calibration_view,
                str(row["ticker"]),
                prediction,
                0.0,
                level,
                allow_ticker_history=True,
            )
            output[f"lower_{label}_log_yoy"] = calibrated["lower"]
            output[f"upper_{label}_log_yoy"] = calibrated["upper"]
            output[f"interval_{label}_radius"] = calibrated["radius"]
        output["candidate_revenue"] = float(row["prior_year_revenue"]) * np.exp(
            prediction / 100.0
        )
        rows.append(output)
    return pd.DataFrame(rows).sort_values(["phase", "subindustry", "ticker"])
