from __future__ import annotations

import numpy as np
import pandas as pd


def build_gd_margin_roic_reinvestment_research(
    *,
    segment_history: pd.DataFrame,
    company_history: pd.DataFrame,
    annual_bridge: pd.DataFrame,
    terminal_margin_hypotheses_pct: list[float],
) -> dict[str, pd.DataFrame]:
    segment = segment_history.copy()
    segment["quarter"] = pd.PeriodIndex(segment["period"], freq="Q")
    segment = segment.sort_values(["segment", "quarter"])
    segment["ttm_revenue_usd"] = segment.groupby("segment")["sales_usd"].transform(
        lambda values: values.rolling(4, min_periods=4).sum()
    )
    segment["ttm_operating_profit_usd"] = segment.groupby("segment")[
        "operating_profit_usd"
    ].transform(lambda values: values.rolling(4, min_periods=4).sum())
    segment["ttm_operating_margin_pct"] = (
        segment["ttm_operating_profit_usd"] / segment["ttm_revenue_usd"] * 100.0
    )
    segment_ttm = segment.dropna(subset=["ttm_operating_margin_pct"]).copy()

    company = company_history.copy()
    company["quarter"] = pd.PeriodIndex(company["period"], freq="Q")
    company = company.sort_values("quarter")
    company["ttm_revenue_usd"] = company["revenue_usd"].rolling(4, min_periods=4).sum()
    company["ttm_operating_income_usd"] = company["operating_income_usd"].rolling(
        4, min_periods=4
    ).sum()
    company["ttm_segment_operating_profit_usd"] = company[
        "segment_sum_operating_profit_usd"
    ].rolling(4, min_periods=4).sum()
    company["ttm_operating_margin_pct"] = (
        company["ttm_operating_income_usd"] / company["ttm_revenue_usd"] * 100.0
    )
    company["ttm_corporate_drag_pct"] = (
        company["ttm_operating_income_usd"]
        - company["ttm_segment_operating_profit_usd"]
    ) / company["ttm_revenue_usd"] * 100.0
    company_ttm = company.dropna(subset=["ttm_operating_margin_pct"]).copy()

    latest_period = segment_ttm["quarter"].max()
    latest = segment_ttm.loc[segment_ttm["quarter"].eq(latest_period)].copy()
    latest["latest_revenue_mix_weight"] = (
        latest["ttm_revenue_usd"] / latest["ttm_revenue_usd"].sum()
    )
    margin_matrix = segment_ttm.pivot(
        index="period", columns="segment", values="ttm_operating_margin_pct"
    )
    weights = latest.set_index("segment")["latest_revenue_mix_weight"]
    common_segments = [column for column in margin_matrix.columns if column in weights]
    reweighted = (margin_matrix[common_segments] * weights[common_segments]).sum(axis=1)
    corporate = company_ttm.set_index("period")["ttm_corporate_drag_pct"]
    contemporaneous = pd.DataFrame(
        {
            "period": reweighted.index,
            "latest_mix_segment_margin_pct": reweighted.values,
        }
    ).merge(corporate.rename("contemporaneous_corporate_drag_pct"), on="period")
    contemporaneous["latest_mix_consolidated_margin_pct"] = (
        contemporaneous["latest_mix_segment_margin_pct"]
        + contemporaneous["contemporaneous_corporate_drag_pct"]
    )
    contemporaneous["all_segment_margins_same_period"] = True
    contemporaneous["historical_diagnostic_only"] = True
    contemporaneous["terminal_input_allowed"] = False

    distribution_rows: list[dict[str, object]] = []
    for label, values in {
        "AS_REPORTED_COMPANY_TTM": company_ttm["ttm_operating_margin_pct"],
        "LATEST_MIX_CONTEMPORANEOUS_TTM": contemporaneous[
            "latest_mix_consolidated_margin_pct"
        ],
    }.items():
        distribution_rows.append(
            {
                "distribution": label,
                "observations": len(values),
                "minimum_pct": float(values.min()),
                "q25_pct": float(values.quantile(0.25)),
                "median_pct": float(values.median()),
                "q75_pct": float(values.quantile(0.75)),
                "maximum_pct": float(values.max()),
                "latest_pct": float(values.iloc[-1]),
                "terminal_input_allowed": False,
            }
        )
    distribution = pd.DataFrame(distribution_rows)
    normalized = contemporaneous["latest_mix_consolidated_margin_pct"]
    hypotheses = pd.DataFrame(
        [
            {
                "terminal_margin_hypothesis_pct": margin,
                "contemporaneous_observations_at_or_above": int(
                    normalized.ge(margin).sum()
                ),
                "inside_observed_contemporaneous_range": bool(
                    normalized.min() <= margin <= normalized.max()
                ),
                "structural_mechanism_independently_identified": False,
                "terminal_input_allowed": False,
                "use": "CONDITIONAL_DCF_EXPECTATIONS_SURFACE_ONLY",
            }
            for margin in terminal_margin_hypotheses_pct
        ]
    )
    annual = annual_bridge.dropna(subset=["reported_roic_pct"]).copy()
    latest_margin = float(company_ttm.iloc[-1]["ttm_operating_margin_pct"])
    roic_summary = pd.DataFrame(
        [
            {
                "reported_roic_observations": len(annual),
                "reported_roic_minimum_pct": float(annual["reported_roic_pct"].min()),
                "reported_roic_q25_pct": float(annual["reported_roic_pct"].quantile(0.25)),
                "reported_roic_median_pct": float(annual["reported_roic_pct"].median()),
                "reported_roic_q75_pct": float(annual["reported_roic_pct"].quantile(0.75)),
                "reported_roic_maximum_pct": float(annual["reported_roic_pct"].max()),
                "latest_reported_roic_pct": float(annual.iloc[-1]["reported_roic_pct"]),
                "latest_ttm_operating_margin_pct": latest_margin,
                "r_and_d_authority": "R_AND_D_NOT_IDENTIFIED_NOT_ZERO_AUTHORITY",
                "innovation_adjusted_reinvestment_claim_allowed": False,
                "terminal_input_allowed": False,
            }
        ]
    )
    return {
        "gd_segment_ttm_margin_history": segment_ttm.drop(columns="quarter"),
        "gd_company_ttm_margin_history": company_ttm.drop(columns="quarter"),
        "gd_latest_mix_contemporaneous_margin_history": contemporaneous,
        "gd_margin_distribution_summary": distribution,
        "gd_terminal_margin_hypothesis_audit": hypotheses,
        "gd_roic_reinvestment_research_summary": roic_summary,
    }


