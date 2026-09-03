from __future__ import annotations

import numpy as np
import pandas as pd


DISCLOSED_COST_COMPONENTS = {
    "development_usd": "DEVELOPMENT_CAPITAL",
    "exploration_usd": "EXPLORATION_AND_DRY_HOLE_SCOPE",
    "proved_acquisition_usd": "PROVED_PROPERTY_ACQUISITION",
    "unproved_acquisition_usd": "UNPROVED_LEASEHOLD_ACQUISITION",
}
UNRESOLVED_COMPANY_SCOPE_DRIVERS = (
    "LEASEHOLD_AND_ACREAGE_OUTSIDE_REPORTED_ACQUISITION_SCOPE",
    "SHARED_INFRASTRUCTURE",
    "CORPORATE_OVERHEAD",
    "ACQUISITION_PREMIUM_AND_PURCHASE_ACCOUNTING",
    "MAINTENANCE_AND_RESERVE_REPLACEMENT_TIMING",
    "IMPAIRMENTS_AND_EARNINGS_TIMING",
)


def build_cost_component_evidence(
    annual_costs: pd.DataFrame,
    eligible_tickers: set[str],
) -> pd.DataFrame:
    selected = annual_costs.loc[
        annual_costs["ticker"].isin(eligible_tickers)
        & pd.to_numeric(
            annual_costs["selected_all_in_reserve_investment_usd"], errors="coerce"
        ).gt(0)
    ].copy()
    rows: list[dict[str, object]] = []
    for ticker, history in selected.groupby("ticker", sort=True):
        all_in = float(history["selected_all_in_reserve_investment_usd"].sum())
        for column, driver in DISCLOSED_COST_COMPONENTS.items():
            values = pd.to_numeric(history[column], errors="coerce")
            amount = float(values.fillna(0.0).sum())
            observed = int(values.notna().sum())
            rows.append(
                {
                    "ticker": ticker,
                    "driver": driver,
                    "identified_cost_usd": amount,
                    "all_in_reserve_cost_usd": all_in,
                    "share_of_all_in_reserve_cost_pct": amount / all_in * 100.0,
                    "observed_years": observed,
                    "window_years": len(history),
                    "identification_status": (
                        "DIRECT_COMPONENT_DISCLOSURE"
                        if observed == len(history)
                        else "RECONCILED_TOTAL_WITH_COMPONENT_NOT_SEPARATELY_DISCLOSED"
                    ),
                    "roic_effect_allocated": False,
                    "allocation_reason": (
                        "COST_COMPOSITION_ONLY_MEDIAN_ROIC_NONLINEAR_NO_ARBITRARY_ALLOCATION"
                    ),
                }
            )
        for driver in UNRESOLVED_COMPANY_SCOPE_DRIVERS:
            rows.append(
                {
                    "ticker": ticker,
                    "driver": driver,
                    "identified_cost_usd": np.nan,
                    "all_in_reserve_cost_usd": all_in,
                    "share_of_all_in_reserve_cost_pct": np.nan,
                    "observed_years": 0,
                    "window_years": len(history),
                    "identification_status": "NOT_SEPARATELY_IDENTIFIED_IN_CURRENT_EVIDENCE",
                    "roic_effect_allocated": False,
                    "allocation_reason": "UNEXPLAINED_RESIDUAL_RETAINED_FAIL_CLOSED",
                }
            )
    return pd.DataFrame(rows)


