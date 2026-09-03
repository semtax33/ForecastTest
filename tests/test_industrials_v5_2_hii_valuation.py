from __future__ import annotations

import pandas as pd
import pytest

from equity_platform.paths import PROJECT_ROOT


OUTPUT = PROJECT_ROOT / "output/industrials_v5_2_hii_conditional_valuation_research"


def test_10k_10q_ir_and_industry_coverage_is_pit() -> None:
    coverage = pd.read_csv(OUTPUT / "hii_v52_source_coverage.csv").set_index("layer")
    assert coverage.loc["SEC_10K", "source_count"] == 7
    assert coverage.loc["SEC_10Q", "source_count"] == 20
    assert coverage.loc["IR_HTML", "source_count"] == 27
    assert coverage.loc["BLS_AS_RELEASED_VINTAGE", "source_count"] == 3
    assert coverage.loc["ANALYST_CONSENSUS_PROVIDER", "source_count"] == 3
    assert coverage["pit_cutoff_pass"].all()
    audit = pd.read_csv(OUTPUT / "hii_2026q3_pit_vintage_audit.csv")
    assert audit["cutoff_respected"].all()
    assert pd.to_datetime(audit["latest_selected_release_date"]).le(
        pd.Timestamp("2026-07-31")
    ).all()


def test_ir_guidance_builds_revenue_margin_capex_and_fcf_bridge() -> None:
    guide = pd.read_csv(OUTPUT / "hii_2026_guidance_financial_bridge.csv").iloc[0]
    assert guide["shipbuilding_revenue_low_usd"] == 10.2e9
    assert guide["shipbuilding_revenue_high_usd"] == 10.4e9
    assert guide["mission_revenue_low_usd"] == 3.0e9
    assert guide["mission_revenue_high_usd"] == 3.2e9
    assert guide["company_revenue_midpoint_usd"] == 13.25e9
    assert guide["consolidated_operating_margin_midpoint_pct"] == pytest.approx(5.5452830189)
    assert guide["depreciation_amortization_midpoint_usd"] == 330e6
    assert (guide["levered_free_cash_flow_low_usd"], guide["levered_free_cash_flow_high_usd"]) == (500e6, 600e6)
    assert guide["source_sha256"] == "7597b77e8082170248de963248d8e2ef5284b65aab82cdef97390d89abce8e09"
    assert not guide["pdf_parsing_used"]


def test_quarterly_nwc_and_ttm_fcff_identity_are_complete() -> None:
    quarterly = pd.read_csv(OUTPUT / "hii_extended_quarterly_financial_bridge.csv")
    latest = quarterly.loc[quarterly["period"].eq("2026Q2")].iloc[0]
    assert latest["nwc_chain_complete"]
    assert latest["accounts_receivable_usd"] == 452e6
    assert latest["contract_assets_usd"] == 2.154e9
    assert latest["contract_liabilities_usd"] == 690e6
    assert latest["operating_nwc_usd"] == 1.415e9
    assert latest["change_operating_nwc_yoy_usd"] == 631e6
    ttm = pd.read_csv(OUTPUT / "hii_ttm_fcff_bridge.csv").iloc[0]
    assert ttm["ttm_quarters"] == 4
    assert ttm["revenue_usd"] == 13.185e9
    assert ttm["quarterly_nwc_chain_complete"]
    assert ttm["fcff_identity_pass"]
    assert ttm["fcff_identity_error_usd"] <= 1.0
    assert ttm["fcff_accounting_core_usd"] + ttm["other_operating_accruals_and_noncash_usd"] == pytest.approx(ttm["fcff_cash_proxy_usd"])


def test_consensus_is_a_vintage_diagnostic_not_a_fit_target() -> None:
    detail = pd.read_csv(OUTPUT / "hii_consensus_vintage_detail.csv")
    summary = pd.read_csv(OUTPUT / "hii_consensus_summary.csv").iloc[0]
    comparison = pd.read_csv(OUTPUT / "hii_model_vs_consensus.csv").iloc[0]
    assert set(detail["provider"]) == {"ALPHA_VANTAGE", "FMP", "YAHOO"}
    assert len(detail) == 6
    assert summary["providers"] == 3
    assert summary["post_ir_providers"] == 2
    assert not summary["consensus_is_model_input"]
    assert not comparison["consensus_used_to_fit_model"]
    assert comparison["model_route"] == "IR_GUIDANCE_ACCOUNTING_BRIDGE"


