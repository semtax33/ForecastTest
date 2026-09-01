from __future__ import annotations

import numpy as np
import pandas as pd


def _finite_sample_quantile(values: pd.Series, level: float) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if not len(clean):
        return np.nan
    # The research specification uses the empirical residual quantile rather
    # than the conservative finite-sample upper order statistic.  Linear
    # interpolation avoids the systematic over-width observed with tiny pools.
    return float(np.quantile(clean, level, method="linear"))


def pooled_conformal_interval(
    history: pd.DataFrame,
    ticker: str,
    prediction: float,
    structural_weight: float,
    level: float,
    allow_ticker_history: bool,
    group_window: int = 12,
    ticker_window: int = 8,
    ticker_prior: int = 8,
) -> dict[str, float | int]:
    valid = history.dropna(
        subset=["actual_log_yoy", "legacy_prediction", "raw_structural_prediction"]
    ).copy()
    valid["_prediction"] = valid["legacy_prediction"] + structural_weight * (
        valid["raw_structural_prediction"] - valid["legacy_prediction"]
    )
    valid["_absolute_residual"] = (
        valid["actual_log_yoy"] - valid["_prediction"]
    ).abs()
    valid = valid.sort_values(["quarter_ordinal", "ticker"])
    group = valid["_absolute_residual"].tail(group_window)
    if len(group) < 8:
        radius = np.nan
        group_radius = np.nan
        ticker_radius = np.nan
        reliability = 0.0
        ticker_observations = 0
    else:
        group_radius = _finite_sample_quantile(group, level)
        company = (
            valid.loc[valid["ticker"].eq(ticker), "_absolute_residual"].tail(ticker_window)
            if allow_ticker_history
            else pd.Series(dtype=float)
        )
        ticker_observations = len(company)
        ticker_radius = (
            _finite_sample_quantile(company, level) if ticker_observations >= 4 else np.nan
        )
        reliability = (
            ticker_observations / (ticker_observations + ticker_prior)
            if np.isfinite(ticker_radius)
            else 0.0
        )
        radius = (
            reliability * ticker_radius + (1.0 - reliability) * group_radius
            if np.isfinite(ticker_radius)
            else group_radius
        )
    return {
        "lower": prediction - radius if np.isfinite(radius) else np.nan,
        "upper": prediction + radius if np.isfinite(radius) else np.nan,
        "radius": radius,
        "group_radius": group_radius,
        "ticker_radius": ticker_radius,
        "ticker_reliability": reliability,
        "group_observations": len(group),
        "ticker_observations": ticker_observations,
    }


def interval_score(actual: float, lower: float, upper: float, level: float) -> float:
    if not all(np.isfinite(value) for value in (actual, lower, upper)):
        return np.nan
    alpha = 1.0 - level
    score = upper - lower
    if actual < lower:
        score += 2.0 / alpha * (lower - actual)
    elif actual > upper:
        score += 2.0 / alpha * (actual - upper)
    return float(score)
