from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd

from ...validation.cross_section_metrics import ticker_scorecard
from ..v35.taxonomy import group_for_ticker


@dataclass(frozen=True)
class MacroCandidateResult:
    predictions: pd.DataFrame
    scorecard: pd.DataFrame
    gate: pd.DataFrame


def _fit_overlay(
    history: pd.DataFrame,
    target: pd.Series,
    features: tuple[str, ...],
    alpha: float,
    minimum_training_observations: int,
    clip_log_points: float,
) -> tuple[float, int, dict[str, float], str]:
    target_values = pd.to_numeric(target[list(features)], errors="coerce").to_numpy(
        dtype=float
    )
    if not np.isfinite(target_values).all():
        return np.nan, 0, {}, "MACRO_FEATURE_UNAVAILABLE_AT_CUTOFF"
    columns = [*features, "residual", "quarter_ordinal"]
    train = history.loc[
        history["quarter_ordinal"].lt(int(target["quarter_ordinal"])), columns
    ].dropna()
    if len(train) < minimum_training_observations:
        # A deployable overlay must define cold-start behavior. Shrink exactly
        # to the frozen grouped benchmark until enough prior residuals exist.
        return 0.0, len(train), {}, "NEUTRAL_COLD_START_SHRINKAGE"
    x = train[list(features)].to_numpy(dtype=float)
    y = train["residual"].to_numpy(dtype=float)
    center = x.mean(axis=0)
    scale = x.std(axis=0, ddof=0)
    if not np.isfinite(scale).all() or (scale <= 1e-12).any():
        return 0.0, len(train), {}, "NEUTRAL_ZERO_VARIANCE_SHRINKAGE"
    standardized = (x - center) / scale
    system = standardized.T @ standardized + alpha * np.eye(len(features))
    beta = np.linalg.solve(system, standardized.T @ y)
    overlay = float(((target_values - center) / scale) @ beta)
    overlay = float(np.clip(overlay, -clip_log_points, clip_log_points))
    coefficients = {feature: float(value) for feature, value in zip(features, beta)}
    return overlay, len(train), coefficients, "AVAILABLE"


def _macro_history(
    baseline_history: pd.DataFrame,
    macro_features: pd.DataFrame,
    group: str,
    features: tuple[str, ...],
    alpha: float,
    minimum_training_observations: int,
    clip_log_points: float,
) -> pd.DataFrame:
    history = baseline_history.copy()
    history["group"] = history["ticker"].map(group_for_ticker)
    history = history.loc[history["group"].eq(group)].merge(
        macro_features[["quarter", *features]], on="quarter", how="left"
    )
    rows: list[dict[str, object]] = []
    for _, target in history.sort_values(["quarter_ordinal", "ticker"]).iterrows():
        overlay, n, coefficients, status = _fit_overlay(
            history,
            target,
            features,
            alpha,
            minimum_training_observations,
            clip_log_points,
        )
        prediction = (
            float(target["candidate_prediction"]) + overlay
            if np.isfinite(overlay)
            else np.nan
        )
        rows.append({
            "ticker": target["ticker"],
            "quarter": target["quarter"],
            "quarter_ordinal": int(target["quarter_ordinal"]),
            "actual_log_yoy": float(target["actual_log_yoy"]),
            "candidate_prediction": prediction,
            "residual": (
                float(target["actual_log_yoy"]) - prediction
                if np.isfinite(prediction)
                else np.nan
            ),
            "macro_overlay_log_points": overlay,
            "macro_training_observations": n,
            "macro_coefficients": json.dumps(coefficients, sort_keys=True),
            "macro_candidate_status": status,
        })
    return pd.DataFrame(rows)


def _attach_interval_and_revenue(
    result: pd.DataFrame,
    index: int,
    row: pd.Series,
    overlay_history: pd.DataFrame,
) -> None:
    prior = overlay_history.loc[
        overlay_history["quarter_ordinal"].lt(int(row["quarter_ordinal"])),
        "residual",
    ].dropna().abs()
    result.loc[index, "calibration_observations"] = len(prior)
    prediction = float(result.loc[index, "candidate_prediction"])
    actual = float(row["actual_log_yoy"])
    for level in (0.80, 0.95):
        label = int(level * 100)
        radius = float(prior.quantile(level)) if len(prior) >= 20 else np.nan
        result.loc[index, f"lower_{label}_log_yoy"] = prediction - radius
        result.loc[index, f"upper_{label}_log_yoy"] = prediction + radius
        result.loc[index, f"covered_{label}"] = (
            bool(prediction - radius <= actual <= prediction + radius)
            if np.isfinite(radius)
            else np.nan
        )
    revenue = float(row["revenue"])
    candidate_revenue = float(row["prior_year_revenue"]) * np.exp(prediction / 100.0)
    result.loc[index, "candidate_revenue"] = candidate_revenue
    result.loc[index, "candidate_revenue_ape_pct"] = (
        abs(candidate_revenue / revenue - 1.0) * 100.0
    )
    result.loc[index, "direction_correct"] = bool(
        np.sign(prediction) == np.sign(actual)
    )


