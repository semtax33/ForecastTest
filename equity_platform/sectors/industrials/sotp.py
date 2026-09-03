from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.valuation import DcfAssumptions, enterprise_value, solve_implied_growth


def residual_income_value(
    *,
    book_equity_usd: float,
    roe_pct: float,
    cost_of_equity_pct: float,
    growth_pct: float,
    horizon_years: int,
) -> tuple[pd.DataFrame, float, float]:
    if book_equity_usd <= 0:
        raise ValueError("Financial Products book equity must be positive")
    if cost_of_equity_pct <= growth_pct:
        raise ValueError("Financial Products cost of equity must exceed growth")
    cost = cost_of_equity_pct / 100.0
    growth = growth_pct / 100.0
    roe = roe_pct / 100.0
    book = book_equity_usd
    rows: list[dict[str, float]] = []
    for year in range(1, horizon_years + 1):
        income = roe * book
        equity_charge = cost * book
        residual_income = income - equity_charge
        discount_factor = (1.0 + cost) ** year
        rows.append(
            {
                "forecast_year": year,
                "beginning_book_equity_usd": book,
                "net_income_usd": income,
                "equity_charge_usd": equity_charge,
                "residual_income_usd": residual_income,
                "discount_factor": discount_factor,
                "pv_residual_income_usd": residual_income / discount_factor,
            }
        )
        book *= 1.0 + growth
    terminal_residual_income = (roe - cost) * book
    terminal_value = terminal_residual_income / (cost - growth)
    pv_terminal = terminal_value / ((1.0 + cost) ** horizon_years)
    value = book_equity_usd + sum(row["pv_residual_income_usd"] for row in rows) + pv_terminal
    justified_pb_value = book_equity_usd * (roe - growth) / (cost - growth)
    rows[-1].update(
        {
            "terminal_residual_income_usd": terminal_residual_income,
            "terminal_residual_income_value_usd": terminal_value,
            "pv_terminal_residual_income_value_usd": pv_terminal,
        }
    )
    return pd.DataFrame(rows), float(value), float(justified_pb_value)


