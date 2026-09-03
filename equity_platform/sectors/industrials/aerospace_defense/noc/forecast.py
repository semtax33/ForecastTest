from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.core.champion_gate import assess_against_naive
from equity_platform.core.forecast import ridge_predict
from equity_platform.sectors.industrials.common.margin import clip_prediction_to_training_range


SEGMENTS = (
    "aeronautics_systems",
    "defense_systems",
    "mission_systems",
    "space_systems",
)
TOTAL_BACKLOG_FEATURES = [
    "lag_backlog_yoy_pct",
    "output_price_yoy_pct",
    "lag_revenue_yoy_pct",
]
FUNDED_BACKLOG_FEATURES = [
    "lag_funded_backlog_yoy_pct",
    "lag_funded_share_pct",
    "output_price_yoy_pct",
    "lag_revenue_yoy_pct",
]
MARGIN_FEATURES = [
    "revenue_driver_pct",
    "lag_margin_pct",
    "output_input_spread_pct",
    "lag_funded_share_pct",
]


def _build_panel(
    *,
    history: pd.DataFrame,
    backlog: pd.DataFrame,
    scope_audit: pd.DataFrame,
    program_adjustments: pd.DataFrame,
    industry_features: pd.DataFrame,
    forecast_origins: pd.DataFrame,
) -> pd.DataFrame:
    frame = history.copy()
    frame["quarter"] = pd.PeriodIndex(frame["period"], freq="Q")
    frame = frame.sort_values(["segment", "quarter"])
    prior = frame[["quarter", "segment", "sales_usd", "operating_margin_pct"]].copy()
    prior["quarter"] = prior["quarter"] + 4
    prior = prior.rename(
        columns={
            "sales_usd": "prior_year_sales_usd",
            "operating_margin_pct": "prior_year_margin_pct",
        }
    )
    frame = frame.merge(prior, on=["quarter", "segment"], how="left", validate="one_to_one")
    frame["actual_revenue_growth_pct"] = frame["sales_usd"] / frame["prior_year_sales_usd"] * 100.0 - 100.0

    anchors = backlog.copy()
    anchors["quarter"] = pd.PeriodIndex(anchors["period"], freq="Q")
    anchors = anchors.sort_values(["segment", "quarter"])
    anchors["backlog_yoy_pct"] = anchors.groupby("segment")["backlog_usd"].pct_change(4, fill_method=None) * 100.0
    anchors["funded_backlog_yoy_pct"] = anchors.groupby("segment")["funded_backlog_usd"].pct_change(4, fill_method=None) * 100.0
    ltm = frame[["period", "segment", "sales_usd"]].copy()
    ltm["ltm_sales_usd"] = ltm.groupby("segment")["sales_usd"].transform(lambda values: values.rolling(4, min_periods=4).sum())
    anchors = anchors.merge(ltm[["period", "segment", "ltm_sales_usd"]], on=["period", "segment"], how="left", validate="one_to_one")
    anchors["backlog_to_ltm_sales"] = anchors["backlog_usd"] / anchors["ltm_sales_usd"]
    frame = frame.merge(
        anchors[[
            "period", "segment", "backlog_usd", "funded_backlog_usd", "unfunded_backlog_usd",
            "funded_share_pct", "backlog_yoy_pct", "funded_backlog_yoy_pct", "backlog_to_ltm_sales",
        ]],
        on=["period", "segment"],
        how="left",
        validate="one_to_one",
    )
    lag = frame[[
        "quarter", "segment", "actual_revenue_growth_pct", "operating_margin_pct",
        "backlog_yoy_pct", "funded_backlog_yoy_pct", "funded_share_pct", "backlog_to_ltm_sales",
        "filing_date",
    ]].copy()
    lag["quarter"] = lag["quarter"] + 1
    lag = lag.rename(
        columns={
            "actual_revenue_growth_pct": "lag_revenue_yoy_pct",
            "operating_margin_pct": "lag_margin_pct",
            "backlog_yoy_pct": "lag_backlog_yoy_pct",
            "funded_backlog_yoy_pct": "lag_funded_backlog_yoy_pct",
            "funded_share_pct": "lag_funded_share_pct",
            "backlog_to_ltm_sales": "lag_backlog_to_ltm_sales",
            "filing_date": "lag_source_available_at",
        }
    )
    frame = frame.merge(lag, on=["quarter", "segment"], how="left", validate="one_to_one")
    frame = frame.merge(forecast_origins, on="period", how="inner", validate="many_to_one", suffixes=("", "_origin"))
    frame = frame.merge(
        industry_features.drop(columns=["actual_available_at"], errors="ignore"),
        on=["period", "segment", "forecast_as_of"],
        how="inner",
        validate="one_to_one",
    )
    frame["input_cost_yoy_pct"] = frame["dedicated_cost_yoy_pct"]
    frame["output_input_spread_pct"] = frame["output_price_yoy_pct"] - frame["input_cost_yoy_pct"]
    change_keys = set(
        scope_audit.loc[scope_audit["material_scope_change"], ["period", "segment"]]
        .itertuples(index=False, name=None)
    )
    program_keys = set(
        program_adjustments[["period", "segment"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    keys = list(frame[["period", "segment"]].itertuples(index=False, name=None))
    frame["unforecastable_scope_change"] = [key in change_keys for key in keys]
    frame["unforecastable_program_adjustment"] = [key in program_keys for key in keys]
    frame["forecast_as_of"] = pd.to_datetime(frame["forecast_as_of"])
    frame["filing_date"] = pd.to_datetime(frame["filing_date"])
    frame["lag_source_available_at"] = pd.to_datetime(frame["lag_source_available_at"])
    frame["historical_pit_input"] = (
        frame["historical_pit_eligible"].astype(bool)
        & frame["lag_source_available_at"].le(frame["forecast_as_of"])
        & frame["filing_date"].gt(frame["forecast_as_of"])
    )
    numeric = frame.select_dtypes(include=[np.number]).columns
    frame[numeric] = frame[numeric].replace([np.inf, -np.inf], np.nan)
    return frame.sort_values(["quarter", "segment"]).reset_index(drop=True)


def build_noc_portability_forecast(
    *,
    history: pd.DataFrame,
    backlog: pd.DataFrame,
    scope_audit: pd.DataFrame,
    program_adjustments: pd.DataFrame,
    industry_features: pd.DataFrame,
    forecast_origins: pd.DataFrame,
    validation_start_period: str,
    minimum_training_quarters: int,
    ridge_penalty: float,
) -> dict[str, pd.DataFrame]:
    panel = _build_panel(
        history=history,
        backlog=backlog,
        scope_audit=scope_audit,
        program_adjustments=program_adjustments,
        industry_features=industry_features,
        forecast_origins=forecast_origins,
    )
    start = pd.Period(validation_start_period, freq="Q")
    rows: list[dict[str, object]] = []
    for segment, group in panel.groupby("segment"):
        group = group.sort_values("quarter")
        for _, test in group.loc[group["quarter"].ge(start)].iterrows():
            training = group.loc[
                group["quarter"].lt(test["quarter"])
                & group["filing_date"].le(test["forecast_as_of"])
                & group["historical_pit_input"]
                & ~group["unforecastable_scope_change"]
            ].copy()
            if len(training) < minimum_training_quarters:
                continue
            total_growth = ridge_predict(
                training,
                test,
                features=TOTAL_BACKLOG_FEATURES,
                target="actual_revenue_growth_pct",
                penalty=ridge_penalty,
            )
            funded_growth = ridge_predict(
                training,
                test,
                features=FUNDED_BACKLOG_FEATURES,
                target="actual_revenue_growth_pct",
                penalty=ridge_penalty,
            )
            total_sales = float(test["prior_year_sales_usd"]) * (1.0 + total_growth / 100.0)
            funded_sales = float(test["prior_year_sales_usd"]) * (1.0 + funded_growth / 100.0)
            margin_training = training.copy()
            margin_training["revenue_driver_pct"] = margin_training["actual_revenue_growth_pct"]
            margin_test = test.copy()
            margin_test["revenue_driver_pct"] = funded_growth
            raw_margin = ridge_predict(
                margin_training,
                margin_test,
                features=MARGIN_FEATURES,
                target="operating_margin_pct",
                penalty=ridge_penalty,
            )
            predicted_margin, margin_lower, margin_upper, boundary_hit = clip_prediction_to_training_range(
                raw_margin, margin_training["operating_margin_pct"]
            )
            revenue_allowed = bool(not test["unforecastable_scope_change"])
            margin_allowed = bool(revenue_allowed and not test["unforecastable_program_adjustment"])
            rows.append(
                {
                    "period": test["period"],
                    "segment": segment,
                    "forecast_as_of": test["forecast_as_of"].date().isoformat(),
                    "actual_available_at": test["filing_date"].date().isoformat(),
                    "training_quarters": len(training),
                    "revenue_route": "STRUCTURAL_FUNDED_BACKLOG_CONVERSION_PRICE",
                    "comparison_revenue_route": "STRUCTURAL_TOTAL_BACKLOG_PRICE",
                    "margin_route": "CONDITIONAL_REVENUE_MIX_PRICE_COST",
                    "actual_sales_usd": test["sales_usd"],
                    "naive_prior_year_sales_usd": test["prior_year_sales_usd"],
                    "total_backlog_predicted_sales_usd": total_sales,
                    "funded_backlog_predicted_sales_usd": funded_sales,
                    "actual_revenue_growth_pct": test["actual_revenue_growth_pct"],
                    "total_backlog_predicted_growth_pct": total_growth,
                    "funded_backlog_predicted_growth_pct": funded_growth,
                    "actual_operating_margin_pct": test["operating_margin_pct"],
                    "naive_prior_year_margin_pct": test["prior_year_margin_pct"],
                    "predicted_operating_margin_pct": predicted_margin,
                    "raw_predicted_operating_margin_pct": raw_margin,
                    "margin_sanity_lower_pct": margin_lower,
                    "margin_sanity_upper_pct": margin_upper,
                    "margin_boundary_hit": boundary_hit,
                    "actual_operating_profit_usd": test["operating_profit_usd"],
                    "predicted_operating_profit_usd": funded_sales * predicted_margin / 100.0,
                    "funded_revenue_absolute_error_usd": abs(test["sales_usd"] - funded_sales),
                    "total_revenue_absolute_error_usd": abs(test["sales_usd"] - total_sales),
                    "revenue_naive_absolute_error_usd": abs(test["sales_usd"] - test["prior_year_sales_usd"]),
                    "funded_revenue_level_ape_pct": abs(funded_sales / test["sales_usd"] - 1.0) * 100.0,
                    "margin_absolute_error_pct_points": abs(test["operating_margin_pct"] - predicted_margin),
                    "margin_naive_absolute_error_pct_points": abs(test["operating_margin_pct"] - test["prior_year_margin_pct"]),
                    "lag_backlog_yoy_pct": test["lag_backlog_yoy_pct"],
                    "lag_funded_backlog_yoy_pct": test["lag_funded_backlog_yoy_pct"],
                    "lag_funded_share_pct": test["lag_funded_share_pct"],
                    "output_price_yoy_pct": test["output_price_yoy_pct"],
                    "input_cost_yoy_pct": test["input_cost_yoy_pct"],
                    "historical_pit_input": bool(test["historical_pit_input"]),
                    "actual_after_forecast": bool(test["filing_date"] > test["forecast_as_of"]),
                    "unforecastable_scope_change": bool(test["unforecastable_scope_change"]),
                    "unforecastable_program_adjustment": bool(test["unforecastable_program_adjustment"]),
                    "revenue_performance_claim_allowed": revenue_allowed,
                    "margin_performance_claim_allowed": margin_allowed,
                    "revenue_margin_authority_separate": True,
                }
            )
    walk = pd.DataFrame(rows).sort_values(["segment", "period"]).reset_index(drop=True)
    summaries: list[dict[str, object]] = []
    for segment, group in walk.groupby("segment"):
        revenue = group.loc[group["revenue_performance_claim_allowed"]]
        margin = group.loc[group["margin_performance_claim_allowed"]]
        funded_metrics = assess_against_naive(
            actual=revenue["actual_sales_usd"],
            prediction=revenue["funded_backlog_predicted_sales_usd"],
            naive=revenue["naive_prior_year_sales_usd"],
        )
        total_metrics = assess_against_naive(
            actual=revenue["actual_sales_usd"],
            prediction=revenue["total_backlog_predicted_sales_usd"],
            naive=revenue["naive_prior_year_sales_usd"],
        )
        margin_metrics = assess_against_naive(
            actual=margin["actual_operating_margin_pct"],
            prediction=margin["predicted_operating_margin_pct"],
            naive=margin["naive_prior_year_margin_pct"],
        )
        summaries.append(
            {
                "segment": segment,
                "validation_observations": len(group),
                "revenue_claim_observations": len(revenue),
                "margin_claim_observations": len(margin),
                "scope_change_rows": int(group["unforecastable_scope_change"].sum()),
                "program_adjustment_rows": int(group["unforecastable_program_adjustment"].sum()),
                "revenue_route": group.iloc[0]["revenue_route"],
                "funded_backlog_revenue_mase": funded_metrics.mase,
                "total_backlog_revenue_mase": total_metrics.mase,
                "funded_vs_total_mase_improvement_pct": (total_metrics.mase - funded_metrics.mase) / total_metrics.mase * 100.0,
                "funded_backlog_revenue_level_ape_pct": float(revenue["funded_revenue_level_ape_pct"].mean()),
                "funded_backlog_revenue_champion_eligible": funded_metrics.eligible,
                "total_backlog_revenue_champion_eligible": total_metrics.eligible,
                "margin_route": group.iloc[0]["margin_route"],
                "margin_mase": margin_metrics.mase,
                "margin_champion_eligible": margin_metrics.eligible,
                "joint_champion": bool(funded_metrics.eligible and margin_metrics.eligible),
                "margin_boundary_hits": int(group["margin_boundary_hit"].sum()),
                "margin_boundary_hit_pct": float(group["margin_boundary_hit"].mean() * 100.0),
                "funded_backlog_anchor_coverage_pct": float(group["lag_funded_backlog_yoy_pct"].notna().mean() * 100.0),
                "historical_pit_input_pct": float(group["historical_pit_input"].mean() * 100.0),
            }
        )
    summary = pd.DataFrame(summaries).sort_values("segment").reset_index(drop=True)
    coverage = pd.DataFrame(
        [
            {
                "segments": walk["segment"].nunique(),
                "validation_rows": len(walk),
                "validation_periods": walk["period"].nunique(),
                "historical_pit_rows": int(walk["historical_pit_input"].sum()),
                "cutoff_violations": int((~walk["actual_after_forecast"]).sum()),
                "funded_backlog_revenue_champions": int(summary["funded_backlog_revenue_champion_eligible"].sum()),
                "total_backlog_revenue_champions": int(summary["total_backlog_revenue_champion_eligible"].sum()),
                "margin_champions": int(summary["margin_champion_eligible"].sum()),
                "joint_champions": int(summary["joint_champion"].sum()),
                "funded_backlog_improved_segments": int(summary["funded_vs_total_mase_improvement_pct"].gt(0).sum()),
                "margin_boundary_hits": int(walk["margin_boundary_hit"].sum()),
                "all_rows_at_margin_boundary": bool(walk.groupby("segment")["margin_boundary_hit"].all().any()),
                "revenue_margin_authority_separated": True,
            }
        ]
    )
    expected = (
        history.assign(quarter=pd.PeriodIndex(history["period"], freq="Q"))
        .loc[lambda frame: frame["quarter"].ge(start)]
        .groupby("segment", as_index=False)
        .agg(expected_validation_rows=("period", "nunique"))
    )
    observed = walk.groupby("segment", as_index=False).agg(model_validation_rows=("period", "nunique"))
    segment_coverage = expected.merge(observed, on="segment", how="left")
    segment_coverage["model_validation_rows"] = segment_coverage["model_validation_rows"].fillna(0).astype(int)
    segment_coverage["missing_model_rows"] = segment_coverage["expected_validation_rows"] - segment_coverage["model_validation_rows"]
    segment_coverage["coverage_status"] = np.where(
        segment_coverage["missing_model_rows"].eq(0),
        "COMPLETE",
        "INSUFFICIENT_SCOPE_STABLE_TRAINING_HISTORY",
    )
    segment_coverage["missing_rows_imputed"] = False
    company = _build_company_forecast(
        history=history,
        backlog=backlog,
        program_adjustments=program_adjustments,
        industry_features=industry_features,
        forecast_origins=forecast_origins,
        validation_start_period=validation_start_period,
        minimum_training_quarters=minimum_training_quarters,
        ridge_penalty=ridge_penalty,
    )
    return {
        "noc_portability_feature_panel": panel.drop(columns="quarter"),
        "noc_portability_walk_forward": walk,
        "noc_portability_summary": summary,
        "noc_portability_coverage": coverage,
        "noc_segment_model_coverage": segment_coverage,
        **company,
    }


def _build_company_forecast(
    *,
    history: pd.DataFrame,
    backlog: pd.DataFrame,
    program_adjustments: pd.DataFrame,
    industry_features: pd.DataFrame,
    forecast_origins: pd.DataFrame,
    validation_start_period: str,
    minimum_training_quarters: int,
    ridge_penalty: float,
) -> dict[str, pd.DataFrame]:
    frame = history.groupby("period", as_index=False).agg(
        sales_usd=("sales_usd", "sum"),
        operating_profit_usd=("operating_profit_usd", "sum"),
        filing_date=("filing_date", "max"),
    )
    frame["operating_margin_pct"] = frame["operating_profit_usd"] / frame["sales_usd"] * 100.0
    frame["quarter"] = pd.PeriodIndex(frame["period"], freq="Q")
    frame = frame.sort_values("quarter")
    prior = frame[["quarter", "sales_usd", "operating_margin_pct"]].copy()
    prior["quarter"] = prior["quarter"] + 4
    prior = prior.rename(columns={"sales_usd": "prior_year_sales_usd", "operating_margin_pct": "prior_year_margin_pct"})
    frame = frame.merge(prior, on="quarter", how="left", validate="one_to_one")
    frame["actual_revenue_growth_pct"] = frame["sales_usd"] / frame["prior_year_sales_usd"] * 100.0 - 100.0
    anchors = backlog.groupby("period", as_index=False).agg(
        backlog_usd=("backlog_usd", "sum"),
        funded_backlog_usd=("funded_backlog_usd", "sum"),
        unfunded_backlog_usd=("unfunded_backlog_usd", "sum"),
        backlog_filing_date=("filing_date", "max"),
    )
    anchors["quarter"] = pd.PeriodIndex(anchors["period"], freq="Q")
    anchors["funded_share_pct"] = anchors["funded_backlog_usd"] / anchors["backlog_usd"] * 100.0
    anchors["backlog_yoy_pct"] = anchors["backlog_usd"].pct_change(4, fill_method=None) * 100.0
    anchors["funded_backlog_yoy_pct"] = anchors["funded_backlog_usd"].pct_change(4, fill_method=None) * 100.0
    frame = frame.merge(anchors.drop(columns="quarter"), on="period", how="left", validate="one_to_one")
    lag = frame[[
        "quarter", "actual_revenue_growth_pct", "operating_margin_pct", "backlog_yoy_pct",
        "funded_backlog_yoy_pct", "funded_share_pct", "filing_date",
    ]].copy()
    lag["quarter"] = lag["quarter"] + 1
    lag = lag.rename(columns={
        "actual_revenue_growth_pct": "lag_revenue_yoy_pct",
        "operating_margin_pct": "lag_margin_pct",
        "backlog_yoy_pct": "lag_backlog_yoy_pct",
        "funded_backlog_yoy_pct": "lag_funded_backlog_yoy_pct",
        "funded_share_pct": "lag_funded_share_pct",
        "filing_date": "lag_source_available_at",
    })
    frame = frame.merge(lag, on="quarter", how="left", validate="one_to_one")
    frame = frame.merge(forecast_origins, on="period", how="inner", validate="one_to_one")
    industry = industry_features.groupby(["period", "forecast_as_of"], as_index=False).agg(
        output_price_yoy_pct=("output_price_yoy_pct", "mean"),
        dedicated_cost_yoy_pct=("dedicated_cost_yoy_pct", "mean"),
        historical_pit_eligible=("historical_pit_eligible", "all"),
    )
    frame = frame.merge(industry, on=["period", "forecast_as_of"], how="inner", validate="one_to_one")
    frame["output_input_spread_pct"] = frame["output_price_yoy_pct"] - frame["dedicated_cost_yoy_pct"]
    frame["forecast_as_of"] = pd.to_datetime(frame["forecast_as_of"])
    frame["filing_date"] = pd.to_datetime(frame["filing_date"])
    frame["lag_source_available_at"] = pd.to_datetime(frame["lag_source_available_at"])
    frame["historical_pit_input"] = (
        frame["historical_pit_eligible"].astype(bool)
        & frame["lag_source_available_at"].le(frame["forecast_as_of"])
        & frame["filing_date"].gt(frame["forecast_as_of"])
    )
    numeric = frame.select_dtypes(include=[np.number]).columns
    frame[numeric] = frame[numeric].replace([np.inf, -np.inf], np.nan)
    event_periods = set(program_adjustments["period"].unique())
    rows: list[dict[str, object]] = []
    start = pd.Period(validation_start_period, freq="Q")
    for _, test in frame.loc[frame["quarter"].ge(start)].iterrows():
        training = frame.loc[
            frame["quarter"].lt(test["quarter"])
            & frame["filing_date"].le(test["forecast_as_of"])
            & frame["historical_pit_input"]
        ].copy()
        if len(training) < minimum_training_quarters:
            continue
        total_growth = ridge_predict(training, test, features=TOTAL_BACKLOG_FEATURES, target="actual_revenue_growth_pct", penalty=ridge_penalty)
        funded_growth = ridge_predict(training, test, features=FUNDED_BACKLOG_FEATURES, target="actual_revenue_growth_pct", penalty=ridge_penalty)
        total_sales = float(test["prior_year_sales_usd"]) * (1.0 + total_growth / 100.0)
        funded_sales = float(test["prior_year_sales_usd"]) * (1.0 + funded_growth / 100.0)
        margin_training = training.copy()
        margin_training["revenue_driver_pct"] = margin_training["actual_revenue_growth_pct"]
        margin_test = test.copy()
        margin_test["revenue_driver_pct"] = funded_growth
        raw_margin = ridge_predict(margin_training, margin_test, features=MARGIN_FEATURES, target="operating_margin_pct", penalty=ridge_penalty)
        predicted_margin, lower, upper, boundary = clip_prediction_to_training_range(raw_margin, margin_training["operating_margin_pct"])
        rows.append({
            "period": test["period"], "company": "NOC",
            "forecast_as_of": test["forecast_as_of"].date().isoformat(),
            "actual_available_at": test["filing_date"].date().isoformat(),
            "training_quarters": len(training), "actual_sales_usd": test["sales_usd"],
            "naive_prior_year_sales_usd": test["prior_year_sales_usd"],
            "funded_backlog_predicted_sales_usd": funded_sales,
            "total_backlog_predicted_sales_usd": total_sales,
            "actual_operating_margin_pct": test["operating_margin_pct"],
            "naive_prior_year_margin_pct": test["prior_year_margin_pct"],
            "predicted_operating_margin_pct": predicted_margin,
            "margin_sanity_lower_pct": lower, "margin_sanity_upper_pct": upper,
            "margin_boundary_hit": boundary,
            "explicit_program_adjustment_period": test["period"] in event_periods,
            "revenue_performance_claim_allowed": True,
            "margin_performance_claim_allowed": test["period"] not in event_periods,
            "historical_pit_input": bool(test["historical_pit_input"]),
            "actual_after_forecast": bool(test["filing_date"] > test["forecast_as_of"]),
        })
    walk = pd.DataFrame(rows).sort_values("period").reset_index(drop=True)
    funded = assess_against_naive(actual=walk["actual_sales_usd"], prediction=walk["funded_backlog_predicted_sales_usd"], naive=walk["naive_prior_year_sales_usd"])
    total = assess_against_naive(actual=walk["actual_sales_usd"], prediction=walk["total_backlog_predicted_sales_usd"], naive=walk["naive_prior_year_sales_usd"])
    margin_rows = walk.loc[walk["margin_performance_claim_allowed"]]
    margin = assess_against_naive(actual=margin_rows["actual_operating_margin_pct"], prediction=margin_rows["predicted_operating_margin_pct"], naive=margin_rows["naive_prior_year_margin_pct"])
    summary = pd.DataFrame([{
        "company": "NOC", "validation_observations": len(walk),
        "revenue_claim_observations": funded.observations, "margin_claim_observations": margin.observations,
        "funded_backlog_revenue_mase": funded.mase, "total_backlog_revenue_mase": total.mase,
        "funded_vs_total_mase_improvement_pct": (total.mase - funded.mase) / total.mase * 100.0,
        "funded_backlog_revenue_champion_eligible": funded.eligible,
        "total_backlog_revenue_champion_eligible": total.eligible,
        "margin_mase": margin.mase, "margin_champion_eligible": margin.eligible,
        "program_adjustment_periods": int(walk["explicit_program_adjustment_period"].sum()),
        "historical_pit_input_pct": float(walk["historical_pit_input"].mean() * 100.0),
    }])
    return {
        "noc_company_feature_panel": frame.drop(columns="quarter"),
        "noc_company_walk_forward": walk,
        "noc_company_portability_summary": summary,
    }
