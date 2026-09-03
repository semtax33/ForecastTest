from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from equity_platform.artifacts import hash_files
from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v16.benchmark import verify_revenue_champion_v1


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output/industrials_valuation_v1_7_research"


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_frozen_revenue_parent_and_all_html_sources_are_verified() -> None:
    parent = verify_revenue_champion_v1(ROOT)
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    audit = read("v1_7_source_audit_summary").iloc[0]
    assert parent["manifest_sha256"] == metadata["revenue_champion_manifest_sha256"]
    assert metadata["revenue_champion_verified_after"]
    assert hash_files(ROOT, metadata["source_hashes"].keys()) == metadata["source_hashes"]
    assert audit["sec_filings"] == 23
    assert audit["sec_10k_filings"] == 6
    assert audit["sec_10q_filings"] == 17
    assert audit["ir_earnings_releases"] == 23
    assert bool(audit["periodic_filing_inventory_complete"])
    assert bool(audit["source_gate_pass"])
    assert not bool(audit["pdf_parsing_used"])


def test_profit_driver_parser_never_fabricates_undisclosed_components() -> None:
    evidence = read("company_reported_profit_driver_evidence")
    bridge = read("company_reported_profit_bridge")
    summary = read("company_reported_profit_driver_summary")
    assert summary["profit_passages_found"].eq(23).all()
    assert summary["passage_coverage_pct"].eq(100.0).all()
    assert summary["profit_driver_parser_pass"].astype(bool).all()
    assert (summary["fully_explained_quarters"] <= summary["quarters_with_numeric_driver"]).all()
    assert bridge["reported_bridge_identity_error_usd"].abs().max() <= 1.0
    assert bridge["unallocated_residual_explicit"].astype(bool).all()
    assert evidence.loc[~evidence["numeric_disclosure"].astype(bool), "reported_driver_change_usd"].isna().all()
    q2 = evidence.loc[evidence["period"].eq("2025Q2") & evidence["segment"].eq("resource")].set_index("driver")
    assert q2.loc["PRICE_REALIZATION", "reported_driver_change_usd"] == -94e6
    assert q2.loc["MANUFACTURING_COST", "reported_driver_change_usd"] == -44e6
    assert q2.loc["SALES_VOLUME_MIX", "reported_driver_change_usd"] == -31e6


def test_power_energy_product_mix_is_pit_and_scope_change_is_explicit() -> None:
    mix = read("power_energy_application_mix")
    summary = read("power_energy_application_mix_summary").iloc[0]
    validation = read("margin_route_walk_forward")
    assert summary["quarters"] == summary["tables_found"] == 23
    assert summary["full_four_application_quarters"] == 21
    assert summary["scope_change_rows"] == 1
    assert "transportation" not in summary["latest_scope"]
    assert bool(summary["product_mix_history_ready"])
    assert validation["application_mix_available_at_origin"].astype(bool).all()
    p_and_e = validation.loc[validation["segment"].eq("power_energy")]
    assert p_and_e["application_mix_reference_period"].eq(
        p_and_e["period"].map(lambda value: str(pd.Period(value, freq="Q") - 1))
    ).all()
    assert mix.loc[mix["period"].eq("2026Q1"), "application_scope_change"].astype(bool).all()


def test_reported_and_comparable_margin_perimeters_reconcile_exactly() -> None:
    perimeter = read("reported_comparable_margin_perimeter")
    validation = perimeter.loc[perimeter["period"].ge("2025Q1")]
    assert validation["margin_perimeter_identity_pass"].astype(bool).all()
    assert validation["margin_perimeter_identity_error_pct_points"].abs().max() <= 1e-10
    flagged = validation.loc[validation["unforecastable_scope_change"].astype(bool)]
    assert len(flagged) == 4
    assert set(flagged["segment"]) == {"power_energy", "resource"}
    assert flagged["scope_change_treatment"].eq("UNFORECASTABLE_SCOPE_CHANGE").all()


