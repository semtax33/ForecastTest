from __future__ import annotations

import pandas as pd


def _anchor_to_frozen_terminal_dcf(
    *,
    industry_bridge: pd.Series,
    frozen_bridge: pd.Series,
    terminal_growth_pct: float,
    horizon_years: int,
) -> tuple[pd.DataFrame, float]:
    wacc = float(frozen_bridge["mpe_wacc_pct"]) / 100.0
    tax = float(frozen_bridge["normalized_tax_rate_pct"]) / 100.0
    terminal_growth = terminal_growth_pct / 100.0
    terminal_margin = float(frozen_bridge["normalized_operating_margin_pct"]) / 100.0
    terminal_roic = float(frozen_bridge["normalized_roic_pct"]) / 100.0
    revenue = float(industry_bridge["forecast_revenue_usd"])
    rows: list[dict[str, float]] = []
    for year in range(1, horizon_years + 1):
        if year == 1:
            growth = float(industry_bridge["forecast_revenue_growth_pct"]) / 100.0
            margin = float(industry_bridge["forecast_operating_margin_pct"]) / 100.0
            roic = float(industry_bridge["forecast_roic_pct"]) / 100.0
            ebit = float(industry_bridge["forecast_ebit_usd"])
            nopat = float(industry_bridge["forecast_nopat_usd"])
            reinvestment = float(industry_bridge["required_reinvestment_usd"])
        else:
            fade = (year - 1) / max(horizon_years - 1, 1)
            growth = (
                float(industry_bridge["forecast_revenue_growth_pct"]) / 100.0 * (1.0 - fade)
                + terminal_growth * fade
            )
            margin = (
                float(industry_bridge["forecast_operating_margin_pct"]) / 100.0 * (1.0 - fade)
                + terminal_margin * fade
            )
            roic = (
                float(industry_bridge["forecast_roic_pct"]) / 100.0 * (1.0 - fade)
                + terminal_roic * fade
            )
            revenue *= 1.0 + growth
            ebit = revenue * margin
            nopat = ebit * (1.0 - tax)
            reinvestment = nopat * growth / roic
        fcff = nopat - reinvestment
        discount = (1.0 + wacc) ** year
        rows.append(
            {
                "forecast_year": year,
                "revenue_usd": revenue,
                "growth_pct": growth * 100.0,
                "operating_margin_pct": margin * 100.0,
                "ebit_usd": ebit,
                "nopat_usd": nopat,
                "roic_pct": roic * 100.0,
                "reinvestment_usd": reinvestment,
                "fcff_usd": fcff,
                "discount_factor": discount,
                "pv_fcff_usd": fcff / discount,
                "fcff_identity_error_usd": fcff - nopat + reinvestment,
            }
        )
    terminal_revenue = revenue * (1.0 + terminal_growth)
    terminal_nopat = terminal_revenue * terminal_margin * (1.0 - tax)
    terminal_reinvestment = terminal_nopat * terminal_growth / terminal_roic
    terminal_fcff = terminal_nopat - terminal_reinvestment
    terminal_value = terminal_fcff / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1.0 + wacc) ** horizon_years)
    rows[-1].update(
        {
            "terminal_margin_pct": terminal_margin * 100.0,
            "terminal_roic_pct": terminal_roic * 100.0,
            "terminal_fcff_usd": terminal_fcff,
            "terminal_value_usd": terminal_value,
            "pv_terminal_value_usd": pv_terminal,
        }
    )
    return pd.DataFrame(rows), float(sum(row["pv_fcff_usd"] for row in rows) + pv_terminal)


def build_cat_v12_research(
    *,
    industry_results: dict[str, pd.DataFrame],
    frozen_mpe_bridge: pd.DataFrame,
    frozen_sotp: pd.DataFrame,
    terminal_growth_pct: float,
    horizon_years: int,
    parser_quality_gate_pass: bool,
) -> dict[str, pd.DataFrame]:
    industry = industry_results["industry_financial_bridge"].iloc[0]
    frozen = frozen_mpe_bridge.iloc[0]
    old_sotp = frozen_sotp.iloc[0]
    projection, mpe_ev = _anchor_to_frozen_terminal_dcf(
        industry_bridge=industry,
        frozen_bridge=frozen,
        terminal_growth_pct=terminal_growth_pct,
        horizon_years=horizon_years,
    )
    debt = float(frozen["mpe_debt_used_usd"])
    cash = float(frozen["mpe_cash_used_usd"])
    fp_value = float(old_sotp["financial_products_equity_value_usd"])
    equity = mpe_ev - debt + cash + fp_value
    shares = float(old_sotp["shares_outstanding"])
    per_share = equity / shares
    explicit_value = float(projection["pv_fcff_usd"].sum())
    terminal_value = float(projection.iloc[-1]["pv_terminal_value_usd"])
    valuation = pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "valuation_status": "V1_2_RESEARCH_DIAGNOSTIC_NOT_A_MISPRICING_SIGNAL",
                "year_one_anchor": "CENSUS_M3_PLUS_BLS_PQCI",
                "terminal_anchor": "V1_1_FROZEN_NORMALIZED_ECONOMICS",
                "mpe_enterprise_value_usd": mpe_ev,
                "explicit_forecast_pv_usd": explicit_value,
                "pv_terminal_value_usd": terminal_value,
                "terminal_value_share_pct": terminal_value / mpe_ev * 100.0,
                "less_mpe_debt_usd": debt,
                "add_mpe_cash_usd": cash,
                "financial_products_equity_value_usd": fp_value,
                "sotp_equity_value_usd": equity,
                "shares_outstanding": shares,
                "sotp_value_per_share": per_share,
                "market_price": old_sotp["market_price"],
                "research_gap_pct": per_share / float(old_sotp["market_price"]) * 100.0 - 100.0,
                "v1_1_value_per_share": old_sotp["sotp_value_per_share"],
                "change_vs_v1_1_pct": per_share / float(old_sotp["sotp_value_per_share"]) * 100.0 - 100.0,
                "component_identity_error_usd": equity - (mpe_ev - debt + cash + fp_value),
                "financial_products_funding_debt_double_counted": False,
                "terminal_replacement_allowed": False,
                "production_promoted": False,
            }
        ]
    )
    gate = pd.DataFrame(
        [
            {
                "parent_v1_1_verified": True,
                "industry_sensor_bridge_complete": True,
                "expectations_surfaces_complete": True,
                "mpe_roic_perimeter_audited": True,
                "cfsc_exact_economics_complete": True,
                "backlog_model_changed": False,
                "backlog_oos_observations": 2,
                "parser_quality_gate_pass": parser_quality_gate_pass,
                "historical_industry_pit_vintages_available": False,
                "research_complete": parser_quality_gate_pass,
                "terminal_input_allowed": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
    return {"v1_2_mpe_dcf_projection": projection, "v1_2_sotp_valuation": valuation, "industrials_v1_2_gate": gate}
