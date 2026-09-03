from __future__ import annotations

import numpy as np
import pandas as pd


SEGMENTS = ("ingalls_shipbuilding", "newport_news_shipbuilding", "mission_technologies")


def _growth(history: pd.DataFrame, value: str, target: pd.Period, as_of: pd.Timestamp) -> float:
    available = history.loc[pd.to_datetime(history["filing_date"]).le(as_of)].copy()
    available["quarter"] = available["period"].map(lambda item: pd.Period(item, freq="Q"))
    values = available.set_index("quarter")[value].to_dict()
    growth: list[float] = []
    for quarter in sorted(values):
        if quarter >= target or quarter - 4 not in values or not values[quarter - 4]:
            continue
        growth.append(values[quarter] / values[quarter - 4] - 1.0)
    return float(np.clip(np.median(growth[-8:]), -0.15, 0.25)) if growth else 0.0


def _backlog_growth(backlog: pd.DataFrame, as_of: pd.Timestamp) -> tuple[float, int, float]:
    available = backlog.loc[
        pd.to_datetime(backlog["filing_date"]).le(as_of) & backlog["total_backlog_usd"].notna()
    ].sort_values("filing_date")
    if len(available) < 2:
        return 0.0, len(available), np.nan
    latest = available.iloc[-1]
    prior = available.iloc[-2]
    years = max(1.0, (pd.Timestamp(latest["filing_date"]) - pd.Timestamp(prior["filing_date"])).days / 365.25)
    growth = (latest["total_backlog_usd"] / prior["total_backlog_usd"]) ** (1.0 / years) - 1.0
    return float(np.clip(growth, -0.15, 0.25)), len(available), float(latest["total_backlog_usd"])