def test_predeclared_margin_routes_create_two_research_champions() -> None:
    summary = read("margin_route_summary").set_index("segment")
    validation = read("margin_route_walk_forward")
    assert validation.groupby("segment").size().eq(6).all()
    assert validation["route_selected_without_oos_peeking"].astype(bool).all()
    assert validation["historical_pit_input"].astype(bool).all()
    assert validation["actual_after_forecast"].astype(bool).all()
    assert summary.loc["construction", "predeclared_route"] == "STRUCTURAL_PROFIT_DRIVER"
    assert summary.loc["construction", "selected_margin_mase"] == pytest.approx(1.098663, abs=1e-5)
    assert not bool(summary.loc["construction", "margin_champion_eligible"])
    assert summary.loc["power_energy", "predeclared_route"] == "REDUCED_FORM_PRODUCT_MIX"
    assert summary.loc["power_energy", "selected_margin_mase"] == pytest.approx(0.805961, abs=1e-5)
    assert summary.loc["resource", "selected_margin_mase"] == pytest.approx(0.822923, abs=1e-5)
    assert int(summary["margin_champion_eligible"].sum()) == 2


def test_10k_and_10q_note_chain_keeps_reinvestment_layers_separate() -> None:
    annual = read("annual_reinvestment_roic_bridge")
    quarterly = read("quarterly_reinvestment_note_bridge")
    coverage = read("annual_note_fact_coverage")
    summary = read("reinvestment_roic_evidence_summary").iloc[0]
    assert len(annual) == 6
    assert summary["periodic_filings_parsed"] == 23
    assert summary["raw_relevant_xbrl_facts"] == 10250
    assert summary["quarterly_discrete_complete_rows"] == 20
    assert summary["critical_metric_minimum_coverage_pct"] == 100.0
    assert annual["inventory_note_identity_pass"].astype(bool).all()
    assert np.allclose(
        annual["gross_productive_asset_capex_usd"],
        annual["capex_usd"] + annual["equipment_on_lease_capex_usd"],
    )
    assert np.allclose(
        annual["total_including_mna_reinvestment_proxy_usd"],
        annual["core_reinvestment_proxy_usd"] + annual["research_development_usd"] + annual["business_acquisitions_usd"],
        equal_nan=True,
    )
    assert coverage.loc[coverage["metric"].eq("warranty_accrual_usd"), "coverage_pct"].iloc[0] == 100.0
    assert (~quarterly["terminal_input_allowed"].astype(bool)).all()
    assert bool(summary["mpe_and_consolidated_perimeters_kept_separate"])
    assert not bool(summary["terminal_input_allowed"])


def test_v1_7_research_freezes_but_valuation_and_production_remain_locked() -> None:
    gate = read("industrials_v1_7_gate").iloc[0]
    authority = read("margin_route_authority").set_index("segment")
    valuation = read("v1_7_valuation_authority").iloc[0]
    assert bool(gate["research_freeze_eligible"])
    assert gate["status"] == "RESEARCH_FROZEN"
    assert gate["margin_champion_segments"] == 2
    assert gate["unforecastable_scope_change_rows"] == 4
    assert not bool(gate["unforecastable_scope_changes_used_as_component_claims"])
    assert not bool(authority["component_attribution_allowed"].any())
    assert authority.loc["power_energy", "reduced_form_route"]
    assert authority.loc["resource", "reduced_form_route"]
    assert not bool(gate["terminal_input_allowed"])
    assert not bool(gate["new_dcf_run"])
    assert not bool(gate["new_reverse_dcf_run"])
    assert str(gate["live_matched_observations"]) == "0/20"
    assert not bool(gate["production_promotable"])
    assert valuation["new_reverse_dcf_result"] == "NOT_RUN_BY_DESIGN"
    assert np.isnan(valuation["new_dcf_value_per_share_usd"])
    assert valuation["v1_3_lite_reference_value_per_share_usd"] == pytest.approx(399.1175)
