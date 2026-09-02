from __future__ import annotations

from dataclasses import dataclass
import json

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TargetValidationResult:
    time_predictions: pd.DataFrame
    loco_predictions: pd.DataFrame
    time_scorecard: pd.DataFrame
    loco_scorecard: pd.DataFrame
    summary: pd.DataFrame
    gate: pd.DataFrame


def _test_rows(panel: pd.DataFrame, quarters: int) -> pd.DataFrame:
    return (
        panel.sort_values(["entity", "quarter_ordinal"])
        .groupby("entity", as_index=False, group_keys=False)
        .tail(quarters)
        .reset_index(drop=True)
    )


def _ridge_prediction(
    history: pd.DataFrame,
    target: pd.Series,
    features: tuple[str, ...],
    *,
    alpha: float,
    minimum_training_observations: int,
    clip_change: float,
) -> tuple[float, int, dict[str, float], str, pd.Series]:
    target_features = pd.to_numeric(target[list(features)], errors="coerce").to_numpy(
        dtype=float
    )
    if not np.isfinite(target_features).all():
        return 0.0, 0, {}, "FEATURE_UNAVAILABLE_ZERO_CHANGE", pd.Series(dtype=float)
    train = history.dropna(subset=["actual_change", *features]).copy()
    if len(train) < minimum_training_observations:
        return (
            0.0,
            len(train),
            {},
            "INSUFFICIENT_HISTORY_ZERO_CHANGE",
            pd.Series(dtype=float),
        )
    x = train[list(features)].to_numpy(dtype=float)
    y = train["actual_change"].to_numpy(dtype=float)
    center = x.mean(axis=0)
    scale = x.std(axis=0, ddof=0)
    if not np.isfinite(scale).all() or (scale <= 1e-12).any():
        return 0.0, len(train), {}, "ZERO_VARIANCE_ZERO_CHANGE", pd.Series(dtype=float)
    z = (x - center) / scale
    y_center = float(y.mean())
    beta = np.linalg.solve(
        z.T @ z + alpha * np.eye(len(features)), z.T @ (y - y_center)
    )
    prediction = y_center + float(((target_features - center) / scale) @ beta)
    prediction = float(np.clip(prediction, -clip_change, clip_change))
    fitted = y_center + z @ beta
    residuals = pd.Series(y - fitted, index=train.index, dtype=float)
    coefficients = {
        feature: float(value) for feature, value in zip(features, beta)
    }
    return prediction, len(train), coefficients, "AVAILABLE", residuals


def _level_from_change(
    prior_year_value: float,
    prediction: float,
    transform: str,
) -> float:
    if transform == "LOG":
        return prior_year_value * float(np.exp(prediction / 100.0))
    if transform == "DELTA":
        return prior_year_value + prediction
    raise ValueError(f"Unknown target transform: {transform}")


def _prediction_rows(
    panel: pd.DataFrame,
    features: tuple[str, ...],
    validation: str,
    *,
    quarters: int,
    alpha: float,
    minimum_training_observations: int,
    clip_change: float,
) -> pd.DataFrame:
    source = panel.dropna(
        subset=["actual_change", "lag_change", "target_value", "prior_year_target_value"]
    ).copy()
    test = _test_rows(source, quarters)
    test_keys = set(zip(test["entity"], test["quarter"]))
    fixed_history = source.loc[
        ~pd.Series(
            list(zip(source["entity"], source["quarter"])), index=source.index
        ).isin(test_keys)
    ].copy()
    outputs: list[dict[str, object]] = []
    for _, target in test.sort_values(["quarter_ordinal", "entity"]).iterrows():
        forecast_cutoff = pd.to_datetime(
            target.get("forecast_cutoff_date"), errors="coerce"
        )
        if validation.startswith("LOCO"):
            history = source.loc[
                source["quarter_ordinal"].lt(int(target["quarter_ordinal"]))
                & source["entity"].ne(target["entity"])
            ].copy()
        else:
            history = fixed_history.loc[
                fixed_history["quarter_ordinal"].lt(int(target["quarter_ordinal"]))
            ].copy()
        if "available_at" in history and pd.notna(forecast_cutoff):
            history = history.loc[
                pd.to_datetime(history["available_at"], errors="coerce").le(
                    forecast_cutoff
                )
            ].copy()
        prediction, n, coefficients, status, residuals = _ridge_prediction(
            history,
            target,
            features,
            alpha=alpha,
            minimum_training_observations=minimum_training_observations,
            clip_change=clip_change,
        )
        actual_change = float(target["actual_change"])
        actual_level = float(target["target_value"])
        prior_year_level = float(target["prior_year_target_value"])
        predicted_level = _level_from_change(
            prior_year_level, prediction, str(target["target_transform"])
        )
        output = target.to_dict()
        output.update(
            {
                "candidate_prediction": prediction,
                "baseline_prediction": 0.0,
                "legacy_prediction": float(target["lag_change"]),
                "candidate_target_value": predicted_level,
                "absolute_change_error": abs(actual_change - prediction),
                "absolute_target_error": abs(actual_level - predicted_level),
                "direction_correct": bool(np.sign(prediction) == np.sign(actual_change)),
                "model_features": "+".join(features),
                "model_coefficients": json.dumps(coefficients, sort_keys=True),
                "model_status": status,
                "model_applied": status == "AVAILABLE",
                "training_observations": n,
                "validation": validation,
                "training_cutoff_date": forecast_cutoff,
            }
        )
        absolute_residuals = residuals.abs().dropna()
        output["calibration_observations"] = len(absolute_residuals)
        for level in (0.80, 0.95):
            label = int(level * 100)
            radius = (
                float(absolute_residuals.quantile(level))
                if len(absolute_residuals) >= 20
                else np.nan
            )
            output[f"lower_{label}_change"] = prediction - radius
            output[f"upper_{label}_change"] = prediction + radius
            output[f"covered_{label}"] = (
                bool(prediction - radius <= actual_change <= prediction + radius)
                if np.isfinite(radius)
                else np.nan
            )
        outputs.append(output)
    return pd.DataFrame(outputs)