def _segment_point_rows(
    history: pd.DataFrame,
    origins: pd.DataFrame,
    industry: pd.DataFrame,
    programs: pd.DataFrame,
    validation_start: str,
    validation_end: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    start, end = pd.Period(validation_start, freq="Q"), pd.Period(validation_end, freq="Q")
    for segment in SEGMENTS:
        segment_history = history.loc[history["segment"].eq(segment)].copy()
        values = segment_history.set_index(segment_history["period"].map(lambda item: pd.Period(item, freq="Q")))["sales_usd"].to_dict()
        margins = segment_history.set_index(segment_history["period"].map(lambda item: pd.Period(item, freq="Q")))["operating_margin_pct"].to_dict()
        for origin in origins.itertuples():
            target = pd.Period(origin.period, freq="Q")
            if target - 4 not in values or not (start <= target <= end):
                continue
            as_of = pd.Timestamp(origin.forecast_as_of)
            lag4 = float(values[target - 4])
            actual = float(values[target])
            median_growth = _growth(segment_history, "sales_usd", target, as_of)
            feature = industry.loc[(industry["period"].eq(origin.period)) & (industry["segment"].eq(segment))]
            output_yoy = float(feature.iloc[0]["output_price_yoy_pct"]) / 100.0 if len(feature) else 0.0
            cost_yoy = float(feature.iloc[0]["dedicated_cost_yoy_pct"]) / 100.0 if len(feature) else 0.0
            industry_growth = float(np.clip(0.70 * median_growth + 0.30 * output_yoy, -0.15, 0.25))
            naive = lag4
            historical = lag4 * (1.0 + median_growth)
            industry_prediction = lag4 * (1.0 + industry_growth)
            blend = 0.50 * naive + 0.25 * historical + 0.25 * industry_prediction
            lag_margin = float(margins[target - 4])
            known = segment_history.loc[pd.to_datetime(segment_history["filing_date"]).le(as_of), "operating_margin_pct"]
            normalized_margin = float(known.tail(8).median())
            industry_margin = float(np.clip(lag_margin + 10.0 * (output_yoy - cost_yoy), -10.0, 25.0))
            margin_blend = 0.50 * lag_margin + 0.35 * normalized_margin + 0.15 * industry_margin
            latest_program = programs.loc[pd.to_datetime(programs["filing_date"]).le(as_of)].sort_values("filing_date").tail(1)
            rows.append({
                "period": origin.period, "segment": segment, "forecast_as_of": origin.forecast_as_of,
                "actual_available_at": origin.actual_available_at,
                "actual_after_forecast": pd.Timestamp(origin.actual_available_at) > as_of,
                "actual_sales_usd": actual, "naive_sales_usd": naive,
                "historical_growth_sales_usd": historical,
                "industry_bridge_sales_usd": industry_prediction,
                "predeclared_blend_sales_usd": blend,
                "actual_margin_pct": float(margins[target]), "naive_margin_pct": lag_margin,
                "normalized_margin_pct": normalized_margin,
                "industry_bridge_margin_pct": industry_margin,
                "predeclared_blend_margin_pct": margin_blend,
                "trailing_median_yoy_growth_pct": median_growth * 100.0,
                "output_price_yoy_pct": output_yoy * 100.0, "input_cost_yoy_pct": cost_yoy * 100.0,
                "program_evidence_available": bool(len(latest_program)),
                "program_evidence_used_as_point_override": False,
                "history_authority": "AS_REPORTED_PIT_HISTORY",
                "historical_pit_input": True,
            })
    return pd.DataFrame(rows).sort_values(["period", "segment"]).reset_index(drop=True)


def _company_point_rows(
    history: pd.DataFrame,
    origins: pd.DataFrame,
    industry: pd.DataFrame,
    backlog: pd.DataFrame,
    segment_walk: pd.DataFrame,
    validation_start: str,
    validation_end: str,
) -> pd.DataFrame:
    values = history.set_index(history["period"].map(lambda item: pd.Period(item, freq="Q")))["revenue_usd"].to_dict()
    eliminations = history.set_index(history["period"].map(lambda item: pd.Period(item, freq="Q")))["intersegment_eliminations_usd"].to_dict()
    rows: list[dict[str, object]] = []
    start, end = pd.Period(validation_start, freq="Q"), pd.Period(validation_end, freq="Q")
    for origin in origins.itertuples():
        target = pd.Period(origin.period, freq="Q")
        if target - 4 not in values or not (start <= target <= end):
            continue
        as_of = pd.Timestamp(origin.forecast_as_of)
        lag4 = float(values[target - 4])
        median_growth = _growth(history, "revenue_usd", target, as_of)
        target_features = industry.loc[industry["period"].eq(origin.period)]
        output_yoy = float(target_features["output_price_yoy_pct"].mean()) / 100.0
        industry_growth = float(np.clip(0.70 * median_growth + 0.30 * output_yoy, -0.15, 0.25))
        backlog_growth, backlog_observations, latest_backlog = _backlog_growth(backlog, as_of)
        naive = lag4
        historical = lag4 * (1.0 + median_growth)
        industry_prediction = lag4 * (1.0 + industry_growth)
        backlog_prediction = lag4 * (1.0 + backlog_growth) if backlog_observations >= 2 else np.nan
        available_candidates = [naive, historical, industry_prediction]
        if np.isfinite(backlog_prediction):
            available_candidates.append(backlog_prediction)
        fixed_blend = float(np.mean(available_candidates))
        segments = segment_walk.loc[segment_walk["period"].eq(origin.period)]
        sum_segment = float(segments["predeclared_blend_sales_usd"].sum() + eliminations[target - 4])
        rows.append({
            "period": origin.period, "forecast_as_of": origin.forecast_as_of,
            "actual_available_at": origin.actual_available_at,
            "actual_after_forecast": pd.Timestamp(origin.actual_available_at) > as_of,
            "actual_revenue_usd": float(values[target]), "naive_revenue_usd": naive,
            "historical_growth_revenue_usd": historical,
            "industry_bridge_revenue_usd": industry_prediction,
            "backlog_bridge_revenue_usd": backlog_prediction,
            "predeclared_blend_revenue_usd": fixed_blend,
            "sum_segment_bridge_revenue_usd": sum_segment,
            "latest_available_backlog_usd": latest_backlog,
            "backlog_observations_available": backlog_observations,
            "trailing_median_yoy_growth_pct": median_growth * 100.0,
            "industry_output_yoy_pct": output_yoy * 100.0,
            "history_authority": "AS_REPORTED_PIT_HISTORY",
            "historical_pit_input": True,
            "segment_backlog_imputed": False,
        })
    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True)


def _metrics(frame: pd.DataFrame, actual: str, naive: str, predictions: dict[str, str]) -> pd.DataFrame:
    denominator = float((frame[actual] - frame[naive]).abs().mean())
    rows: list[dict[str, object]] = []
    for route, column in predictions.items():
        eligible = frame.loc[frame[column].notna() & frame[actual].notna()]
        mae = float((eligible[actual] - eligible[column]).abs().mean())
        rows.append({
            "route": route, "validation_observations": len(eligible), "mae": mae,
            "mase": mae / denominator if denominator else np.nan,
            "mean_ape_pct": float(((eligible[actual] - eligible[column]).abs() / eligible[actual].abs()).mean() * 100.0),
            "beats_prior_year_naive": bool(mae < denominator),
        })
    return pd.DataFrame(rows).sort_values(["mase", "route"]).reset_index(drop=True)


