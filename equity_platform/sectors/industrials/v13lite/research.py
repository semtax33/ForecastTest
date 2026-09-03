from __future__ import annotations

from pathlib import Path

from lxml import html
import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.v12.research import _anchor_to_frozen_terminal_dcf


def _financial_bridge(
    segment_forecast: pd.DataFrame,
    annual_history: pd.DataFrame,
) -> pd.DataFrame:
    latest = annual_history.iloc[-1]
    window = annual_history.tail(5)
    base_revenue = float(segment_forecast["base_fy2025_sales_usd"].sum())
    forecast_revenue = float(segment_forecast["forecast_fy2026_sales_usd"].sum())
    forecast_cost = float(segment_forecast["forecast_fy2026_operating_cost_usd"].sum())
    forecast_ebit = forecast_revenue - forecast_cost
    tax_rate = float(window["mpe_effective_tax_rate_pct"].median())
    forecast_nopat = forecast_ebit * (1.0 - tax_rate / 100.0)
    base_nopat = float(latest["mpe_nopat_usd"])
    sales_to_capital = float((window["mpe_total_revenue_usd"] / window["mpe_invested_capital_usd"]).median())
    reinvestment = (forecast_revenue - base_revenue) / sales_to_capital
    base_capital = float(latest["mpe_invested_capital_usd"])
    forecast_capital = base_capital + reinvestment
    average_capital = (base_capital + forecast_capital) / 2.0
    forecast_roic = forecast_nopat / average_capital * 100.0
    incremental_roic = (forecast_nopat - base_nopat) / reinvestment * 100.0 if abs(reinvestment) > 1.0 else np.nan
    growth = forecast_revenue / base_revenue * 100.0 - 100.0
    return pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "forecast_origin_fiscal_year": 2025,
                "target_fiscal_year": 2026,
                "anchor_architecture": "SEGMENT_IR_ACTUAL_PLUS_CAPTURE_CALIBRATED_INDUSTRY_BRIDGE",
                "base_revenue_usd": base_revenue,
                "forecast_revenue_usd": forecast_revenue,
                "forecast_revenue_lower_usd": float(segment_forecast["forecast_fy2026_sales_lower_usd"].sum()),
                "forecast_revenue_upper_usd": float(segment_forecast["forecast_fy2026_sales_upper_usd"].sum()),
                "forecast_revenue_growth_pct": growth,
                "base_operating_cost_usd": float(segment_forecast["base_fy2025_operating_cost_usd"].sum()),
                "forecast_operating_cost_usd": forecast_cost,
                "forecast_ebit_usd": forecast_ebit,
                "forecast_operating_margin_pct": forecast_ebit / forecast_revenue * 100.0,
                "historical_operating_margin_median_pct": float(window["mpe_operating_margin_pct"].median()),
                "normalized_tax_rate_pct": tax_rate,
                "forecast_nopat_usd": forecast_nopat,
                "historical_sales_to_capital": sales_to_capital,
                "required_reinvestment_usd": reinvestment,
                "reinvestment_rate_on_base_nopat": reinvestment / base_nopat,
                "forecast_invested_capital_usd": forecast_capital,
                "forecast_roic_pct": forecast_roic,
                "incremental_roic_pct": incremental_roic,
                "forecast_nopat_growth_pct": forecast_nopat / base_nopat * 100.0 - 100.0,
                "reinvestment_bridge_method": "PRIOR_REPORTED_SALES_TO_CAPITAL_CONDITIONAL_ON_CAPTURE_REVENUE",
                "reinvestment_bridge_validated": False,
                "snapshot_pit_status": "IR_ACTUAL_IS_PIT_BUT_INDUSTRY_HISTORY_IS_LATEST_REVISED_NOT_PIT",
                "historical_backtest_allowed": False,
                "forecast_performance_claim_allowed": False,
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )


def _reinvestment_validation(history: pd.DataFrame, minimum_observations: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = history.sort_values("fiscal_year").reset_index(drop=True).copy()
    frame["actual_delta_revenue_usd"] = frame["mpe_total_revenue_usd"].diff()
    frame["actual_delta_invested_capital_usd"] = frame["mpe_invested_capital_usd"].diff()
    rows: list[dict[str, object]] = []
    for index in range(2, len(frame)):
        prior = frame.iloc[:index]
        current = frame.iloc[index]
        sales_to_capital = float((prior["mpe_total_revenue_usd"] / prior["mpe_invested_capital_usd"]).median())
        predicted = float(current["actual_delta_revenue_usd"] / sales_to_capital)
        actual = float(current["actual_delta_invested_capital_usd"])
        rows.append(
            {
                "fiscal_year": int(current["fiscal_year"]),
                "training_years": len(prior),
                "realized_delta_revenue_usd": current["actual_delta_revenue_usd"],
                "prior_median_sales_to_capital": sales_to_capital,
                "conditional_predicted_reinvestment_usd": predicted,
                "actual_delta_invested_capital_usd": actual,
                "absolute_error_usd": abs(predicted - actual),
                "validation_semantics": "CONDITIONAL_ON_REALIZED_REVENUE_NOT_FULL_FORECAST_OOS",
            }
        )
    validation = pd.DataFrame(rows)
    scale = float(validation["actual_delta_invested_capital_usd"].diff().abs().dropna().mean())
    summary = pd.DataFrame(
        [
            {
                "validation_observations": len(validation),
                "minimum_observations_required": minimum_observations,
                "minimum_observations_met": len(validation) >= minimum_observations,
                "conditional_bridge_mae_usd": float(validation["absolute_error_usd"].mean()),
                "conditional_bridge_mase": float(validation["absolute_error_usd"].mean() / scale) if scale else np.nan,
                "realized_revenue_used_as_condition": True,
                "full_forecast_oos_validated": False,
                "reinvestment_bridge_validated": False,
                "status": "FAIL_CLOSED_CONDITIONAL_BRIDGE_ONLY",
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return validation, summary


def _duration_value(
    *,
    base_revenue: float,
    near_growth_pct: float,
    high_margin_pct: float,
    high_roic_pct: float,
    cap_years: int,
    tax_pct: float,
    wacc_pct: float,
    terminal_growth_pct: float,
    terminal_margin_pct: float,
    terminal_roic_pct: float,
) -> tuple[float, float, float]:
    revenue = base_revenue
    wacc = wacc_pct / 100.0
    tax = tax_pct / 100.0
    terminal_growth = terminal_growth_pct / 100.0
    explicit = 0.0
    for year in range(1, cap_years + 1):
        fade = (year - 1) / max(cap_years - 1, 1)
        growth = (near_growth_pct / 100.0) * (1.0 - fade) + terminal_growth * fade
        revenue *= 1.0 + growth
        nopat = revenue * high_margin_pct / 100.0 * (1.0 - tax)
        reinvestment = nopat * growth / (high_roic_pct / 100.0)
        explicit += (nopat - reinvestment) / ((1.0 + wacc) ** year)
    terminal_revenue = revenue * (1.0 + terminal_growth)
    terminal_nopat = terminal_revenue * terminal_margin_pct / 100.0 * (1.0 - tax)
    terminal_reinvestment = terminal_nopat * terminal_growth / (terminal_roic_pct / 100.0)
    terminal_fcff = terminal_nopat - terminal_reinvestment
    terminal = terminal_fcff / (wacc - terminal_growth) / ((1.0 + wacc) ** cap_years)
    return explicit + terminal, explicit, terminal


def _cap_surfaces(
    *,
    bridge: pd.Series,
    frozen_bridge: pd.Series,
    frozen_sotp: pd.Series,
    market_target_ev: float,
    cap_years: list[int],
    margins: list[float],
    roics: list[float],
    terminal_growth_pct: float,
    match_tolerance_pct: float,
) -> dict[str, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    debt = float(frozen_bridge["mpe_debt_used_usd"])
    cash = float(frozen_bridge["mpe_cash_used_usd"])
    fp_value = float(frozen_sotp["financial_products_equity_value_usd"])
    shares = float(frozen_sotp["shares_outstanding"])
    for duration in cap_years:
        for margin in margins:
            for roic in roics:
                ev, explicit, terminal = _duration_value(
                    base_revenue=float(bridge["base_revenue_usd"]),
                    near_growth_pct=float(bridge["forecast_revenue_growth_pct"]),
                    high_margin_pct=margin,
                    high_roic_pct=roic,
                    cap_years=duration,
                    tax_pct=float(frozen_bridge["normalized_tax_rate_pct"]),
                    wacc_pct=float(frozen_bridge["mpe_wacc_pct"]),
                    terminal_growth_pct=terminal_growth_pct,
                    terminal_margin_pct=float(frozen_bridge["normalized_operating_margin_pct"]),
                    terminal_roic_pct=float(frozen_bridge["normalized_roic_pct"]),
                )
                gap = ev / market_target_ev * 100.0 - 100.0
                rows.append(
                    {
                        "cap_years": duration,
                        "high_margin_pct": margin,
                        "high_roic_pct": roic,
                        "mpe_enterprise_value_usd": ev,
                        "explicit_pv_usd": explicit,
                        "terminal_pv_usd": terminal,
                        "terminal_value_share_pct": terminal / ev * 100.0,
                        "market_target_mpe_enterprise_value_usd": market_target_ev,
                        "market_value_gap_pct": gap,
                        "market_match": abs(gap) <= match_tolerance_pct,
                        "sotp_value_per_share": (ev - debt + cash + fp_value) / shares,
                        "appropriate_cap_claim_allowed": False,
                        "terminal_input_allowed": False,
                    }
                )
    three_dimensional = pd.DataFrame(rows)
    nearest = three_dimensional.loc[three_dimensional["market_value_gap_pct"].abs().groupby(three_dimensional["cap_years"]).idxmin()].copy()
    margin_cap = three_dimensional.loc[np.isclose(three_dimensional["high_roic_pct"], float(frozen_bridge["normalized_roic_pct"]))].copy()
    summary = pd.DataFrame(
        [
            {
                "margin_cap_points": len(margin_cap),
                "margin_roic_cap_points": len(three_dimensional),
                "market_match_points": int(three_dimensional["market_match"].sum()),
                "nearest_absolute_gap_pct": float(three_dimensional["market_value_gap_pct"].abs().min()),
                "non_identification_preserved": True,
                "appropriate_cap_claim_allowed": False,
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return {"cap_surface_margin_duration": margin_cap, "cap_surface_margin_roic_duration": three_dimensional, "cap_surface_nearest_by_duration": nearest, "cap_surface_summary": summary}


def _financial_products_residual_audit(
    *,
    annual_history: pd.DataFrame,
    cfsc_history: pd.DataFrame,
    latest_cat_path: Path,
) -> pd.DataFrame:
    cat = annual_history.iloc[-1]
    cfsc = cfsc_history.iloc[-1]
    source_text = " ".join(html.fromstring(latest_cat_path.read_bytes()).text_content().split())
    phrases = []
    for needle in ["We determine Financial Products Segment profit", "Financial Products — Our finance and insurance subsidiaries"]:
        start = source_text.find(needle)
        if start >= 0:
            phrases.append(source_text[start : start + 360])
    cat_pretax = float(cat["financial_products_pretax_profit_usd"])
    cat_tax = float(cat["financial_products_income_tax_usd"])
    cat_net = float(cat["financial_products_profit_usd"])
    cfsc_pretax = float(cfsc["pretax_profit_usd"])
    cfsc_tax = float(cfsc["income_tax_usd"])
    cfsc_net = float(cfsc["standalone_profit_usd"])
    return pd.DataFrame(
        [
            {
                "fiscal_year": int(cat["fiscal_year"]),
                "cat_financial_products_pretax_usd": cat_pretax,
                "cfsc_standalone_pretax_usd": cfsc_pretax,
                "pretax_perimeter_residual_usd": cat_pretax - cfsc_pretax,
                "cat_financial_products_tax_usd": cat_tax,
                "cfsc_standalone_tax_usd": cfsc_tax,
                "tax_perimeter_residual_usd": cat_tax - cfsc_tax,
                "cat_financial_products_net_profit_usd": cat_net,
                "cfsc_standalone_net_profit_usd": cfsc_net,
                "reported_net_perimeter_residual_usd": cat_net - cfsc_net,
                "bridge_implied_net_residual_usd": (cat_pretax - cfsc_pretax) - (cat_tax - cfsc_tax),
                "rounding_and_affiliate_residual_usd": (cat_net - cfsc_net) - ((cat_pretax - cfsc_pretax) - (cat_tax - cfsc_tax)),
                "bridge_level_attribution_identified": True,
                "economic_subcomponent_attribution_identified": False,
                "perimeter_evidence": "CAT_FINANCE_AND_INSURANCE_SUBSIDIARIES_INCLUDING_CFSC_AND_INSURANCE_SERVICES",
                "measurement_evidence": "FINANCIAL_PRODUCTS_SEGMENT_PROFIT_IS_PRETAX",
                "source_excerpt": " | ".join(phrases),
                "source_path": str(latest_cat_path),
                "status": "BRIDGE_RECONCILED_SUBCOMPONENTS_STILL_UNIDENTIFIED",
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )


def build_v13_lite_research(
    *,
    capture_results: dict[str, pd.DataFrame],
    annual_history: pd.DataFrame,
    cfsc_history: pd.DataFrame,
    latest_cat_path: Path,
    frozen_bridge: pd.DataFrame,
    frozen_sotp: pd.DataFrame,
    frozen_reverse: pd.DataFrame,
    v12_sotp: pd.DataFrame,
    segment_capex_history: pd.DataFrame,
    terminal_growth_pct: float,
    cap_years: list[int],
    cap_margins: list[float],
    cap_roics: list[float],
    market_match_tolerance_pct: float,
    minimum_validation_observations: int,
    ir_parser_gate_pass: bool,
) -> dict[str, pd.DataFrame]:
    bridge_frame = _financial_bridge(capture_results["segment_fy2026_forecast"], annual_history)
    bridge = bridge_frame.iloc[0]
    frozen = frozen_bridge.iloc[0]
    sotp = frozen_sotp.iloc[0]
    projection, mpe_ev = _anchor_to_frozen_terminal_dcf(
        industry_bridge=bridge,
        frozen_bridge=frozen,
        terminal_growth_pct=terminal_growth_pct,
        horizon_years=5,
    )
    equity = mpe_ev - float(frozen["mpe_debt_used_usd"]) + float(frozen["mpe_cash_used_usd"]) + float(sotp["financial_products_equity_value_usd"])
    per_share = equity / float(sotp["shares_outstanding"])
    valuation = pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "valuation_status": "V1_3_LITE_CALIBRATION_DIAGNOSTIC_NOT_A_PERFORMANCE_OR_MISPRICING_SIGNAL",
                "year_one_anchor": bridge["anchor_architecture"],
                "terminal_anchor": "V1_1_FROZEN_NORMALIZED_ECONOMICS",
                "mpe_enterprise_value_usd": mpe_ev,
                "explicit_forecast_pv_usd": float(projection["pv_fcff_usd"].sum()),
                "pv_terminal_value_usd": float(projection.iloc[-1]["pv_terminal_value_usd"]),
                "terminal_value_share_pct": float(projection.iloc[-1]["pv_terminal_value_usd"] / mpe_ev * 100.0),
                "sotp_equity_value_usd": equity,
                "shares_outstanding": sotp["shares_outstanding"],
                "sotp_value_per_share": per_share,
                "market_price": sotp["market_price"],
                "research_gap_pct": per_share / float(sotp["market_price"]) * 100.0 - 100.0,
                "v1_1_value_per_share": sotp["sotp_value_per_share"],
                "v1_2_value_per_share": v12_sotp.iloc[0]["sotp_value_per_share"],
                "historical_industry_pit_vintages_available": False,
                "terminal_replacement_allowed": False,
                "production_promoted": False,
            }
        ]
    )
    reinvestment, reinvestment_summary = _reinvestment_validation(annual_history, minimum_validation_observations)
    latest_capex = segment_capex_history.iloc[-1]
    capex_context = pd.DataFrame(
        [
            {
                "forecast_required_reinvestment_usd": bridge["required_reinvestment_usd"],
                "latest_mpe_capex_proxy_usd": latest_capex["mpe_capex_proxy_usd"],
                "required_reinvestment_to_latest_mpe_capex_pct": bridge["required_reinvestment_usd"] / latest_capex["mpe_capex_proxy_usd"] * 100.0,
                "comparison_semantics": "NET_REINVESTMENT_REQUIREMENT_VS_GROSS_CAPEX_CONTEXT_ONLY",
                "accounting_identity_claim_allowed": False,
                "reinvestment_bridge_validated": False,
                "terminal_input_allowed": False,
            }
        ]
    )
    caps = _cap_surfaces(
        bridge=bridge,
        frozen_bridge=frozen,
        frozen_sotp=sotp,
        market_target_ev=float(frozen_reverse.iloc[0]["market_target_mpe_enterprise_value_usd"]),
        cap_years=cap_years,
        margins=cap_margins,
        roics=cap_roics,
        terminal_growth_pct=terminal_growth_pct,
        match_tolerance_pct=market_match_tolerance_pct,
    )
    residual = _financial_products_residual_audit(annual_history=annual_history, cfsc_history=cfsc_history, latest_cat_path=latest_cat_path)
    validation = capture_results["capture_temporal_validation"]
    gate = pd.DataFrame(
        [
            {
                "parent_v1_2_architecture_verified": True,
                "arcana_ir_html_used": True,
                "ir_parser_gate_pass": ir_parser_gate_pass,
                "capture_validation_observations": len(validation),
                "minimum_capture_observations_met": len(validation) >= minimum_validation_observations,
                "historical_industry_pit_vintages_available": False,
                "capture_forecast_performance_validated": False,
                "margin_forecast_performance_validated": False,
                "reinvestment_bridge_validated": False,
                "cfsc_residual_bridge_reconciled": bool(residual.iloc[0]["bridge_level_attribution_identified"]),
                "cfsc_residual_subcomponents_identified": False,
                "cap_surface_complete": True,
                "backlog_model_changed": False,
                "backlog_oos_observations": 2,
                "pdf_parsing_deferred": True,
                "research_complete": bool(ir_parser_gate_pass),
                "terminal_input_allowed": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
    return {
        "capture_calibrated_financial_bridge": bridge_frame,
        "v1_3_lite_mpe_dcf_projection": projection,
        "v1_3_lite_sotp_valuation": valuation,
        "reinvestment_conditional_validation": reinvestment,
        "reinvestment_validation_summary": reinvestment_summary,
        "reinvestment_capex_context": capex_context,
        "financial_products_residual_bridge_audit": residual,
        **caps,
        "industrials_v1_3_lite_gate": gate,
    }