def build_gd_conditional_financial_bridge(
    *, prospective_segment_forecast: pd.DataFrame, research: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    revenue = float(prospective_segment_forecast["predicted_sales_usd"].sum())
    prior = float(prospective_segment_forecast["prior_year_sales_usd"].sum())
    operating_profit = float(
        prospective_segment_forecast["predicted_operating_profit_usd"].sum()
    )
    growth = revenue / prior * 100.0 - 100.0
    margin = operating_profit / revenue * 100.0
    roic = research["gd_roic_reinvestment_research_summary"].iloc[0]
    margin_delta = margin - float(roic["latest_ttm_operating_margin_pct"])
    operating_leverage = float(roic["latest_reported_roic_pct"]) / max(
        float(roic["latest_ttm_operating_margin_pct"]), 0.01
    )
    forecast_roic = float(
        np.clip(
            float(roic["reported_roic_median_pct"]) + margin_delta * operating_leverage,
            float(roic["reported_roic_minimum_pct"]),
            float(roic["reported_roic_maximum_pct"]),
        )
    )
    reinvestment_rate = growth / forecast_roic * 100.0
    return pd.DataFrame(
        [
            {
                "forecast_period": prospective_segment_forecast.iloc[0]["period"],
                "company_revenue_usd": revenue,
                "prior_year_company_revenue_usd": prior,
                "company_revenue_growth_pct": growth,
                "company_operating_profit_usd": operating_profit,
                "company_operating_margin_pct": margin,
                "conditional_roic_pct": forecast_roic,
                "growth_roic_implied_reinvestment_rate_pct": reinvestment_rate,
                "roic_method": "THROUGH_CYCLE_MEDIAN_PLUS_MARGIN_DELTA_OPERATING_LEVERAGE_CLIPPED_TO_OBSERVED_RANGE",
                "reinvestment_identity": "GROWTH_DIVIDED_BY_ROIC",
                "innovation_adjusted_reinvestment_claim_allowed": False,
                "terminal_input_allowed": False,
                "valuation_use": "CONDITIONAL_RESEARCH_ONLY",
            }
        ]
    )
