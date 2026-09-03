from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.core.champion_gate import assess_against_naive
from equity_platform.core.forecast import ridge_predict
from equity_platform.sectors.industrials.aerospace_defense.noc.forecast import (
    FUNDED_BACKLOG_FEATURES,
    MARGIN_FEATURES,
    TOTAL_BACKLOG_FEATURES,
    build_noc_portability_forecast,
)
from equity_platform.sectors.industrials.common.margin import (
    clip_prediction_to_training_range,
)


DELIVERY_FEATURES = [
    "lag_delivery_yoy_pct",
    "output_price_yoy_pct",
    "lag_revenue_yoy_pct",
]


def _rename_noc_outputs(result: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    renamed: dict[str, pd.DataFrame] = {}
    for key, frame in result.items():
        converted = frame.copy()
        for column in converted.select_dtypes(include="object").columns:
            converted[column] = converted[column].replace("NOC", "GD")
        renamed[key.replace("noc_", "gd_")] = converted
    return renamed


def _aerospace_delivery_challenger(
    *,
    feature_panel: pd.DataFrame,
    delivery_history: pd.DataFrame,
    validation_start_period: str,
    minimum_training_quarters: int,
    ridge_penalty: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = feature_panel.loc[feature_panel["segment"].eq("aerospace")].copy()
    frame["quarter"] = pd.PeriodIndex(frame["period"], freq="Q")
    deliveries = delivery_history[["period", "deliveries_yoy_pct", "filing_date"]].copy()
    deliveries["quarter"] = pd.PeriodIndex(deliveries["period"], freq="Q") + 1
    deliveries = deliveries.rename(
        columns={
            "deliveries_yoy_pct": "lag_delivery_yoy_pct",
            "filing_date": "lag_delivery_available_at",
        }
    )
    frame = frame.merge(
        deliveries[["quarter", "lag_delivery_yoy_pct", "lag_delivery_available_at"]],
        on="quarter",
        how="left",
        validate="one_to_one",
    )
    frame["lag_delivery_available_at"] = pd.to_datetime(frame["lag_delivery_available_at"])
    frame["forecast_as_of"] = pd.to_datetime(frame["forecast_as_of"])
    frame["delivery_pit_available"] = frame["lag_delivery_available_at"].le(
        frame["forecast_as_of"]
    )
    start = pd.Period(validation_start_period, freq="Q")
    rows: list[dict[str, object]] = []
    for _, test in frame.loc[frame["quarter"].ge(start)].sort_values("quarter").iterrows():
        training = frame.loc[
            frame["quarter"].lt(test["quarter"])
            & frame["filing_date"].le(test["forecast_as_of"])
            & frame["historical_pit_input"]
            & frame["delivery_pit_available"]
            & ~frame["unforecastable_scope_change"]
        ].dropna(subset=DELIVERY_FEATURES + ["actual_revenue_growth_pct"])
        if len(training) < minimum_training_quarters or not bool(test["delivery_pit_available"]):
            continue
        growth = ridge_predict(
            training,
            test,
            features=DELIVERY_FEATURES,
            target="actual_revenue_growth_pct",
            penalty=ridge_penalty,
        )
        sales = float(test["prior_year_sales_usd"]) * (1.0 + growth / 100.0)
        rows.append(
            {
                "period": test["period"],
                "segment": "aerospace",
                "forecast_as_of": test["forecast_as_of"].date().isoformat(),
                "actual_available_at": pd.Timestamp(test["filing_date"]).date().isoformat(),
                "training_quarters": len(training),
                "route": "GULFSTREAM_DELIVERIES_PLUS_OUTPUT_PRICE_PREDECLARED_CHALLENGER",
                "actual_sales_usd": test["sales_usd"],
                "naive_prior_year_sales_usd": test["prior_year_sales_usd"],
                "predicted_sales_usd": sales,
                "predicted_growth_pct": growth,
                "lag_delivery_yoy_pct": test["lag_delivery_yoy_pct"],
                "output_price_yoy_pct": test["output_price_yoy_pct"],
                "actual_after_forecast": bool(
                    pd.Timestamp(test["filing_date"]) > test["forecast_as_of"]
                ),
                "historical_pit_input": bool(test["historical_pit_input"]),
                "delivery_pit_available": bool(test["delivery_pit_available"]),
                "revenue_level_ape_pct": abs(sales / float(test["sales_usd"]) - 1.0)
                * 100.0,
            }
        )
    walk = pd.DataFrame(rows)
    metrics = assess_against_naive(
        actual=walk["actual_sales_usd"],
        prediction=walk["predicted_sales_usd"],
        naive=walk["naive_prior_year_sales_usd"],
    )
    summary = pd.DataFrame(
        [
            {
                "segment": "aerospace",
                "validation_observations": len(walk),
                "route": walk.iloc[0]["route"],
                "revenue_mase": metrics.mase,
                "revenue_level_ape_pct": float(walk["revenue_level_ape_pct"].mean()),
                "revenue_champion_eligible": metrics.eligible,
                "cutoff_violations": int((~walk["actual_after_forecast"]).sum()),
                "delivery_anchor_coverage_pct": float(
                    walk["delivery_pit_available"].mean() * 100.0
                ),
                "predeclared_challenger_not_posthoc_selected": True,
            }
        ]
    )
    return walk, summary


def build_gd_forecast_research(
    *,
    history: pd.DataFrame,
    backlog: pd.DataFrame,
    delivery_history: pd.DataFrame,
    scope_audit: pd.DataFrame,
    industry_features: pd.DataFrame,
    forecast_origins: pd.DataFrame,
    validation_start_period: str,
    minimum_training_quarters: int,
    ridge_penalty: float,
) -> dict[str, pd.DataFrame]:
    empty_adjustments = pd.DataFrame(columns=["period", "segment"])
    base = build_noc_portability_forecast(
        history=history,
        backlog=backlog,
        scope_audit=scope_audit,
        program_adjustments=empty_adjustments,
        industry_features=industry_features,
        forecast_origins=forecast_origins,
        validation_start_period=validation_start_period,
        minimum_training_quarters=minimum_training_quarters,
        ridge_penalty=ridge_penalty,
    )
    result = _rename_noc_outputs(base)
    walk, summary = _aerospace_delivery_challenger(
        feature_panel=result["gd_portability_feature_panel"],
        delivery_history=delivery_history,
        validation_start_period=validation_start_period,
        minimum_training_quarters=minimum_training_quarters,
        ridge_penalty=ridge_penalty,
    )
    result["gd_aerospace_delivery_challenger_walk_forward"] = walk
    result["gd_aerospace_delivery_challenger_summary"] = summary
    return result


def build_gd_prospective_segment_forecast(
    *,
    feature_panel: pd.DataFrame,
    history: pd.DataFrame,
    backlog: pd.DataFrame,
    industry_features: pd.DataFrame,
    target_period: str,
    ridge_penalty: float,
) -> pd.DataFrame:
    target = pd.Period(target_period, freq="Q")
    target_industry = industry_features.loc[
        industry_features["period"].eq(target_period)
    ].set_index("segment")
    history = history.assign(quarter=pd.PeriodIndex(history["period"], freq="Q"))
    backlog = backlog.assign(quarter=pd.PeriodIndex(backlog["period"], freq="Q"))
    rows: list[dict[str, object]] = []
    panel = feature_panel.assign(quarter=pd.PeriodIndex(feature_panel["period"], freq="Q"))
    for segment, training in panel.groupby("segment"):
        training = training.loc[
            training["quarter"].lt(target)
            & training["historical_pit_input"]
            & ~training["unforecastable_scope_change"]
        ].dropna(subset=FUNDED_BACKLOG_FEATURES + ["actual_revenue_growth_pct"])
        latest_history = history.loc[
            history["segment"].eq(segment) & history["quarter"].eq(target - 1)
        ].iloc[0]
        prior_year = history.loc[
            history["segment"].eq(segment) & history["quarter"].eq(target - 4)
        ].iloc[0]
        latest_backlog = backlog.loc[
            backlog["segment"].eq(segment) & backlog["quarter"].eq(target - 1)
        ].iloc[0]
        backlog_prior = backlog.loc[
            backlog["segment"].eq(segment) & backlog["quarter"].eq(target - 5)
        ].iloc[0]
        industry = target_industry.loc[segment]
        test = pd.Series(
            {
                "lag_revenue_yoy_pct": latest_history["sales_usd"]
                / history.loc[
                    history["segment"].eq(segment)
                    & history["quarter"].eq(target - 5),
                    "sales_usd",
                ].iloc[0]
                * 100.0
                - 100.0,
                "lag_margin_pct": latest_history["operating_margin_pct"],
                "lag_backlog_yoy_pct": latest_backlog["backlog_usd"]
                / backlog_prior["backlog_usd"]
                * 100.0
                - 100.0,
                "lag_funded_backlog_yoy_pct": latest_backlog["funded_backlog_usd"]
                / backlog_prior["funded_backlog_usd"]
                * 100.0
                - 100.0,
                "lag_funded_share_pct": latest_backlog["funded_share_pct"],
                "output_price_yoy_pct": industry["output_price_yoy_pct"],
                "input_cost_yoy_pct": industry["dedicated_cost_yoy_pct"],
            }
        )
        test["output_input_spread_pct"] = (
            test["output_price_yoy_pct"] - test["input_cost_yoy_pct"]
        )
        funded_growth = ridge_predict(
            training,
            test,
            features=FUNDED_BACKLOG_FEATURES,
            target="actual_revenue_growth_pct",
            penalty=ridge_penalty,
        )
        total_growth = ridge_predict(
            training,
            test,
            features=TOTAL_BACKLOG_FEATURES,
            target="actual_revenue_growth_pct",
            penalty=ridge_penalty,
        )
        test["revenue_driver_pct"] = funded_growth
        margin_training = training.copy()
        margin_training["revenue_driver_pct"] = margin_training[
            "actual_revenue_growth_pct"
        ]
        raw_margin = ridge_predict(
            margin_training,
            test,
            features=MARGIN_FEATURES,
            target="operating_margin_pct",
            penalty=ridge_penalty,
        )
        margin, lower, upper, boundary = clip_prediction_to_training_range(
            raw_margin, margin_training["operating_margin_pct"]
        )
        sales = float(prior_year["sales_usd"]) * (1.0 + funded_growth / 100.0)
        rows.append(
            {
                "period": target_period,
                "segment": segment,
                "forecast_as_of": industry["forecast_as_of"],
                "prior_year_sales_usd": prior_year["sales_usd"],
                "predicted_sales_usd": sales,
                "predicted_revenue_growth_pct": funded_growth,
                "total_backlog_comparison_growth_pct": total_growth,
                "predicted_operating_margin_pct": margin,
                "raw_predicted_operating_margin_pct": raw_margin,
                "predicted_operating_profit_usd": sales * margin / 100.0,
                "margin_sanity_lower_pct": lower,
                "margin_sanity_upper_pct": upper,
                "margin_boundary_hit": boundary,
                "lag_funded_backlog_yoy_pct": test["lag_funded_backlog_yoy_pct"],
                "lag_funded_share_pct": test["lag_funded_share_pct"],
                "output_price_yoy_pct": test["output_price_yoy_pct"],
                "input_cost_yoy_pct": test["input_cost_yoy_pct"],
                "revenue_route": "STRUCTURAL_FUNDED_BACKLOG_CONVERSION_PRICE",
                "margin_route": "CONDITIONAL_REVENUE_MIX_PRICE_COST",
                "historical_pit_industry_input": bool(
                    industry["historical_pit_eligible"]
                ),
                "actual_not_yet_used": True,
                "terminal_input_allowed": False,
            }
        )
    return pd.DataFrame(rows).sort_values("segment").reset_index(drop=True)
