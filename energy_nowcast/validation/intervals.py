from __future__ import annotations

import numpy as np
import pandas as pd


def weighted_quantile(values, quantile: float, weights) -> float:
    values_array = np.asarray(values, dtype=float)
    weights_array = np.asarray(weights, dtype=float)
    valid = np.isfinite(values_array) & np.isfinite(weights_array) & (weights_array > 0)
    values_array = values_array[valid]
    weights_array = weights_array[valid]
    if values_array.size == 0:
        return float("nan")
    order = np.argsort(values_array)
    values_array = values_array[order]
    weights_array = weights_array[order]
    cumulative = np.cumsum(weights_array) - 0.5 * weights_array
    cumulative /= weights_array.sum()
    return float(np.interp(quantile, cumulative, values_array))


def pooled_residual_quantiles(
    residuals: pd.DataFrame,
    ticker: str,
    lower_probability: float,
    upper_probability: float,
    ticker_weight: float = 0.5,
) -> tuple[float, float, int, int]:
    pooled = pd.to_numeric(residuals["residual_log_points"], errors="coerce").dropna()
    local = pd.to_numeric(
        residuals.loc[residuals["ticker"].eq(ticker), "residual_log_points"],
        errors="coerce",
    ).dropna()
    if pooled.empty:
        return float("nan"), float("nan"), 0, 0
    if local.empty:
        values = pooled.to_numpy()
        weights = np.full(len(pooled), 1.0 / len(pooled))
    else:
        values = np.concatenate([local.to_numpy(), pooled.to_numpy()])
        weights = np.concatenate(
            [
                np.full(len(local), ticker_weight / len(local)),
                np.full(len(pooled), (1.0 - ticker_weight) / len(pooled)),
            ]
        )
    return (
        weighted_quantile(values, lower_probability, weights),
        weighted_quantile(values, upper_probability, weights),
        int(len(local)),
        int(len(pooled)),
    )


def add_walk_forward_intervals(
    validation: pd.DataFrame,
    levels: tuple[float, ...] = (0.80, 0.95),
    ticker_weight: float = 0.5,
    min_history: int = 4,
) -> pd.DataFrame:
    result = validation.sort_values(["quarter", "ticker"]).copy()
    result["residual_log_points"] = (
        result["actual_log_yoy"] - result["prediction_log_yoy"]
    )
    training = result.loc[result["evaluation_split"].eq("train_validation")].copy()

    for level in levels:
        label = int(round(level * 100))
        result[f"lower_{label}_log_yoy"] = np.nan
        result[f"upper_{label}_log_yoy"] = np.nan
        result[f"covered_{label}"] = pd.NA

    for index, row in result.iterrows():
        history = training.loc[
            training["quarter"].astype(str) < str(row["quarter"])
        ]
        if len(history) < min_history:
            continue
        for level in levels:
            tail = (1.0 - level) / 2.0
            lower_error, upper_error, _, _ = pooled_residual_quantiles(
                history,
                str(row["ticker"]),
                tail,
                1.0 - tail,
                ticker_weight,
            )
            label = int(round(level * 100))
            lower = float(row["prediction_log_yoy"] + lower_error)
            upper = float(row["prediction_log_yoy"] + upper_error)
            result.at[index, f"lower_{label}_log_yoy"] = lower
            result.at[index, f"upper_{label}_log_yoy"] = upper
            result.at[index, f"covered_{label}"] = bool(
                lower <= float(row["actual_log_yoy"]) <= upper
            )
    return result


def prediction_intervals_for_nowcast(
    nowcast: pd.DataFrame,
    validation: pd.DataFrame,
    levels: tuple[float, ...] = (0.80, 0.95),
    ticker_weight: float = 0.5,
) -> pd.DataFrame:
    result = nowcast.copy()
    residuals = validation.copy()
    residuals["residual_log_points"] = (
        residuals["actual_log_yoy"] - residuals["prediction_log_yoy"]
    )
    for level in levels:
        label = int(round(level * 100))
        lower_logs: list[float] = []
        upper_logs: list[float] = []
        lower_revenues: list[float] = []
        upper_revenues: list[float] = []
        ticker_counts: list[int] = []
        pooled_counts: list[int] = []
        for _, row in result.iterrows():
            tail = (1.0 - level) / 2.0
            lower_error, upper_error, ticker_n, pooled_n = pooled_residual_quantiles(
                residuals,
                str(row["ticker"]),
                tail,
                1.0 - tail,
                ticker_weight,
            )
            point_log = float(row["predicted_revenue_log_yoy"])
            lower_log = point_log + lower_error
            upper_log = point_log + upper_error
            point_revenue = float(row["predicted_revenue_B"])
            base_revenue = point_revenue / np.exp(point_log / 100.0)
            lower_logs.append(lower_log)
            upper_logs.append(upper_log)
            lower_revenues.append(base_revenue * np.exp(lower_log / 100.0))
            upper_revenues.append(base_revenue * np.exp(upper_log / 100.0))
            ticker_counts.append(ticker_n)
            pooled_counts.append(pooled_n)
        result[f"lower_{label}_log_yoy"] = lower_logs
        result[f"upper_{label}_log_yoy"] = upper_logs
        result[f"lower_{label}_revenue_B"] = lower_revenues
        result[f"upper_{label}_revenue_B"] = upper_revenues
        result[f"interval_ticker_residual_n"] = ticker_counts
        result[f"interval_pooled_residual_n"] = pooled_counts
    return result
