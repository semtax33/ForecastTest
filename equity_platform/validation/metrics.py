from __future__ import annotations

import numpy as np
import pandas as pd


def log_to_yoy_pct(values: pd.Series | np.ndarray | float):
    return 100.0 * np.expm1(np.asarray(values, dtype=float) / 100.0)


def mean_absolute_error(actual, predicted) -> float:
    pairs = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    if pairs.empty:
        return float("nan")
    return float((pairs["actual"] - pairs["predicted"]).abs().mean())


def mean_absolute_yoy_pct_error(actual_log, predicted_log) -> float:
    actual = log_to_yoy_pct(actual_log)
    predicted = log_to_yoy_pct(predicted_log)
    return mean_absolute_error(actual, predicted)


def mase(actual, predicted, naive) -> float:
    numerator = mean_absolute_error(actual, predicted)
    denominator = mean_absolute_error(actual, naive)
    if not np.isfinite(denominator) or denominator <= 0:
        return float("nan")
    return float(numerator / denominator)


def enrich_revenue_level_errors(
    validation: pd.DataFrame,
    panel: pd.DataFrame,
    prediction_column: str = "prediction_log_yoy",
) -> pd.DataFrame:
    """Attach actual/predicted revenue and level APE to validation rows."""
    result = validation.copy()
    result["_quarter"] = pd.PeriodIndex(result["quarter"].astype(str), freq="Q")

    revenue = panel[["ticker", "quarter", "revenue"]].copy()
    revenue["_quarter"] = pd.PeriodIndex(revenue["quarter"].astype(str), freq="Q")
    revenue["revenue"] = pd.to_numeric(revenue["revenue"], errors="coerce")
    current = revenue[["ticker", "_quarter", "revenue"]].rename(
        columns={"revenue": "actual_revenue"}
    )
    prior = current.rename(
        columns={"_quarter": "_prior_quarter", "actual_revenue": "prior_year_revenue"}
    )

    result["_prior_quarter"] = result["_quarter"] - 4
    result = result.merge(current, on=["ticker", "_quarter"], how="left")
    result = result.merge(prior, on=["ticker", "_prior_quarter"], how="left")
    result["predicted_revenue"] = result["prior_year_revenue"] * np.exp(
        pd.to_numeric(result[prediction_column], errors="coerce") / 100.0
    )
    valid_actual = result["actual_revenue"].where(result["actual_revenue"] > 0)
    result["revenue_level_ape_pct"] = (
        (result["predicted_revenue"] / valid_actual - 1.0).abs() * 100.0
    )
    return result.drop(columns=["_quarter", "_prior_quarter"])


def _one_metric_row(
    frame: pd.DataFrame,
    ticker: str,
    split: str,
    prediction_column: str,
) -> dict[str, float | int | str]:
    return {
        "ticker": ticker,
        "evaluation_split": split,
        "observations": int(len(frame)),
        "mae_log_points": mean_absolute_error(
            frame["actual_log_yoy"], frame[prediction_column]
        ),
        "mae_yoy_pct_points": mean_absolute_yoy_pct_error(
            frame["actual_log_yoy"], frame[prediction_column]
        ),
        "mase": mase(
            frame["actual_log_yoy"],
            frame[prediction_column],
            frame["naive_log_yoy"],
        ),
        "revenue_level_mape_pct": float(frame["revenue_level_ape_pct"].mean()),
    }


def build_metric_table(
    validation: pd.DataFrame,
    prediction_column: str = "prediction_log_yoy",
) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    split_order = ["all", "train_validation", "untouched_test"]
    for split in split_order:
        selected = (
            validation
            if split == "all"
            else validation.loc[validation["evaluation_split"].eq(split)]
        )
        if selected.empty:
            continue
        rows.append(_one_metric_row(selected, "ALL", split, prediction_column))
        for ticker, group in selected.groupby("ticker", sort=True):
            rows.append(_one_metric_row(group, str(ticker), split, prediction_column))
    return pd.DataFrame(rows)

