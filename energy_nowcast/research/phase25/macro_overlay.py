from __future__ import annotations

from dataclasses import dataclass
import json

import numpy as np
import pandas as pd

from ...core.company_kpi_platform import _fit_point_weights, _point_predictions
from equity_platform.validation.cross_section_metrics import ticker_scorecard, universe_summary


@dataclass(frozen=True)
class ResidualCandidateResult:
    predictions: pd.DataFrame
    scorecard: pd.DataFrame
    summary: pd.DataFrame
    gate: pd.DataFrame


def attach_target_aligned_macro_features(
    panel: pd.DataFrame,
    macro_features: pd.DataFrame,
) -> pd.DataFrame:
    """Attach only features known at each target quarter's forecast cutoff."""
    result = panel.copy()
    result["brent_wti_spread_pct"] = 100.0 * (
        pd.to_numeric(result["brent"], errors="coerce")
        - pd.to_numeric(result["wti"], errors="coerce")
    ) / pd.to_numeric(result["wti"], errors="coerce").abs().replace(0.0, np.nan)
    result["crack_spread_log_yoy"] = pd.to_numeric(
        result["crack_321_per_bbl_log_yoy"], errors="coerce"
    )
    result["product_demand_log_yoy"] = pd.to_numeric(
        result["us_liquid_fuels_consumption_log_yoy"], errors="coerce"
    )
    macro_columns = [
        column
        for column in macro_features
        if column == "quarter"
        or column.endswith("_z")
        or column.endswith("_pct")
        or column.endswith("_date")
    ]
    macro_columns = list(dict.fromkeys(macro_columns))
    overlap = [
        column for column in macro_columns if column != "quarter" and column in result
    ]
    result = result.drop(columns=overlap).merge(
        macro_features[macro_columns], on="quarter", how="left"
    )
    cutoff = pd.to_datetime(result["forecast_cutoff_date"], errors="coerce")
    for column in [name for name in result if name.endswith("_availability_date")]:
        invalid = pd.to_datetime(result[column], errors="coerce").gt(cutoff)
        if invalid.any():
            raise AssertionError(f"Post-cutoff macro feature detected: {column}")
    return result


def _fit_residual(
    history: pd.DataFrame,
    target: pd.Series,
    features: tuple[str, ...],
    *,
    company_mode: bool,
    alpha: float,
    minimum_training_observations: int,
    clip_log_points: float,
) -> tuple[float, int, dict[str, float], str, pd.Series]:
    target_values = pd.to_numeric(target[list(features)], errors="coerce").to_numpy(
        dtype=float
    )
    if not np.isfinite(target_values).all():
        return (
            0.0,
            0,
            {},
            "MACRO_FEATURE_UNAVAILABLE_FALLBACK_BASELINE",
            pd.Series(dtype=float),
        )
    proxy_weight, company_weight, _ = _fit_point_weights(history, company_mode)
    train = history.copy()
    train["_baseline_prediction"] = _point_predictions(
        train, proxy_weight, company_weight, company_mode
    )
    train["_baseline_residual"] = (
        train["actual_log_yoy"] - train["_baseline_prediction"]
    )
    train = train.dropna(subset=[*features, "_baseline_residual"])
    if len(train) < minimum_training_observations:
        return (
            0.0,
            len(train),
            {},
            "INSUFFICIENT_TRAINING_FALLBACK_BASELINE",
            train["_baseline_residual"],
        )
    x = train[list(features)].to_numpy(dtype=float)
    y = train["_baseline_residual"].to_numpy(dtype=float)
    center = x.mean(axis=0)
    scale = x.std(axis=0, ddof=0)
    if not np.isfinite(scale).all() or (scale <= 1e-12).any():
        return (
            0.0,
            len(train),
            {},
            "ZERO_VARIANCE_FALLBACK_BASELINE",
            train["_baseline_residual"],
        )
    standardized = (x - center) / scale
    system = standardized.T @ standardized + alpha * np.eye(len(features))
    beta = np.linalg.solve(system, standardized.T @ y)
    overlay = float(((target_values - center) / scale) @ beta)
    overlay = float(np.clip(overlay, -clip_log_points, clip_log_points))
    adjusted_residuals = pd.Series(
        y - standardized @ beta,
        index=train.index,
        dtype=float,
    )
    coefficients = {
        feature: float(value) for feature, value in zip(features, beta)
    }
    return overlay, len(train), coefficients, "AVAILABLE", adjusted_residuals