def build_project_to_company_waterfall(
    reserve_cross_check: pd.DataFrame,
    company_ranges: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    reserve = reserve_cross_check.copy()
    for column in (
        "project_development_roic_proxy_q50_pct",
        "company_scope_all_in_reserve_roic_proxy_q50_pct",
    ):
        reserve[column] = pd.to_numeric(reserve[column], errors="coerce")
    reserve = reserve.loc[
        reserve["project_development_roic_proxy_q50_pct"].notna()
        & reserve["company_scope_all_in_reserve_roic_proxy_q50_pct"].notna()
    ]
    company = company_ranges.set_index("ticker")
    step_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for source in reserve.to_dict("records"):
        ticker = str(source["ticker"])
        project = float(source["project_development_roic_proxy_q50_pct"])
        replacement = float(
            source["company_scope_all_in_reserve_roic_proxy_q50_pct"]
        )
        has_company = ticker in company.index
        if has_company:
            company_row = company.loc[ticker]
            low = float(company_row["organic_roic_research_low_pct"])
            high = float(company_row["organic_roic_research_high_pct"])
            midpoint = float(company_row["organic_roic_research_midpoint_pct"])
            range_category = str(company_row["range_width_category"])
            company_effect = midpoint - replacement
        else:
            low = high = midpoint = company_effect = np.nan
            range_category = "NO_VALIDATED_COMPANY_COHORT"
        reserve_effect = replacement - project
        identity_error = (
            project + reserve_effect + company_effect - midpoint
            if has_company
            else np.nan
        )
        step_rows.extend(
            [
                {
                    "ticker": ticker,
                    "step_order": 1,
                    "stage": "PROJECT_DEVELOPMENT_ECONOMICS",
                    "ending_roic_pct": project,
                    "incremental_effect_pct_points": 0.0,
                    "effect_identification": "DIRECT_V1_5_PROJECT_PROXY",
                    "economic_scope": "DEVELOPMENT_COST_ONLY",
                },
                {
                    "ticker": ticker,
                    "step_order": 2,
                    "stage": "RESERVE_REPLACEMENT_SCOPE",
                    "ending_roic_pct": replacement,
                    "incremental_effect_pct_points": reserve_effect,
                    "effect_identification": "IDENTIFIED_AGGREGATE_SCOPE_EFFECT",
                    "economic_scope": "DEVELOPMENT_EXPLORATION_PROVED_AND_UNPROVED_ACQUISITION",
                },
                {
                    "ticker": ticker,
                    "step_order": 3,
                    "stage": "COMPANY_ORGANIC_ECONOMICS",
                    "ending_roic_pct": midpoint,
                    "incremental_effect_pct_points": company_effect,
                    "effect_identification": (
                        "UNEXPLAINED_COMPANY_SCOPE_RESIDUAL"
                        if has_company
                        else "LOCKED_NO_VALIDATED_COMPANY_COHORT"
                    ),
                    "economic_scope": "TOTAL_COMPANY_ORGANIC_INVESTED_CAPITAL_AND_NOPAT",
                },
            ]
        )
        total_gap = midpoint - project if has_company else np.nan
        summary_rows.append(
            {
                "ticker": ticker,
                "project_roic_pct": project,
                "reserve_replacement_roic_pct": replacement,
                "company_organic_roic_low_pct": low,
                "company_organic_roic_midpoint_pct": midpoint,
                "company_organic_roic_high_pct": high,
                "company_range_category": range_category,
                "project_to_reserve_effect_pct_points": reserve_effect,
                "reserve_to_company_unexplained_effect_pct_points": company_effect,
                "project_to_company_total_effect_pct_points": total_gap,
                "waterfall_identity_error_pct_points": identity_error,
                "waterfall_identity_pass": bool(
                    has_company and abs(identity_error) <= 1e-10
                ),
                "strong_company_comparison": bool(
                    has_company and range_category == "STRONG"
                ),
                "cross_level_period_alignment": (
                    "OVERLAPPING_CLEAN_WINDOW"
                    if ticker == "AR"
                    else "NONCOMPARABLE_OR_NO_MATCHED_WINDOW"
                ),
                "company_scope_driver_closure": False,
                "normal_roic_claimed": False,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        )
    steps = pd.DataFrame(step_rows)
    steps["normal_roic_claimed"] = False
    steps["terminal_input_allowed"] = False
    steps["research_only"] = True
    return steps, pd.DataFrame(summary_rows)