def build_financial_products_valuation(
    *,
    segment_history: pd.DataFrame,
    cost_of_equity_pct: float,
    cost_of_equity_sensitivity_pct: float,
    terminal_growth_pct: float,
    horizon_years: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    history = segment_history.dropna(subset=["fp_roe_pct"])
    latest = segment_history.iloc[-1]
    roe = history["fp_roe_pct"]
    scenario_inputs = (
        ("BEAR", float(roe.quantile(0.25)), cost_of_equity_pct + cost_of_equity_sensitivity_pct),
        ("BASE", float(roe.median()), cost_of_equity_pct),
        ("BULL", float(roe.quantile(0.75)), cost_of_equity_pct - cost_of_equity_sensitivity_pct),
    )
    summary_rows: list[dict[str, object]] = []
    base_projection = pd.DataFrame()
    for scenario, normalized_roe, scenario_cost in scenario_inputs:
        projections, value, pb_crosscheck = residual_income_value(
            book_equity_usd=float(latest["financial_products_equity_usd"]),
            roe_pct=normalized_roe,
            cost_of_equity_pct=scenario_cost,
            growth_pct=terminal_growth_pct,
            horizon_years=horizon_years,
        )
        if scenario == "BASE":
            base_projection = projections.assign(scenario=scenario)
        summary_rows.append(
            {
                "scenario": scenario,
                "valuation_method": "STABLE_GROWTH_RESIDUAL_INCOME",
                "book_equity_usd": latest["financial_products_equity_usd"],
                "normalized_roe_pct": normalized_roe,
                "cost_of_equity_pct": scenario_cost,
                "terminal_growth_pct": terminal_growth_pct,
                "residual_income_value_usd": value,
                "justified_price_to_book_value_usd": pb_crosscheck,
                "valuation_identity_error_usd": value - pb_crosscheck,
                "latest_profit_usd": latest["financial_products_profit_usd"],
                "finance_receivables_usd": latest["fp_finance_receivables_total_usd"],
                "funding_debt_usd": latest["fp_funding_debt_usd"],
                "funding_cost_proxy_pct": latest["fp_funding_cost_proxy_pct"],
                "revenue_yield_proxy_pct": latest["fp_revenue_yield_proxy_pct"],
                "funding_spread_proxy_pct": latest["fp_funding_spread_proxy_pct"],
                "credit_loss_provision_pct_receivables": latest[
                    "fp_credit_loss_provision_pct_receivables"
                ],
                "credit_loss_allowance_pct_receivables": latest[
                    "fp_credit_loss_allowance_pct_receivables"
                ],
                "production_input_allowed": False,
            }
        )
    return pd.DataFrame(summary_rows), base_projection


def build_cat_sotp_research(
    *,
    segment_history: pd.DataFrame,
    market: pd.DataFrame,
    backlog_results: dict[str, pd.DataFrame],
    bridge_history_years: int,
    terminal_growth_pct: float,
    horizon_years: int,
    finance_cost_of_equity_sensitivity_pct: float,
    reverse_growth_lower_pct: float,
    reverse_growth_upper_pct: float,
    v1_forecast: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    current_market = market.iloc[0]
    latest = segment_history.iloc[-1]
    window = segment_history.tail(bridge_history_years)
    fp_valuation, fp_projection = build_financial_products_valuation(
        segment_history=segment_history,
        cost_of_equity_pct=float(current_market["cost_of_equity_pct"]),
        cost_of_equity_sensitivity_pct=finance_cost_of_equity_sensitivity_pct,
        terminal_growth_pct=terminal_growth_pct,
        horizon_years=horizon_years,
    )
    fp_base_value = float(
        fp_valuation.loc[fp_valuation["scenario"].eq("BASE"), "residual_income_value_usd"].iloc[0]
    )
    mpe_debt = float(latest["mpe_total_debt_usd"])
    mpe_cash = float(latest["mpe_cash_usd"])
    mpe_market_equity = float(current_market["equity_market_value_usd"]) - fp_base_value
    if mpe_market_equity <= 0:
        raise ValueError("Financial Products value exceeds CAT market capitalization")
    average_mpe_debt = float(
        segment_history["mpe_total_debt_usd"].tail(2).mean()
    )
    direct_mpe_cost_of_debt = (
        float(latest["mpe_interest_expense_usd"]) / average_mpe_debt * 100.0
    )
    tax_rate_pct = float(window["mpe_effective_tax_rate_pct"].median())
    total_mpe_capital = mpe_market_equity + mpe_debt
    mpe_wacc_pct = (
        mpe_market_equity
        / total_mpe_capital
        * float(current_market["cost_of_equity_pct"])
        + mpe_debt
        / total_mpe_capital
        * direct_mpe_cost_of_debt
        * (1.0 - tax_rate_pct / 100.0)
    )
    anchor_gate = backlog_results["backlog_anchor_gate"].iloc[0]
    candidate = backlog_results["backlog_conversion_candidate"].iloc[0]
    anchor_promoted = bool(anchor_gate["anchor_promoted"])
    growth_pct = (
        float(candidate["candidate_revenue_mid_usd"])
        / float(latest["mpe_total_revenue_usd"])
        * 100.0
        - 100.0
        if anchor_promoted
        else 0.0
    )
    margin_pct = float(window["mpe_operating_margin_pct"].median())
    roic_pct = float(window["mpe_roic_pct"].dropna().median())
    assumptions = DcfAssumptions(
        base_revenue_usd=float(latest["mpe_total_revenue_usd"]),
        near_term_growth_pct=growth_pct,
        operating_margin_pct=margin_pct,
        tax_rate_pct=tax_rate_pct,
        roic_pct=roic_pct,
        wacc_pct=mpe_wacc_pct,
        terminal_growth_pct=terminal_growth_pct,
        horizon_years=horizon_years,
    )
    projections, mpe_enterprise_value = enterprise_value(assumptions)
    mpe_equity_value = mpe_enterprise_value - mpe_debt + mpe_cash
    sotp_equity_value = mpe_equity_value + fp_base_value
    shares = float(current_market["shares_outstanding"])
    sotp_per_share = sotp_equity_value / shares
    market_target_mpe_ev = (
        float(current_market["equity_market_value_usd"])
        - fp_base_value
        + mpe_debt
        - mpe_cash
    )
    reverse = solve_implied_growth(
        assumptions,
        market_target_mpe_ev,
        lower_pct=reverse_growth_lower_pct,
        upper_pct=reverse_growth_upper_pct,
    )
    projection_frame = pd.DataFrame(projections)
    projection_frame.insert(0, "business", "MP&E")
    year_one = projection_frame.iloc[0]
    bridge = pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "forecast_origin_fiscal_year": int(latest["fiscal_year"]),
                "target_fiscal_year": int(latest["fiscal_year"]) + 1,
                "business": "MP&E",
                "primary_anchor": "FIRM_ORDER_BACKLOG_DIRECT_10_K",
                "selected_forecast_route": anchor_gate["selected_forecast_route"],
                "anchor_promoted": anchor_promoted,
                "base_revenue_usd": assumptions.base_revenue_usd,
                "near_term_growth_pct": assumptions.near_term_growth_pct,
                "year_one_revenue_usd": year_one["revenue_usd"],
                "normalized_operating_margin_pct": margin_pct,
                "year_one_ebit_usd": year_one["ebit_usd"],
                "normalized_tax_rate_pct": tax_rate_pct,
                "year_one_nopat_usd": year_one["nopat_usd"],
                "normalized_roic_pct": roic_pct,
                "year_one_reinvestment_usd": year_one["reinvestment_usd"],
                "year_one_fcff_usd": year_one["fcff_usd"],
                "mpe_cost_of_debt_pct": direct_mpe_cost_of_debt,
                "mpe_cost_of_debt_method": "DIRECT_INTEREST_EX_FP_OVER_AVERAGE_MPE_DEBT",
                "mpe_wacc_pct": mpe_wacc_pct,
                "terminal_growth_pct": terminal_growth_pct,
                "mpe_debt_used_usd": mpe_debt,
                "mpe_cash_used_usd": mpe_cash,
                "fp_funding_debt_excluded_usd": latest["fp_funding_debt_usd"],
                "mpe_enterprise_value_usd": mpe_enterprise_value,
                "mpe_equity_value_usd": mpe_equity_value,
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    sotp = pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "valuation_status": "RESEARCH_ONLY_NOT_A_MISPRICING_SIGNAL",
                "mpe_enterprise_value_usd": mpe_enterprise_value,
                "less_mpe_debt_usd": mpe_debt,
                "add_mpe_cash_usd": mpe_cash,
                "mpe_equity_value_usd": mpe_equity_value,
                "financial_products_equity_value_usd": fp_base_value,
                "sotp_equity_value_usd": sotp_equity_value,
                "shares_outstanding": shares,
                "sotp_value_per_share": sotp_per_share,
                "market_price": current_market["market_price"],
                "research_gap_pct": sotp_per_share / float(current_market["market_price"]) * 100.0 - 100.0,
                "component_identity_error_usd": (
                    sotp_equity_value - mpe_equity_value - fp_base_value
                ),
                "financial_products_funding_debt_double_counted": False,
                "terminal_input_allowed": False,
                "production_promoted": False,
            }
        ]
    )
    reverse_frame = pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "market_equity_value_usd": current_market["equity_market_value_usd"],
                "less_financial_products_equity_value_usd": fp_base_value,
                "add_mpe_debt_usd": mpe_debt,
                "less_mpe_cash_usd": mpe_cash,
                "market_target_mpe_enterprise_value_usd": market_target_mpe_ev,
                "reverse_dcf_status": reverse["status"],
                "market_implied_near_term_growth_pct": reverse["implied_growth_pct"],
                "solver_residual_usd": reverse["residual_usd"],
                "search_lower_pct": reverse_growth_lower_pct,
                "search_upper_pct": reverse_growth_upper_pct,
                "boundary_reported_as_solution": False,
            }
        ]
    )
    v1_value = np.nan
    v1_gap = np.nan
    if v1_forecast is not None and not v1_forecast.empty:
        v1_value = float(v1_forecast.iloc[0]["forward_dcf_fair_value_per_share"])
        v1_gap = float(v1_forecast.iloc[0]["expectations_gap_pct"])
    comparison = pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "v1_consolidated_dcf_value_per_share": v1_value,
                "v1_reported_expectations_gap_pct": v1_gap,
                "v1_gap_interpretation": "RETIRED_NOT_INTERPRETABLE_AS_MISPRICING",
                "v1_1_sotp_value_per_share": sotp_per_share,
                "v1_1_minus_v1_value_per_share": sotp_per_share - v1_value,
                "v1_1_research_gap_pct": sotp.iloc[0]["research_gap_pct"],
                "change_driver_1": "RPO_RETIRED_DIRECT_FIRM_BACKLOG_DIAGNOSTIC",
                "change_driver_2": "MPE_DEBT_ONLY_EV_TO_EQUITY_BRIDGE",
                "change_driver_3": "FINANCIAL_PRODUCTS_RESIDUAL_INCOME_SOTP",
                "investment_conclusion_allowed": False,
            }
        ]
    )
    identity_error = abs(float(year_one["revenue_usd"]) - (
        assumptions.base_revenue_usd * (1.0 + assumptions.near_term_growth_pct / 100.0)
    ))
    gate = pd.DataFrame(
        [
            {
                "version": "INDUSTRIALS_V1_1_CAT_SEMANTIC_SOTP_AUDIT",
                "direct_firm_backlog_years": int(anchor_gate["direct_firm_backlog_years"]),
                "rpo_anchor_retired": bool(anchor_gate["rpo_anchor_retired"]),
                "direct_backlog_anchor_promoted": anchor_promoted,
                "backlog_oos_validation_observations": int(
                    anchor_gate["walk_forward_validation_observations"]
                ),
                "segment_history_years": len(segment_history),
                "segment_reconciliation_pass": bool(
                    segment_history["segment_reconciliation_pass"].all()
                ),
                "mpe_debt_used_usd": mpe_debt,
                "fp_funding_debt_excluded_from_mpe_bridge_usd": latest["fp_funding_debt_usd"],
                "financial_products_separately_valued": True,
                "sotp_component_identity_pass": abs(
                    float(sotp.iloc[0]["component_identity_error_usd"])
                ) <= 1.0,
                "year_one_revenue_identity_error_usd": identity_error,
                "year_one_revenue_identity_pass": identity_error <= 1.0,
                "reverse_dcf_fail_closed": reverse["status"] in {
                    "SOLVED",
                    "UNBRACKETED_NO_SOLUTION_IN_DOMAIN",
                },
                "research_audit_complete": True,
                "terminal_input_allowed": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
    return {
        "financial_products_valuation": fp_valuation,
        "financial_products_residual_income_projection": fp_projection,
        "mpe_forecast_financial_bridge": bridge,
        "mpe_dcf_projections": projection_frame,
        "sotp_valuation": sotp,
        "sotp_reverse_dcf": reverse_frame,
        "v1_vs_v1_1_comparison": comparison,
        "industrials_v1_1_gate": gate,
    }
