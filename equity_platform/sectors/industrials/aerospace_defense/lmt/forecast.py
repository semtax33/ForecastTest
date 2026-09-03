from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.core.forecast import ridge_predict
from equity_platform.core.champion_gate import assess_against_naive
from equity_platform.sectors.industrials.common.margin import (
    attach_explicit_program_loss_normalization,
    clip_prediction_to_training_range,
)


SEGMENTS = ("aeronautics", "missiles_fire_control", "rotary_mission_systems", "space")
REVENUE_ROUTES = {
    "aeronautics": ("STRUCTURAL_BACKLOG_DELIVERIES_PRICE", ["lag_backlog_yoy_pct", "lag_delivery_yoy_pct", "output_price_yoy_pct", "lag_revenue_yoy_pct"]),
    "missiles_fire_control": ("STRUCTURAL_BACKLOG_PRICE", ["lag_backlog_yoy_pct", "output_price_yoy_pct", "lag_revenue_yoy_pct"]),
    "rotary_mission_systems": ("STRUCTURAL_BACKLOG_HELICOPTER_DELIVERIES", ["lag_backlog_yoy_pct", "lag_delivery_yoy_pct", "output_price_yoy_pct", "lag_revenue_yoy_pct"]),
    "space": ("STRUCTURAL_BACKLOG_PRICE", ["lag_backlog_yoy_pct", "output_price_yoy_pct", "lag_revenue_yoy_pct"]),
}
MARGIN_ROUTES = {
    segment: ("CONDITIONAL_PROGRAM_MIX_PRICE_COST", ["revenue_driver_pct", "lag_margin_pct", "output_input_spread_pct", "lag_backlog_yoy_pct"])
    for segment in SEGMENTS
}


def _anchor_features(history: pd.DataFrame, backlog: pd.DataFrame, deliveries: pd.DataFrame) -> pd.DataFrame:
    sales = history[["period", "segment", "sales_usd"]].copy()
    sales["quarter"] = pd.PeriodIndex(sales["period"], freq="Q")
    sales = sales.sort_values(["segment", "quarter"])
    sales["ltm_sales_usd"] = sales.groupby("segment")["sales_usd"].transform(lambda values: values.rolling(4, min_periods=4).sum())
    anchor = backlog.merge(sales[["period", "segment", "ltm_sales_usd"]], on=["period", "segment"], how="left", validate="one_to_one")
    anchor["quarter"] = pd.PeriodIndex(anchor["period"], freq="Q")
    anchor = anchor.sort_values(["segment", "quarter"])
    anchor["backlog_yoy_pct"] = anchor.groupby("segment")["backlog_usd"].pct_change(4, fill_method=None) * 100.0
    anchor["backlog_qoq_pct"] = anchor.groupby("segment")["backlog_usd"].pct_change(fill_method=None) * 100.0
    anchor["backlog_to_ltm_sales"] = anchor["backlog_usd"] / anchor["ltm_sales_usd"]
    delivery = deliveries.copy()
    delivery["quarter"] = pd.PeriodIndex(delivery["period"], freq="Q")
    delivery = delivery.sort_values(["segment", "quarter"])
    delivery["delivery_yoy_pct"] = delivery.groupby("segment")["deliveries"].pct_change(4, fill_method=None) * 100.0
    delivery["delivery_yoy_pct"] = delivery["delivery_yoy_pct"].replace([np.inf, -np.inf], np.nan)
    anchor = anchor.merge(delivery[["period", "segment", "deliveries", "delivery_yoy_pct"]], on=["period", "segment"], how="left", validate="one_to_one")
    anchor["delivery_anchor_available"] = anchor["deliveries"].notna()
    anchor["nonfinancial_anchor_available"] = anchor["backlog_usd"].notna()
    return anchor[
        [
            "period", "segment", "backlog_usd", "backlog_yoy_pct", "backlog_qoq_pct",
            "backlog_to_ltm_sales", "deliveries", "delivery_yoy_pct",
            "delivery_anchor_available", "nonfinancial_anchor_available",
        ]
    ]