def target_scorecard(
    predictions: pd.DataFrame,
    minimum_observations: int = 8,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for entity, group in predictions.groupby("entity", sort=True):
        valid = group.dropna(
            subset=["actual_change", "candidate_prediction", "legacy_prediction"]
        )
        n = len(valid)
        naive_mae = float(valid["actual_change"].abs().mean()) if n else np.nan
        legacy_mae = (
            float((valid["actual_change"] - valid["legacy_prediction"]).abs().mean())
            if n
            else np.nan
        )
        candidate_mae = (
            float((valid["actual_change"] - valid["candidate_prediction"]).abs().mean())
            if n
            else np.nan
        )
        mase = candidate_mae / naive_mae if naive_mae > 0 else np.nan
        level_denominator = float(valid["target_value"].abs().sum()) if n else 0.0
        wape = (
            float(valid["absolute_target_error"].sum() / level_denominator * 100.0)
            if level_denominator > 0
            else np.nan
        )
        first = valid.iloc[0] if n else group.iloc[0]
        rows.append(
            {
                "entity": entity,
                "ticker": first.get("ticker"),
                "segment": first.get("segment", pd.NA),
                "target_name": first.get("target_name"),
                "observations": n,
                "naive_mae_change_units": naive_mae,
                "legacy_mae_change_units": legacy_mae,
                "candidate_mae_change_units": candidate_mae,
                "mase_vs_prior_year_no_change": mase,
                "improvement_vs_naive_change_units": naive_mae - candidate_mae,
                "improvement_vs_lag_change_units": legacy_mae - candidate_mae,
                "target_level_wape_pct": wape,
                "target_level_mae": float(valid["absolute_target_error"].mean()) if n else np.nan,
                "pi80_coverage": float(valid["covered_80"].mean()) if n else np.nan,
                "directional_hit_rate": float(valid["direction_correct"].eq(True).mean()) if n else np.nan,  # noqa: E712
                "model_applied_share": float(valid["model_applied"].mean()) if n else 0.0,
                "minimum_observations_pass": n >= minimum_observations,
            }
        )
    return pd.DataFrame(rows)


def target_summary(
    scorecard: pd.DataFrame,
    predictions: pd.DataFrame,
    validation: str,
) -> pd.DataFrame:
    valid = scorecard.dropna(subset=["mase_vs_prior_year_no_change"])
    rows = len(valid)
    return pd.DataFrame(
        [
            {
                "target_name": (
                    str(predictions["target_name"].iloc[0]) if len(predictions) else ""
                ),
                "validation": validation,
                "entities": rows,
                "forecasts": int(len(predictions)),
                "median_entity_mase": float(valid["mase_vs_prior_year_no_change"].median()) if rows else np.nan,
                "mean_entity_mase": float(valid["mase_vs_prior_year_no_change"].mean()) if rows else np.nan,
                "mean_candidate_mae_change_units": float(valid["candidate_mae_change_units"].mean()) if rows else np.nan,
                "mean_target_level_mae": float(valid["target_level_mae"].mean()) if rows else np.nan,
                "aggregate_target_wape_pct": (
                    float(predictions["absolute_target_error"].sum() / predictions["target_value"].abs().sum() * 100.0)
                    if len(predictions) and predictions["target_value"].abs().sum() > 0
                    else np.nan
                ),
                "naive_no_regression_share": float(valid["improvement_vs_naive_change_units"].ge(0).mean()) if rows else np.nan,
                "lag_no_regression_share": float(valid["improvement_vs_lag_change_units"].ge(0).mean()) if rows else np.nan,
                "mase_below_one_share": float(valid["mase_vs_prior_year_no_change"].lt(1).mean()) if rows else np.nan,
                "mean_pi80_coverage": float(valid["pi80_coverage"].mean()) if rows else np.nan,
                "mean_directional_hit_rate": float(valid["directional_hit_rate"].mean()) if rows else np.nan,
                "model_applied_share": float(valid["model_applied_share"].mean()) if rows else 0.0,
            }
        ]
    )


def target_gate(
    scorecard: pd.DataFrame,
    summary: pd.Series,
    *,
    parser_quality_gate: bool,
    expected_entities: int,
    severe_regression_threshold: float,
    minimum_observations: int,
) -> pd.DataFrame:
    valid = scorecard.dropna(subset=["mase_vs_prior_year_no_change"])
    severe = int(
        valid["improvement_vs_naive_change_units"]
        .lt(-severe_regression_threshold)
        .sum()
    )
    checks = {
        "entity_coverage_complete": len(valid) == expected_entities,
        "minimum_8_forecasts_per_entity": (
            len(valid) == expected_entities
            and valid["observations"].ge(minimum_observations).all()
        ),
        "median_mase_below_one": float(summary["median_entity_mase"]) < 1.0,
        "mean_mase_no_worse_than_one": float(summary["mean_entity_mase"]) <= 1.0,
        "naive_no_regression_share_at_least_80pct": float(summary["naive_no_regression_share"]) >= 0.80,
        "lag_no_regression_share_at_least_80pct": float(summary["lag_no_regression_share"]) >= 0.80,
        "severe_regression_count_zero": severe == 0,
        "pi80_between_75_85pct": (
            np.isfinite(summary["mean_pi80_coverage"])
            and 0.75 <= float(summary["mean_pi80_coverage"]) <= 0.85
        ),
        "directional_hit_at_least_65pct": (
            np.isfinite(summary["mean_directional_hit_rate"])
            and float(summary["mean_directional_hit_rate"]) >= 0.65
        ),
        "model_applied_all_rows": float(summary["model_applied_share"]) == 1.0,
        "parser_quality_gate": bool(parser_quality_gate),
    }
    return pd.DataFrame(
        [
            {
                "target_name": summary["target_name"],
                "expected_entities": expected_entities,
                "evaluable_entities": len(valid),
                "severe_regression_count": severe,
                **checks,
                "research_gate": all(bool(value) for value in checks.values()),
                "production_eligible": False,
            }
        ]
    )


def validate_target_panel(
    panel: pd.DataFrame,
    features: tuple[str, ...],
    *,
    parser_quality_gate: bool,
    expected_entities: int,
    quarters: int = 8,
    alpha: float = 12.0,
    minimum_training_observations: int = 16,
    clip_change: float = 30.0,
    severe_regression_threshold: float = 2.0,
) -> TargetValidationResult:
    time = _prediction_rows(
        panel,
        features,
        "TIME_HOLDOUT_8Q_PRIMARY",
        quarters=quarters,
        alpha=alpha,
        minimum_training_observations=minimum_training_observations,
        clip_change=clip_change,
    )
    loco = _prediction_rows(
        panel,
        features,
        "LOCO_TIME_SAFE_8Q_COLD_START",
        quarters=quarters,
        alpha=alpha,
        minimum_training_observations=minimum_training_observations,
        clip_change=clip_change,
    )
    time_score = target_scorecard(time, quarters)
    loco_score = target_scorecard(loco, quarters)
    time_summary = target_summary(time_score, time, "TIME_HOLDOUT_8Q_PRIMARY")
    loco_summary = target_summary(loco_score, loco, "LOCO_TIME_SAFE_8Q_COLD_START")
    summary = pd.concat([time_summary, loco_summary], ignore_index=True)
    gate = target_gate(
        time_score,
        time_summary.iloc[0],
        parser_quality_gate=parser_quality_gate,
        expected_entities=expected_entities,
        severe_regression_threshold=severe_regression_threshold,
        minimum_observations=quarters,
    )
    return TargetValidationResult(
        time, loco, time_score, loco_score, summary, gate
    )
