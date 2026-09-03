from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.aerospace_defense.hii_v54 import (
    verify_hii_v54_margin_mechanism_research,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/industrials_v6_gd_fourth_company_research"


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / name)


def test_gd_sources_and_parser_are_complete_without_hiding_the_open_bridge():
    source = read("gd_sec_source_summary.csv").iloc[0]
    parser = read("gd_ir_parser_summary.csv").iloc[0]
    recon = read("gd_sec_ir_reconciliation.csv")
    assert (source["sec_10k_filings"], source["sec_10q_filings"]) == (7, 20)
    assert source["sec_hash_matches"] == 27
    assert bool(source["source_gate_pass"])
    assert parser["earnings_releases"] == 23
    assert parser["segment_quarter_rows"] == 92
    assert parser["backlog_segment_quarter_rows"] == 92
    assert parser["aerospace_delivery_quarters"] == 23
    assert bool(parser["parser_gate_pass"])
    revenue = recon.loc[recon["metric"].eq("revenue")]
    operating = recon.loc[recon["metric"].eq("operating_income")]
    assert revenue["identity_pass"].all()
    unresolved = operating.loc[~operating["identity_pass"]]
    assert len(unresolved) == 1
    assert unresolved.iloc[0]["period"] == "2020Q4"
    assert abs(unresolved.iloc[0]["difference_usd"]) == 26_000_000


def test_gd_industry_features_are_pit_and_revised_context_is_excluded():
    summary = read("gd_industry_data_summary.csv").iloc[0]
    pit = read("gd_pit_feature_summary.csv").iloc[0]
    authority = read("gd_industry_sensor_authority.csv")
    assert bool(summary["historical_pit_ready"])
    assert pit["cutoff_violations"] == 0
    assert pit["segments"] == 4
    assert pit["forecast_periods"] == 15
    revised = authority.loc[~authority["historical_pit_eligible"].astype(bool)]
    assert not revised["model_input_allowed"].astype(bool).any()
    assert not bool(summary["current_revised_labor_used_in_oos_claim"])


def test_gd_fixed_oos_performance_and_delivery_challenger_are_honest():
    segment = read("gd_portability_summary.csv")
    company = read("gd_company_portability_summary.csv").iloc[0]
    delivery = read("gd_aerospace_delivery_challenger_summary.csv").iloc[0]
    walk = read("gd_portability_walk_forward.csv")
    assert len(walk) == 24
    assert walk["actual_after_forecast"].astype(bool).all()
    assert walk["historical_pit_input"].astype(bool).all()
    assert segment["validation_observations"].eq(6).all()
    assert segment["funded_backlog_revenue_champion_eligible"].sum() == 2
    assert segment["margin_champion_eligible"].sum() == 2
    assert segment["joint_champion"].sum() == 1
    assert np.isclose(company["funded_backlog_revenue_mase"], 0.2597918682)
    assert np.isclose(company["margin_mase"], 0.4816598199)
    assert bool(company["funded_backlog_revenue_champion_eligible"])
    assert bool(company["margin_champion_eligible"])
    assert delivery["revenue_mase"] > 1.0
    assert not bool(delivery["revenue_champion_eligible"])
    assert bool(delivery["predeclared_challenger_not_posthoc_selected"])


def test_gd_prospective_anchor_bridge_and_accounting_identities():
    forecast = read("gd_2026q3_prospective_segment_forecast.csv")
    bridge = read("gd_2026q3_conditional_financial_bridge.csv").iloc[0]
    assert len(forecast) == 4
    assert forecast["period"].eq("2026Q3").all()
    assert forecast["actual_not_yet_used"].astype(bool).all()
    assert not forecast["margin_boundary_hit"].astype(bool).any()
    assert np.isclose(forecast["predicted_sales_usd"].sum(), bridge["company_revenue_usd"])
    assert np.isclose(
        forecast["predicted_operating_profit_usd"].sum(),
        bridge["company_operating_profit_usd"],
    )
    assert np.isclose(
        bridge["growth_roic_implied_reinvestment_rate_pct"],
        bridge["company_revenue_growth_pct"] / bridge["conditional_roic_pct"] * 100.0,
    )
    assert not bool(bridge["innovation_adjusted_reinvestment_claim_allowed"])


def test_gd_margin_roic_and_terminal_authority_stay_separate():
    margin = read("gd_margin_distribution_summary.csv")
    hypothesis = read("gd_terminal_margin_hypothesis_audit.csv")
    roic = read("gd_roic_reinvestment_research_summary.csv").iloc[0]
    normalized = margin.loc[
        margin["distribution"].eq("LATEST_MIX_CONTEMPORANEOUS_TTM")
    ].iloc[0]
    assert normalized["observations"] == 20
    assert normalized["minimum_pct"] < normalized["median_pct"] < normalized["maximum_pct"]
    assert hypothesis["terminal_input_allowed"].astype(bool).sum() == 0
    assert not hypothesis["structural_mechanism_independently_identified"].astype(bool).any()
    assert roic["reported_roic_observations"] == 6
    assert roic["r_and_d_authority"] == "R_AND_D_NOT_IDENTIFIED_NOT_ZERO_AUTHORITY"
    assert not bool(roic["innovation_adjusted_reinvestment_claim_allowed"])


def test_gd_dcf_reverse_dcf_fail_closed_and_no_fair_value_claim():
    projection = read("gd_dcf_projections.csv")
    scenario = read("gd_dcf_scenario_assumptions_and_values.csv")
    reverse = read("gd_reverse_dcf_diagnostics.csv")
    summary = read("gd_conditional_valuation_summary.csv").iloc[0]
    assert np.allclose(
        projection["nopat_usd"],
        projection["ebit_usd"] * (1.0 - projection["tax_rate_pct"] / 100.0),
    )
    assert np.allclose(
        projection["reinvestment_rate_pct"],
        projection["revenue_growth_pct"] / projection["roic_pct"] * 100.0,
    )
    assert np.allclose(
        projection["fcff_usd"], projection["nopat_usd"] - projection["reinvestment_usd"]
    )
    assert scenario["ev_to_common_equity_identity_error_usd"].le(1.0).all()
    assert reverse["status"].isin(["SOLVED", "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"]).all()
    growth = reverse.loc[reverse["diagnostic"].eq("MARKET_IMPLIED_NEAR_TERM_GROWTH")].iloc[0]
    assert growth["status"] == "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"
    assert bool(summary["reverse_solver_fail_closed"])
    assert summary["round_trip_growth_error_pct"] < 1e-8
    assert bool(summary["high_terminal_dependence"])
    assert not bool(summary["fair_value_claim_allowed"])
    assert not bool(summary["terminal_input_allowed"])


def test_gd_gate_cross_company_and_frozen_parent():
    gate = read("industrials_v6_gd_gate.csv").iloc[0]
    cross = read("aerospace_defense_four_company_summary.csv")
    parent = verify_hii_v54_margin_mechanism_research(ROOT)
    assert parent["verified_files"] > 0
    assert bool(gate["hii_v54_parent_unchanged"])
    assert bool(gate["forecast_research_freeze_eligible"])
    assert not bool(gate["terminal_gate_pass"])
    assert not bool(gate["fair_value_claim_allowed"])
    assert gate["live_matched_observations"] == "0/20"
    assert not cross["four_company_industry_law_claim_allowed"].astype(bool).any()