def build_hii_forecast_research(
    *, company_history: pd.DataFrame, segment_history: pd.DataFrame,
    backlog: pd.DataFrame, programs: pd.DataFrame, origins: pd.DataFrame,
    industry_features: pd.DataFrame, validation_start: str, validation_end: str,
) -> dict[str, pd.DataFrame]:
    segment_walk = _segment_point_rows(
        segment_history, origins, industry_features, programs, validation_start, validation_end
    )
    company_walk = _company_point_rows(
        company_history, origins, industry_features, backlog, segment_walk,
        validation_start, validation_end,
    )
    company_metrics = _metrics(company_walk, "actual_revenue_usd", "naive_revenue_usd", {
        "PRIOR_YEAR_NAIVE": "naive_revenue_usd",
        "HISTORICAL_GROWTH": "historical_growth_revenue_usd",
        "PIT_INDUSTRY_BRIDGE": "industry_bridge_revenue_usd",
        "TOTAL_BACKLOG_BRIDGE": "backlog_bridge_revenue_usd",
        "PREDECLARED_EQUAL_BLEND": "predeclared_blend_revenue_usd",
        "SUM_SEGMENT_BRIDGE": "sum_segment_bridge_revenue_usd",
    })
    segment_metrics: list[pd.DataFrame] = []
    margin_metrics: list[pd.DataFrame] = []
    for segment, frame in segment_walk.groupby("segment"):
        revenue = _metrics(frame, "actual_sales_usd", "naive_sales_usd", {
            "PRIOR_YEAR_NAIVE": "naive_sales_usd", "HISTORICAL_GROWTH": "historical_growth_sales_usd",
            "PIT_INDUSTRY_BRIDGE": "industry_bridge_sales_usd", "PREDECLARED_BLEND": "predeclared_blend_sales_usd",
        })
        revenue.insert(0, "segment", segment)
        segment_metrics.append(revenue)
        margin = _metrics(frame, "actual_margin_pct", "naive_margin_pct", {
            "PRIOR_YEAR_NAIVE": "naive_margin_pct", "NORMALIZED_MARGIN": "normalized_margin_pct",
            "PIT_COST_MARGIN_BRIDGE": "industry_bridge_margin_pct", "PREDECLARED_BLEND": "predeclared_blend_margin_pct",
        })
        margin.insert(0, "segment", segment)
        margin_metrics.append(margin)
    segment_metric = pd.concat(segment_metrics, ignore_index=True)
    margin_metric = pd.concat(margin_metrics, ignore_index=True)
    champion = company_metrics.iloc[0]
    segment_champions = segment_metric.sort_values(["segment", "mase"]).groupby("segment", as_index=False).first()
    margin_champions = margin_metric.sort_values(["segment", "mase"]).groupby("segment", as_index=False).first()
    authority = pd.DataFrame([{
        "company": "HII", "aggregate_revenue_point_authority": bool(champion["mase"] < 1.0 and champion["validation_observations"] == 6),
        "aggregate_revenue_champion_route": champion["route"], "aggregate_revenue_mase": champion["mase"],
        "aggregate_revenue_mean_ape_pct": champion["mean_ape_pct"],
        "segment_revenue_attribution_authority": False,
        "segment_revenue_routes_beating_naive": int(segment_champions["beats_prior_year_naive"].sum()),
        "margin_authority": False, "margin_routes_beating_naive": int(margin_champions["beats_prior_year_naive"].sum()),
        "backlog_point_authority": False, "segment_backlog_available": False,
        "funded_backlog_incremental_value": "NOT_TESTABLE_NO_FUNDED_DISCLOSURE",
        "uncertainty_authority": False,
        "roic_reinvestment_authority": "HISTORICAL_DIAGNOSTIC_ONLY",
        "terminal_authority": False, "production_authority": False,
        "dcf_authority": False, "reverse_dcf_authority": False,
        "forecast_freeze_eligible": False,
    }])
    coverage = pd.DataFrame([{
        "company_expected_oos_rows": 6, "company_model_oos_rows": len(company_walk),
        "segment_expected_oos_rows": 18, "segment_model_oos_rows": len(segment_walk),
        "missing_rows_imputed": False, "segment_backlog_imputed": False,
        "actual_after_forecast_all": bool(company_walk["actual_after_forecast"].all() and segment_walk["actual_after_forecast"].all()),
        "historical_pit_input_pct": 100.0,
    }])
    uncertainty = pd.DataFrame([{
        "company_calibration_observations": len(company_walk),
        "minimum_required_calibration_observations": 10,
        "company_interval_eligible": False,
        "segment_interval_eligible_count": 0,
        "uncertainty_authority": False,
        "reason": "FIXED_OOS_HAS_SIX_OBSERVATIONS_BELOW_TEN_OBSERVATION_CONFORMAL_MINIMUM",
    }])
    return {
        "hii_company_walk_forward": company_walk,
        "hii_company_route_metrics": company_metrics,
        "hii_segment_walk_forward": segment_walk,
        "hii_segment_revenue_route_metrics": segment_metric,
        "hii_segment_margin_route_metrics": margin_metric,
        "hii_segment_revenue_champions": segment_champions,
        "hii_segment_margin_champions": margin_champions,
        "hii_forecast_coverage": coverage,
        "hii_uncertainty_gate": uncertainty,
        "hii_forecast_authority": authority,
    }