def _build_panel(*, history: pd.DataFrame, scope_audit: pd.DataFrame, program_losses: pd.DataFrame, backlog: pd.DataFrame, deliveries: pd.DataFrame, industry_features: pd.DataFrame, forecast_origins: pd.DataFrame) -> pd.DataFrame:
    frame = attach_explicit_program_loss_normalization(history, program_losses)
    frame["quarter"] = pd.PeriodIndex(frame["period"], freq="Q")
    frame = frame.sort_values(["segment", "quarter"])
    prior = frame[["quarter", "segment", "sales_usd", "operating_margin_pct"]].copy()
    prior["quarter"] = prior["quarter"] + 4
    prior = prior.rename(columns={"sales_usd": "prior_year_original_sales_usd", "operating_margin_pct": "prior_year_original_margin_pct"})
    frame = frame.merge(prior, on=["quarter", "segment"], how="left", validate="one_to_one")
    frame["actual_revenue_growth_pct"] = frame["sales_usd"] / frame["prior_year_original_sales_usd"] * 100.0 - 100.0
    frame["sequential_revenue_growth_pct"] = frame.groupby("segment")["sales_usd"].pct_change(fill_method=None) * 100.0
    anchor = _anchor_features(history, backlog, deliveries)
    frame = frame.merge(anchor, on=["period", "segment"], how="left", validate="one_to_one")
    lag_columns = [
        "quarter", "segment", "actual_revenue_growth_pct", "sequential_revenue_growth_pct", "model_operating_margin_pct",
        "backlog_yoy_pct", "backlog_qoq_pct", "backlog_to_ltm_sales", "delivery_yoy_pct",
        "nonfinancial_anchor_available", "delivery_anchor_available", "filing_date",
    ]
    lag = frame[lag_columns].copy()
    lag["quarter"] = lag["quarter"] + 1
    lag = lag.rename(columns={
        "actual_revenue_growth_pct": "lag_revenue_yoy_pct", "sequential_revenue_growth_pct": "lag_sequential_growth_pct",
        "model_operating_margin_pct": "lag_margin_pct", "backlog_yoy_pct": "lag_backlog_yoy_pct",
        "backlog_qoq_pct": "lag_backlog_qoq_pct", "backlog_to_ltm_sales": "lag_backlog_to_ltm_sales",
        "delivery_yoy_pct": "lag_delivery_yoy_pct", "nonfinancial_anchor_available": "lag_nonfinancial_anchor_available",
        "delivery_anchor_available": "lag_delivery_anchor_available", "filing_date": "lag_source_available_at",
    })
    frame = frame.merge(lag, on=["quarter", "segment"], how="left", validate="one_to_one")
    frame = frame.merge(forecast_origins, on="period", how="inner", validate="many_to_one", suffixes=("", "_origin"))
    frame = frame.merge(industry_features.drop(columns=["actual_available_at"], errors="ignore"), on=["period", "segment", "forecast_as_of"], how="inner", validate="one_to_one")
    frame["input_cost_yoy_pct"] = frame["dedicated_cost_yoy_pct"]
    frame["output_input_spread_pct"] = frame["output_price_yoy_pct"] - frame["input_cost_yoy_pct"]
    numeric_columns = frame.select_dtypes(include=[np.number]).columns
    frame[numeric_columns] = frame[numeric_columns].replace([np.inf, -np.inf], np.nan)
    changes = scope_audit.loc[scope_audit["material_scope_change"], ["period", "segment"]].drop_duplicates()
    change_keys = set(changes.itertuples(index=False, name=None))
    loss_keys = set(program_losses[["period", "segment"]].itertuples(index=False, name=None)) if not program_losses.empty else set()
    frame["unforecastable_scope_change"] = [(period, segment) in change_keys for period, segment in frame[["period", "segment"]].itertuples(index=False, name=None)]
    frame["unforecastable_program_loss"] = [(period, segment) in loss_keys for period, segment in frame[["period", "segment"]].itertuples(index=False, name=None)]
    frame["forecast_as_of"] = pd.to_datetime(frame["forecast_as_of"])
    frame["filing_date"] = pd.to_datetime(frame["filing_date"])
    frame["lag_source_available_at"] = pd.to_datetime(frame["lag_source_available_at"])
    frame["historical_pit_input"] = frame["historical_pit_eligible"].astype(bool) & frame["lag_source_available_at"].le(frame["forecast_as_of"]) & frame["filing_date"].gt(frame["forecast_as_of"])
    return frame.sort_values(["quarter", "segment"]).reset_index(drop=True)


