from __future__ import annotations

import numpy as np
import pandas as pd

from ..v35.taxonomy import group_for_ticker


def standardize_revenue_predictions(
    predictions: pd.DataFrame,
    *,
    phase: int | None,
    subindustry: str | None,
    route_model: str | None,
    validation: str,
    production_model: str,
) -> pd.DataFrame:
    frame = predictions.copy()
    output = pd.DataFrame(
        {
            "ticker": frame["ticker"].astype(str),
            "quarter": frame["quarter"].astype(str),
            "phase": (
                pd.to_numeric(frame["phase"], errors="coerce").astype("Int64")
                if phase is None and "phase" in frame
                else phase
            ),
            "subindustry": (
                frame["subindustry"].astype(str)
                if subindustry is None and "subindustry" in frame
                else subindustry
            ),
            "forecast_target": "GAAP_REVENUE",
            "actual_value": pd.to_numeric(frame["revenue"], errors="coerce"),
            "prior_year_actual_value": pd.to_numeric(
                frame["prior_year_revenue"], errors="coerce"
            ),
            "actual_log_yoy": pd.to_numeric(
                frame["actual_log_yoy"], errors="coerce"
            ),
            "prediction_log_yoy": pd.to_numeric(
                frame["candidate_prediction"], errors="coerce"
            ),
            "predicted_value": pd.to_numeric(
                frame["candidate_revenue"], errors="coerce"
            ),
            "lower_80_log_yoy": pd.to_numeric(
                frame.get("lower_80_log_yoy"), errors="coerce"
            ),
            "upper_80_log_yoy": pd.to_numeric(
                frame.get("upper_80_log_yoy"), errors="coerce"
            ),
            "lower_95_log_yoy": pd.to_numeric(
                frame.get("lower_95_log_yoy"), errors="coerce"
            ),
            "upper_95_log_yoy": pd.to_numeric(
                frame.get("upper_95_log_yoy"), errors="coerce"
            ),
            "research_route_model": (
                frame["research_route_model"].astype(str)
                if route_model is None and "research_route_model" in frame
                else route_model
            ),
            "production_model": production_model,
            "validation": validation,
        }
    )
    output["absolute_error_log_points"] = (
        output["actual_log_yoy"] - output["prediction_log_yoy"]
    ).abs()
    output["absolute_percentage_error_pct"] = (
        output["predicted_value"] / output["actual_value"] - 1.0
    ).abs() * 100.0
    output["router_role"] = "STATIC_DISPATCH_ONLY_NO_META_MODEL"
    return output


def standardize_ebitda_predictions(
    predictions: pd.DataFrame,
    validation: str,
    route_model: str,
) -> pd.DataFrame:
    frame = predictions.copy()
    output = standardize_revenue_predictions(
        frame,
        phase=3,
        subindustry="midstream",
        route_model=route_model,
        validation=validation,
        production_model="RESEARCH_ONLY_NO_PRODUCTION_ROUTE",
    )
    output["forecast_target"] = "ADJUSTED_EBITDA_NON_GAAP"
    return output


def energy_sector_scorecard(common_predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (target, subindustry, model, validation), group in common_predictions.groupby(
        [
            "forecast_target",
            "subindustry",
            "research_route_model",
            "validation",
        ],
        dropna=False,
    ):
        valid = group.dropna(
            subset=["actual_value", "predicted_value", "actual_log_yoy", "prediction_log_yoy"]
        )
        by_ticker = []
        for _, ticker_rows in valid.groupby("ticker"):
            naive = float(ticker_rows["actual_log_yoy"].abs().mean())
            error = float(ticker_rows["absolute_error_log_points"].mean())
            by_ticker.append(error / naive if naive > 0 else np.nan)
        denominator = float(valid["actual_value"].abs().sum())
        wape = (
            float((valid["predicted_value"] - valid["actual_value"]).abs().sum())
            / denominator
            * 100.0
            if denominator > 0
            else np.nan
        )
        rows.append(
            {
                "forecast_target": target,
                "subindustry": subindustry,
                "research_route_model": model,
                "validation": validation,
                "tickers": int(valid["ticker"].nunique()),
                "forecasts": len(valid),
                "median_ticker_mase": float(pd.Series(by_ticker).median()),
                "mean_ticker_mase": float(pd.Series(by_ticker).mean()),
                "aggregate_wape_pct": wape,
                "median_ape_pct": float(
                    valid["absolute_percentage_error_pct"].median()
                ),
            }
        )
    return pd.DataFrame(rows)


def ep_subindustry(ticker: str) -> str:
    return f"ep_{group_for_ticker(ticker)}"
