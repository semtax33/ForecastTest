from __future__ import annotations

import numpy as np
import pandas as pd


def mean_absolute_error(actual: pd.Series, forecast: pd.Series) -> float:
    valid = pd.DataFrame({"actual": actual, "forecast": forecast}).dropna()
    if valid.empty:
        return float("nan")
    return float((valid["actual"] - valid["forecast"]).abs().mean())


def mean_absolute_scaled_error(
    actual: pd.Series,
    forecast: pd.Series,
    naive_forecast: pd.Series,
) -> float:
    model_error = mean_absolute_error(actual, forecast)
    naive_error = mean_absolute_error(actual, naive_forecast)
    if not np.isfinite(model_error) or not np.isfinite(naive_error) or naive_error == 0:
        return float("nan")
    return model_error / naive_error


def absolute_percentage_error(actual: pd.Series, forecast: pd.Series) -> pd.Series:
    actual_values = pd.to_numeric(actual, errors="coerce")
    forecast_values = pd.to_numeric(forecast, errors="coerce")
    return (forecast_values / actual_values - 1.0).abs().where(actual_values.ne(0)) * 100.0