def apply_residual_candidate(
    baseline_predictions: pd.DataFrame,
    candidate_panel: pd.DataFrame,
    subindustry: str,
    features: tuple[str, ...],
    validation: str,
    *,
    alpha: float = 8.0,
    minimum_training_observations: int = 20,
    clip_log_points: float = 8.0,
) -> pd.DataFrame:
    baseline = baseline_predictions.loc[
        baseline_predictions["subindustry"].eq(subindustry)
    ].copy()
    panel = candidate_panel.loc[candidate_panel["subindustry"].eq(subindustry)].copy()
    feature_lookup = panel[["ticker", "quarter", *features]].drop_duplicates(
        ["ticker", "quarter"]
    )
    baseline = baseline.drop(columns=list(features), errors="ignore").merge(
        feature_lookup, on=["ticker", "quarter"], how="left"
    )
    company_mode = "benchmark_raw_structural_prediction" in panel
    first_test = int(baseline["quarter_ordinal"].min())
    rows: list[dict[str, object]] = []
    for _, target in baseline.sort_values(["quarter_ordinal", "ticker"]).iterrows():
        if validation.startswith("LOCO"):
            history = panel.loc[
                panel["quarter_ordinal"].lt(int(target["quarter_ordinal"]))
                & panel["ticker"].ne(target["ticker"])
            ].copy()
        else:
            history = panel.loc[panel["quarter_ordinal"].lt(first_test)].copy()
        overlay, n, coefficients, status, adjusted_residuals = _fit_residual(
            history,
            target,
            features,
            company_mode=company_mode,
            alpha=alpha,
            minimum_training_observations=minimum_training_observations,
            clip_log_points=clip_log_points,
        )
        baseline_prediction = float(target["candidate_prediction"])
        prediction = baseline_prediction + overlay
        output = target.to_dict()
        output.update(
            {
                "baseline_candidate_prediction": baseline_prediction,
                "candidate_prediction": prediction,
                "macro_features": "+".join(features),
                "macro_overlay_log_points": overlay,
                "macro_training_observations": n,
                "macro_coefficients": json.dumps(coefficients, sort_keys=True),
                "macro_candidate_status": status,
                "macro_overlay_applied": status == "AVAILABLE",
                "validation": validation,
            }
        )
        absolute_residuals = adjusted_residuals.abs().dropna()
        output["calibration_observations"] = len(absolute_residuals)
        actual = float(target["actual_log_yoy"])
        for level in (0.80, 0.95):
            label = int(level * 100)
            radius = (
                float(absolute_residuals.quantile(level))
                if len(absolute_residuals) >= 20
                else np.nan
            )
            output[f"lower_{label}_log_yoy"] = prediction - radius
            output[f"upper_{label}_log_yoy"] = prediction + radius
            output[f"covered_{label}"] = (
                bool(prediction - radius <= actual <= prediction + radius)
                if np.isfinite(radius)
                else np.nan
            )
        output["candidate_revenue"] = float(target["prior_year_revenue"]) * np.exp(
            prediction / 100.0
        )
        output["candidate_revenue_ape_pct"] = abs(
            output["candidate_revenue"] / float(target["revenue"]) - 1.0
        ) * 100.0
        output["direction_correct"] = bool(np.sign(prediction) == np.sign(actual))
        rows.append(output)
    return pd.DataFrame(rows)