def build_lmt_portability_forecast(*, history: pd.DataFrame, scope_audit: pd.DataFrame, program_losses: pd.DataFrame, backlog: pd.DataFrame, deliveries: pd.DataFrame, industry_features: pd.DataFrame, forecast_origins: pd.DataFrame, validation_start_period: str, minimum_training_quarters: int, ridge_penalty: float) -> dict[str, pd.DataFrame]:
    panel = _build_panel(history=history, scope_audit=scope_audit, program_losses=program_losses, backlog=backlog, deliveries=deliveries, industry_features=industry_features, forecast_origins=forecast_origins)
    start = pd.Period(validation_start_period, freq="Q")
    rows: list[dict[str, object]] = []
    for segment, group in panel.groupby("segment"):
        group = group.sort_values("quarter")
        revenue_route, revenue_features = REVENUE_ROUTES[segment]
        margin_route, margin_features = MARGIN_ROUTES[segment]
        for _, test in group.loc[group["quarter"].ge(start)].iterrows():
            base_training = group.loc[group["quarter"].lt(test["quarter"]) & group["filing_date"].le(test["forecast_as_of"]) & group["historical_pit_input"]].copy()
            revenue_training = base_training.loc[~base_training["unforecastable_scope_change"]].copy()
            margin_training = base_training.loc[~base_training["unforecastable_scope_change"]].copy()
            if min(len(revenue_training), len(margin_training)) < minimum_training_quarters:
                continue
            predicted_growth = ridge_predict(revenue_training, test, features=revenue_features, target="actual_revenue_growth_pct", penalty=ridge_penalty)
            predicted_sales = float(test["prior_year_original_sales_usd"]) * (1.0 + predicted_growth / 100.0)
            margin_training["revenue_driver_pct"] = margin_training["actual_revenue_growth_pct"]
            margin_test = test.copy()
            margin_test["revenue_driver_pct"] = predicted_growth
            raw_predicted_margin = ridge_predict(margin_training, margin_test, features=margin_features, target="model_operating_margin_pct", penalty=ridge_penalty)
            predicted_margin, margin_lower, margin_upper, margin_boundary_hit = clip_prediction_to_training_range(
                raw_predicted_margin, margin_training["model_operating_margin_pct"]
            )
            revenue_allowed = bool(not test["unforecastable_scope_change"])
            margin_allowed = bool(revenue_allowed and not test["unforecastable_program_loss"])
            rows.append({
                "period": test["period"], "segment": segment, "forecast_as_of": test["forecast_as_of"].date().isoformat(),
                "actual_available_at": test["filing_date"].date().isoformat(), "revenue_training_quarters": len(revenue_training),
                "margin_training_quarters": len(margin_training), "revenue_route": revenue_route, "margin_route": margin_route,
                "actual_sales_usd": test["sales_usd"], "naive_prior_year_sales_usd": test["prior_year_original_sales_usd"],
                "predicted_sales_usd": predicted_sales, "actual_revenue_growth_pct": test["actual_revenue_growth_pct"],
                "predicted_revenue_growth_pct": predicted_growth, "actual_operating_margin_pct": test["operating_margin_pct"],
                "naive_prior_year_margin_pct": test["prior_year_original_margin_pct"], "predicted_operating_margin_pct": predicted_margin,
                "raw_predicted_operating_margin_pct": raw_predicted_margin,
                "margin_sanity_lower_pct": margin_lower, "margin_sanity_upper_pct": margin_upper,
                "margin_boundary_hit": margin_boundary_hit,
                "actual_operating_profit_usd": test["operating_profit_usd"], "predicted_operating_profit_usd": predicted_sales * predicted_margin / 100.0,
                "revenue_absolute_error_usd": abs(test["sales_usd"] - predicted_sales),
                "revenue_naive_absolute_error_usd": abs(test["sales_usd"] - test["prior_year_original_sales_usd"]),
                "revenue_level_ape_pct": abs(predicted_sales / test["sales_usd"] - 1.0) * 100.0,
                "margin_absolute_error_pct_points": abs(test["operating_margin_pct"] - predicted_margin),
                "margin_naive_absolute_error_pct_points": abs(test["operating_margin_pct"] - test["prior_year_original_margin_pct"]),
                "lag_backlog_yoy_pct": test["lag_backlog_yoy_pct"], "lag_backlog_to_ltm_sales": test["lag_backlog_to_ltm_sales"],
                "lag_delivery_yoy_pct": test["lag_delivery_yoy_pct"], "output_price_yoy_pct": test["output_price_yoy_pct"],
                "input_cost_yoy_pct": test["input_cost_yoy_pct"], "lag_nonfinancial_anchor_available": bool(test["lag_nonfinancial_anchor_available"]),
                "lag_delivery_anchor_available": bool(test["lag_delivery_anchor_available"]), "historical_pit_input": bool(test["historical_pit_input"]),
                "actual_after_forecast": bool(test["filing_date"] > test["forecast_as_of"]), "unforecastable_scope_change": bool(test["unforecastable_scope_change"]),
                "unforecastable_program_loss": bool(test["unforecastable_program_loss"]), "revenue_performance_claim_allowed": revenue_allowed,
                "margin_performance_claim_allowed": margin_allowed, "performance_claim_allowed": margin_allowed,
                "revenue_and_margin_champions_separate": True,
            })
    walk = pd.DataFrame(rows).sort_values(["segment", "period"]).reset_index(drop=True)
    summary_rows: list[dict[str, object]] = []
    for segment, group in walk.groupby("segment"):
        revenue_clean = group.loc[group["revenue_performance_claim_allowed"]]
        margin_clean = group.loc[group["margin_performance_claim_allowed"]]
        revenue_metrics = assess_against_naive(
            actual=revenue_clean["actual_sales_usd"],
            prediction=revenue_clean["predicted_sales_usd"],
            naive=revenue_clean["naive_prior_year_sales_usd"],
        )
        margin_metrics = assess_against_naive(
            actual=margin_clean["actual_operating_margin_pct"],
            prediction=margin_clean["predicted_operating_margin_pct"],
            naive=margin_clean["naive_prior_year_margin_pct"],
        )
        summary_rows.append({
            "segment": segment, "validation_observations": len(group), "revenue_claim_observations": len(revenue_clean),
            "margin_claim_observations": len(margin_clean), "scope_change_rows": int(group["unforecastable_scope_change"].sum()),
            "program_loss_rows": int(group["unforecastable_program_loss"].sum()), "revenue_route": group.iloc[0]["revenue_route"],
            "margin_boundary_hits": int(group["margin_boundary_hit"].sum()),
            "margin_boundary_hit_pct": float(group["margin_boundary_hit"].mean() * 100.0),
            "structural_anchor_coverage_pct": float(group["lag_nonfinancial_anchor_available"].mean() * 100.0),
            "delivery_anchor_coverage_pct": float(group["lag_delivery_anchor_available"].mean() * 100.0),
            "revenue_mae_usd": revenue_metrics.mae, "revenue_mase": revenue_metrics.mase,
            "revenue_level_ape_pct": float(revenue_clean["revenue_level_ape_pct"].mean()),
            "revenue_champion_eligible": revenue_metrics.eligible,
            "margin_route": group.iloc[0]["margin_route"], "margin_mae_pct_points": margin_metrics.mae, "margin_mase": margin_metrics.mase,
            "margin_champion_eligible": margin_metrics.eligible,
            "joint_champion": bool(revenue_metrics.eligible and margin_metrics.eligible),
            "historical_pit_input_pct": float(group["historical_pit_input"].mean() * 100.0),
        })
    summary = pd.DataFrame(summary_rows).sort_values("segment").reset_index(drop=True)
    coverage = pd.DataFrame([{
        "segments": walk["segment"].nunique(), "validation_rows": len(walk), "validation_periods": walk["period"].nunique(),
        "historical_pit_rows": int(walk["historical_pit_input"].sum()), "cutoff_violations": int((~walk["actual_after_forecast"]).sum()),
        "revenue_champions": int(summary["revenue_champion_eligible"].sum()), "margin_champions": int(summary["margin_champion_eligible"].sum()),
        "joint_champions": int(summary["joint_champion"].sum()), "structural_revenue_routes": int(summary["revenue_route"].str.startswith("STRUCTURAL").sum()),
        "revenue_margin_authority_separated": True, "program_loss_margin_exclusions": int(walk["unforecastable_program_loss"].sum()),
        "margin_boundary_hits": int(walk["margin_boundary_hit"].sum()),
        "all_rows_at_margin_boundary": bool(walk.groupby("segment")["margin_boundary_hit"].all().any()),
    }])
    return {"lmt_portability_feature_panel": panel.drop(columns="quarter"), "lmt_portability_walk_forward": walk, "lmt_portability_summary": summary, "lmt_portability_coverage": coverage}