def test_clean_prospective_route_uses_backlog_and_bls_without_future_actual() -> None:
    route = pd.read_csv(OUTPUT / "hii_2026q3_clean_prospective_revenue_route.csv").iloc[0]
    features = pd.read_csv(OUTPUT / "hii_2026q3_pit_industry_features.csv")
    assert route["target_period"] == "2026Q3"
    assert route["selected_route"] == "PREDECLARED_EQUAL_BLEND"
    assert route["clean_prospective_benchmark"]
    assert not route["actual_available"]
    assert route["latest_backlog_usd"] == 57.3e9
    assert len(features) == 3
    assert features["historical_pit_eligible"].all()


def test_independent_wacc_and_market_bridge_are_reconciled() -> None:
    beta = pd.read_csv(OUTPUT / "hii_beta_peer_cross_check.csv")
    wacc = pd.read_csv(OUTPUT / "hii_wacc_range.csv").iloc[0]
    market = pd.read_csv(OUTPUT / "hii_market_capitalization_bridge.csv").iloc[0]
    assert set(beta["ticker"]) == {"HII", "LMT", "NOC", "GD", "RTX"}
    assert beta["weekly_observations"].min() >= 100
    assert wacc["wacc_is_independent_of_market_price_fit"]
    assert not wacc["geopolitical_cash_flow_risk_added_to_wacc"]
    assert wacc["risk_channel_double_count_count"] == 0
    assert wacc["symmetric_wacc_pct"] < wacc["downside_wacc_pct"]
    assert market["market_price"] == pytest.approx(324.0150146484)
    assert market["shares_outstanding"] == 39_404_203
    assert market["ev_to_equity_bridge_identity_error_usd"] <= 1.0


def test_dcf_reverse_dcf_and_round_trip_fail_closed() -> None:
    scenario = pd.read_csv(OUTPUT / "hii_dcf_scenario_assumptions_and_values.csv")
    reverse = pd.read_csv(OUTPUT / "hii_reverse_dcf_diagnostics.csv").set_index("diagnostic")
    round_trip = pd.read_csv(OUTPUT / "hii_dcf_reverse_round_trip.csv").iloc[0]
    summary = pd.read_csv(OUTPUT / "hii_conditional_valuation_summary.csv").iloc[0]
    assert set(scenario["scenario"]) == {"bear", "base", "bull"}
    assert scenario["ev_to_common_equity_identity_error_usd"].le(1.0).all()
    assert scenario["terminal_value_share_pct"].between(0.0, 100.0).all()
    assert reverse["status"].isin(["SOLVED", "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"]).all()
    assert reverse.loc["MARKET_IMPLIED_NEAR_TERM_GROWTH", "status"] == "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"
    assert reverse.loc["MARKET_IMPLIED_TERMINAL_MARGIN", "status"] == "SOLVED"
    assert reverse.loc["MARKET_IMPLIED_WACC", "status"] == "SOLVED"
    assert not reverse["appropriate_parameter_claim_allowed"].any()
    assert round_trip["status"] == "SOLVED"
    assert round_trip["growth_round_trip_error_pct"] <= 1e-7
    assert summary["high_terminal_dependence"]
    assert not summary["terminal_authority"]
    assert not summary["production_promoted"]


def test_terminal_margin_wacc_surface_exposes_non_identification() -> None:
    surface = pd.read_csv(OUTPUT / "hii_terminal_margin_wacc_expectations_surface.csv")
    iso = pd.read_csv(OUTPUT / "hii_terminal_margin_conditional_implied_wacc.csv")
    assert len(surface) == 48
    assert surface["terminal_margin_pct"].nunique() == 8
    assert surface["wacc_pct"].nunique() == 6
    assert surface["conditional_on_base_growth_and_roic"].all()
    assert not surface["terminal_authority"].any()
    assert len(iso) == 8
    assert iso["status"].isin(["SOLVED", "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"]).all()
    solved = iso.loc[iso["status"].eq("SOLVED")].sort_values("terminal_margin_pct")
    assert len(solved) >= 6
    assert solved["market_implied_wacc_pct"].is_monotonic_increasing
    assert not iso["appropriate_wacc_claim_allowed"].any()


def test_v52_gate_allows_research_run_but_not_terminal_or_production() -> None:
    gate = pd.read_csv(OUTPUT / "hii_v52_gate.csv").iloc[0]
    assert gate["research_freeze_eligible"]
    assert gate["dcf_run"] and gate["reverse_dcf_run"]
    assert gate["solver_round_trip_pass"]
    assert gate["ev_to_equity_identity_pass"]
    assert not gate["terminal_authority"]
    assert not gate["production_promoted"]
    assert gate["live_forward_matched_observations"] == "0/20"