def residual_candidate_gate(
    baseline_predictions: pd.DataFrame,
    candidate_predictions: pd.DataFrame,
    subindustry: str,
    features: tuple[str, ...],
    validation: str,
    *,
    parser_quality_gate: bool,
    minimum_forecasts: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    baseline_score = ticker_scorecard(
        baseline_predictions.loc[
            baseline_predictions["subindustry"].eq(subindustry)
        ],
        minimum_observations=minimum_forecasts,
    )
    candidate_score = ticker_scorecard(
        candidate_predictions, minimum_observations=minimum_forecasts
    )
    comparison = baseline_score[[
        "ticker",
        "observations",
        "mase",
        "candidate_mae_log_points",
        "directional_hit_rate",
        "pi_80_coverage",
    ]].rename(
        columns={
            "observations": "baseline_observations",
            "mase": "baseline_mase",
            "candidate_mae_log_points": "baseline_mae",
            "directional_hit_rate": "baseline_direction",
            "pi_80_coverage": "baseline_pi80",
        }
    ).merge(
        candidate_score[[
            "ticker",
            "observations",
            "mase",
            "candidate_mae_log_points",
            "directional_hit_rate",
            "pi_80_coverage",
        ]],
        on="ticker",
        how="left",
    )
    qualified = comparison.loc[
        comparison["observations"].ge(minimum_forecasts)
    ].copy()
    delta = qualified["candidate_mae_log_points"] - qualified["baseline_mae"]
    no_regression_share = float(delta.le(0.0).mean()) if len(delta) else 0.0
    severe_count = int(delta.gt(2.0).sum())
    baseline_median = float(comparison["baseline_mase"].median())
    baseline_mean = float(comparison["baseline_mase"].mean())
    candidate_median = float(qualified["mase"].median()) if len(qualified) else np.nan
    candidate_mean = float(qualified["mase"].mean()) if len(qualified) else np.nan
    candidate_pi80 = (
        float(qualified["pi_80_coverage"].mean()) if len(qualified) else np.nan
    )
    baseline_direction = float(comparison["baseline_direction"].mean())
    candidate_direction = (
        float(qualified["directional_hit_rate"].mean())
        if len(qualified)
        else np.nan
    )
    applied_share = float(candidate_predictions["macro_overlay_applied"].mean())
    checks = {
        "minimum_8_forecasts_per_baseline_ticker": (
            len(qualified) == len(comparison) and len(comparison) > 0
        ),
        "median_mase_improves": candidate_median < baseline_median,
        "mean_mase_no_worse": candidate_mean <= baseline_mean + 1e-12,
        "baseline_no_regression_share_at_least_80pct": no_regression_share >= 0.80,
        "severe_regression_count_zero": severe_count == 0,
        "pi80_between_75_85pct": (
            np.isfinite(candidate_pi80) and 0.75 <= candidate_pi80 <= 0.85
        ),
        "direction_no_worse": candidate_direction >= baseline_direction - 1e-12,
        "feature_available_and_applied_all_rows": applied_share == 1.0,
        "parser_quality_gate": bool(parser_quality_gate),
    }
    gate = pd.DataFrame(
        [
            {
                "validation": validation,
                "subindustry": subindustry,
                "features": "+".join(features),
                "baseline_median_mase": baseline_median,
                "candidate_median_mase": candidate_median,
                "baseline_mean_mase": baseline_mean,
                "candidate_mean_mase": candidate_mean,
                "baseline_no_regression_share": no_regression_share,
                "severe_regression_count": severe_count,
                "baseline_pi80": float(comparison["baseline_pi80"].mean()),
                "candidate_pi80": candidate_pi80,
                "baseline_direction": baseline_direction,
                "candidate_direction": candidate_direction,
                "macro_applied_share": applied_share,
                **checks,
                "candidate_gate": all(bool(value) for value in checks.values()),
            }
        ]
    )
    summary = universe_summary(candidate_score, candidate_predictions, validation)
    return candidate_score, summary, gate


def evaluate_residual_candidate(
    baseline_predictions: pd.DataFrame,
    candidate_panel: pd.DataFrame,
    subindustry: str,
    features: tuple[str, ...],
    validation: str,
    *,
    parser_quality_gate: bool,
    alpha: float = 8.0,
    minimum_training_observations: int = 20,
    clip_log_points: float = 8.0,
) -> ResidualCandidateResult:
    predictions = apply_residual_candidate(
        baseline_predictions,
        candidate_panel,
        subindustry,
        features,
        validation,
        alpha=alpha,
        minimum_training_observations=minimum_training_observations,
        clip_log_points=clip_log_points,
    )
    score, summary, gate = residual_candidate_gate(
        baseline_predictions,
        predictions,
        subindustry,
        features,
        validation,
        parser_quality_gate=parser_quality_gate,
    )
    return ResidualCandidateResult(predictions, score, summary, gate)