def apply_macro_overlay(
    baseline_predictions: pd.DataFrame,
    panel: pd.DataFrame,
    candidate_history: pd.DataFrame,
    macro_features: pd.DataFrame,
    group: str,
    features: tuple[str, ...],
    validation: str,
    alpha: float = 8.0,
    minimum_training_observations: int = 20,
    clip_log_points: float = 8.0,
) -> pd.DataFrame:
    """Apply a group-only, point-in-time residual macro overlay."""
    if group == "gas_heavy":
        raise ValueError("Gas macro research is prohibited after the V3.5.3 gate")
    result = baseline_predictions.loc[
        baseline_predictions["group"].eq(group)
    ].copy()
    result["baseline_grouped_prediction"] = result["candidate_prediction"]
    feature_columns = [
        "quarter",
        "forecast_cutoff_date",
        *features,
        *[f"{feature}_observation_date" for feature in features],
        *[f"{feature}_availability_date" for feature in features],
    ]
    result = result.drop(
        columns=[column for column in feature_columns if column != "quarter" and column in result],
        errors="ignore",
    ).merge(macro_features[feature_columns], on="quarter", how="left")
    result["macro_group"] = group
    result["macro_features"] = "+".join(features)
    result["macro_overlay_log_points"] = np.nan
    result["macro_training_observations"] = 0
    result["macro_coefficients"] = "{}"
    result["macro_overlay_applied"] = False
    result["macro_candidate_status"] = "NOT_EVALUATED"

    history_cache: dict[str | None, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for index, row in result.sort_values(["quarter_ordinal", "ticker"]).iterrows():
        if not np.isfinite(pd.to_numeric(row["baseline_grouped_prediction"], errors="coerce")):
            result.loc[index, "candidate_prediction"] = np.nan
            result.loc[index, "candidate_status"] = "BASELINE_GROUPED_UNAVAILABLE"
            result.loc[index, "macro_candidate_status"] = "BASELINE_GROUPED_UNAVAILABLE"
            continue
        excluded = str(row["ticker"]) if validation.startswith("LOCO") else None
        if excluded not in history_cache:
            baseline_history = candidate_history.copy()
            if excluded is not None:
                baseline_history = baseline_history.loc[
                    baseline_history["ticker"].ne(excluded)
                ]
            baseline_history["group"] = baseline_history["ticker"].map(group_for_ticker)
            baseline_history = baseline_history.loc[
                baseline_history["group"].eq(group)
            ]
            selected = baseline_history.merge(
                macro_features[["quarter", *features]], on="quarter", how="left"
            )
            overlaid = _macro_history(
                baseline_history,
                macro_features,
                group,
                features,
                alpha,
                minimum_training_observations,
                clip_log_points,
            )
            history_cache[excluded] = (selected, overlaid)
        selected_history, overlay_history = history_cache[excluded]
        overlay, n, coefficients, status = _fit_overlay(
            selected_history,
            row,
            features,
            alpha,
            minimum_training_observations,
            clip_log_points,
        )
        result.loc[index, "macro_training_observations"] = n
        result.loc[index, "macro_coefficients"] = json.dumps(
            coefficients, sort_keys=True
        )
        result.loc[index, "macro_candidate_status"] = status
        result.loc[index, "candidate_status"] = (
            "AVAILABLE" if np.isfinite(overlay) else status
        )
        if not np.isfinite(overlay):
            result.loc[index, "candidate_prediction"] = np.nan
            continue
        result.loc[index, "macro_overlay_log_points"] = overlay
        result.loc[index, "candidate_prediction"] = (
            float(row["baseline_grouped_prediction"]) + overlay
        )
        result.loc[index, "macro_overlay_applied"] = status == "AVAILABLE"
        _attach_interval_and_revenue(result, index, row, overlay_history)
    result["validation"] = validation
    return result


def macro_candidate_gate(
    baseline_scorecard: pd.DataFrame,
    candidate_scorecard: pd.DataFrame,
    group: str,
    features: tuple[str, ...],
    validation: str,
    minimum_forecasts: int = 8,
) -> pd.DataFrame:
    baseline = baseline_scorecard.loc[
        baseline_scorecard["ticker"].map(group_for_ticker).eq(group)
        & baseline_scorecard["observations"].ge(minimum_forecasts)
    ].copy()
    candidate = candidate_scorecard.loc[
        candidate_scorecard["ticker"].isin(baseline["ticker"])
    ].copy()
    comparison = baseline[[
        "ticker", "mase", "candidate_mae_log_points", "directional_hit_rate",
        "pi_80_coverage",
    ]].rename(columns={
        "mase": "baseline_mase",
        "candidate_mae_log_points": "baseline_mae",
        "directional_hit_rate": "baseline_direction",
        "pi_80_coverage": "baseline_pi80",
    }).merge(
        candidate[[
            "ticker", "observations", "mase", "candidate_mae_log_points",
            "directional_hit_rate", "pi_80_coverage",
        ]],
        on="ticker",
        how="left",
    )
    qualified = comparison.loc[comparison["observations"].ge(minimum_forecasts)].copy()
    baseline_median = float(comparison["baseline_mase"].median()) if len(comparison) else np.nan
    baseline_mean = float(comparison["baseline_mase"].mean()) if len(comparison) else np.nan
    candidate_median = float(qualified["mase"].median()) if len(qualified) else np.nan
    candidate_mean = float(qualified["mase"].mean()) if len(qualified) else np.nan
    delta = qualified["candidate_mae_log_points"] - qualified["baseline_mae"]
    no_regression_count = int(delta.le(0.0).sum())
    severe_count = int(delta.gt(2.0).sum())
    denominator = len(comparison)
    no_regression_share = no_regression_count / denominator if denominator else 0.0
    candidate_pi80 = float(qualified["pi_80_coverage"].mean()) if len(qualified) else np.nan
    baseline_direction = float(comparison["baseline_direction"].mean()) if denominator else np.nan
    candidate_direction = float(qualified["directional_hit_rate"].mean()) if len(qualified) else np.nan
    checks = {
        "minimum_8_forecasts_per_baseline_ticker": (
            denominator > 0 and len(qualified) == denominator
        ),
        "group_median_mase_improves": (
            np.isfinite(candidate_median) and candidate_median < baseline_median
        ),
        "group_mean_mase_no_worse": (
            np.isfinite(candidate_mean) and candidate_mean <= baseline_mean + 1e-12
        ),
        "baseline_no_regression_share_at_least_80pct": (
            denominator > 0 and no_regression_share >= 0.80
        ),
        "severe_regression_count_zero": severe_count == 0,
        "pi80_between_75_85pct": (
            np.isfinite(candidate_pi80) and 0.75 <= candidate_pi80 <= 0.85
        ),
        "direction_no_worse": (
            np.isfinite(candidate_direction)
            and candidate_direction >= baseline_direction - 1e-12
        ),
    }
    row: dict[str, object] = {
        "validation": validation,
        "group": group,
        "features": "+".join(features),
        "baseline_qualified_tickers": denominator,
        "candidate_qualified_tickers": len(qualified),
        "minimum_candidate_forecasts": (
            int(comparison["observations"].fillna(0).min()) if denominator else 0
        ),
        "baseline_median_mase": baseline_median,
        "candidate_median_mase": candidate_median,
        "baseline_mean_mase": baseline_mean,
        "candidate_mean_mase": candidate_mean,
        "baseline_no_regression_count": no_regression_count,
        "baseline_no_regression_share": no_regression_share,
        "severe_regression_count": severe_count,
        "baseline_pi80": float(comparison["baseline_pi80"].mean()) if denominator else np.nan,
        "candidate_pi80": candidate_pi80,
        "baseline_direction": baseline_direction,
        "candidate_direction": candidate_direction,
        **checks,
        "candidate_gate": all(checks.values()),
    }
    return pd.DataFrame([row])


def evaluate_macro_candidate(
    baseline_predictions: pd.DataFrame,
    baseline_scorecard: pd.DataFrame,
    panel: pd.DataFrame,
    candidate_history: pd.DataFrame,
    macro_features: pd.DataFrame,
    group: str,
    features: tuple[str, ...],
    validation: str,
    alpha: float = 8.0,
    minimum_training_observations: int = 20,
    clip_log_points: float = 8.0,
) -> MacroCandidateResult:
    predictions = apply_macro_overlay(
        baseline_predictions,
        panel,
        candidate_history,
        macro_features,
        group,
        features,
        validation,
        alpha,
        minimum_training_observations,
        clip_log_points,
    )
    score = ticker_scorecard(predictions, minimum_observations=8)
    score["group"] = group
    score["features"] = "+".join(features)
    score["validation"] = validation
    gate = macro_candidate_gate(
        baseline_scorecard, score, group, features, validation
    )
    return MacroCandidateResult(predictions, score, gate)


def passing_pairwise_combinations(
    time_gates: pd.DataFrame,
    group: str,
) -> list[tuple[str, str]]:
    passing = time_gates.loc[
        time_gates["group"].eq(group)
        & time_gates["candidate_gate"].eq(True)  # noqa: E712
        & ~time_gates["features"].str.contains("\\+", regex=True),
        "features",
    ].tolist()
    return list(combinations(sorted(set(map(str, passing))), 2))
