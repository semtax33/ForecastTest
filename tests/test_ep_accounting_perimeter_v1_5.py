from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.research.ep_v14.benchmark import verify_v14
from energy_nowcast.research.ep_v15.benchmark import verify_v15
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_5_research"


def test_v1_5_frozen_research_manifest_verifies() -> None:
    manifest = verify_v15(ROOT)
    assert manifest["research_frozen"] is True
    assert manifest["accounting_perimeter_framework_frozen"] is True
    assert manifest["route_aware_reserve_extraction_frozen"] is True
    assert manifest["route_aware_reserve_chain_ready_tickers"] == 4
    assert manifest["reserve_coverage_target_met"] is False
    assert manifest["company_incremental_roic_validated_tickers"] == 0
    assert manifest["terminal_anchor_ready"] == 0
    assert manifest["production_promoted"] is False
    assert manifest["live_matched_observations"] == "0/20"
    assert manifest["verified_files"] == 18


def test_v1_5_preserves_every_frozen_parent_and_is_research_only() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["v1_manifest_sha256"] == verify_v1(ROOT)["manifest_sha256"]
    assert metadata["v1_1_manifest_sha256"] == verify_v11(ROOT)["manifest_sha256"]
    assert metadata["v1_2_manifest_sha256"] == verify_v12(ROOT)["manifest_sha256"]
    assert metadata["v1_3_manifest_sha256"] == verify_v13(ROOT)["manifest_sha256"]
    assert metadata["v1_4_manifest_sha256"] == verify_v14(ROOT)["manifest_sha256"]
    assert metadata["frozen_parent_mutated"] is False
    assert metadata["wacc_range_recalibrated"] is False
    assert metadata["v1_1_mutation_allowed"] is False
    assert metadata["production_promoted"] is False


def test_accounting_perimeter_gate_uses_same_year_margins_and_fails_closed() -> None:
    annual = pd.read_csv(
        OUTPUT / "annual_accounting_perimeter_reconciliation.csv"
    )
    summary = pd.read_csv(
        OUTPUT / "accounting_perimeter_reconciliation_summary.csv"
    ).set_index("ticker")
    cnx = summary.loc["CNX"]
    assert cnx["comparable_years_2021_2025"] == 4
    assert cnx["green_years"] == 3
    assert cnx["red_years"] == 1
    assert cnx["median_absolute_raw_margin_gap_pct_points"] < 5.0
    assert bool(cnx["numeric_reconciliation_pass"])
    assert cnx["accounting_perimeter_reconciliation_gate"] == (
        "LOCKED_NUMERIC_PASS_HEDGE_PRESENTATION_NOT_PROVEN"
    )
    assert summary.loc["AR", "accounting_perimeter_reconciliation_gate"] == (
        "LOCKED_INCOMPLETE_STANDARDIZED_COST_SCOPE"
    )
    assert summary.loc["FANG", "accounting_perimeter_reconciliation_gate"] == (
        "LOCKED_INCOMPLETE_STANDARDIZED_COST_SCOPE"
    )
    comparable = annual.loc[annual["perimeter_comparable"]]
    expected_grade = np.where(
        comparable["absolute_raw_margin_gap_pct_points"].le(5.0),
        "GREEN_ABSOLUTE_GAP_LE_5PPT",
        np.where(
            comparable["absolute_raw_margin_gap_pct_points"].le(10.0),
            "YELLOW_ABSOLUTE_GAP_GT_5_LE_10PPT",
            "RED_ABSOLUTE_GAP_GT_10PPT",
        ),
    )
    assert comparable["annual_perimeter_grade"].eq(expected_grade).all()
    assert (~annual["hedge_accounting_adjustment_applied"]).all()


def test_route_aware_reserve_coverage_adds_eqt_without_weakening_kpi_gate() -> None:
    coverage = pd.read_csv(OUTPUT / "reserve_coverage_summary.csv").set_index("ticker")
    panel = pd.read_csv(OUTPUT / "route_aware_reserve_panel.csv")
    assert coverage["route_aware_reserve_chain_ready"].sum() == 4
    assert coverage.loc["EQT", "v13_reserve_quantity_years"] == 2
    assert coverage.loc["EQT", "v15_route_aware_reserve_quantity_years"] == 10
    assert coverage.loc["EQT", "coverage_year_improvement"] == 8
    assert panel["production_calibration_ratio"].between(0.75, 1.25).all()
    assert panel["production_source_tag"].str.len().gt(0).all()
    assert panel["end_reserves_source_tag"].str.len().gt(0).all()
    assert "missing_optional_events_assumed_zero_for_identity" in panel
    eqt_2025 = panel.loc[
        panel["ticker"].eq("EQT") & panel["year"].eq(2025)
    ].iloc[0]
    assert eqt_2025["end_reserves_mboe"] > 4_000_000.0
    assert np.isclose(eqt_2025["production_calibration_ratio"], 1.0, atol=0.01)


def test_all_in_reserve_cost_separates_project_and_company_scope_roic() -> None:
    roic = pd.read_csv(
        OUTPUT / "reserve_roic_scope_cross_check.csv"
    ).set_index("ticker")
    for ticker in ("AR", "CNX", "FANG"):
        row = roic.loc[ticker]
        assert row["observed_all_in_reserve_cost_years"] >= 3
        assert row["observed_all_in_cost_per_gross_added_boe"] > 0
        assert (
            row["company_scope_all_in_reserve_roic_proxy_q50_pct"]
            < row["project_development_roic_proxy_q50_pct"]
        )
        assert row["roic_scope_status"] == (
            "OBSERVED_DEV_EXPLORATION_ACQUISITION_SCOPE_NOT_FULL_COMPANY_INCREMENTAL_ROIC"
        )
        assert bool(row["project_roic_equals_company_incremental_roic"]) is False
        assert bool(row["company_incremental_roic_validated"]) is False
    assert np.isclose(
        roic.loc["CNX", "company_scope_all_in_reserve_roic_proxy_q50_pct"],
        74.843141,
        atol=1e-4,
    )
    assert roic.loc["FANG", "company_scope_all_in_reserve_roic_proxy_q50_pct"] < 50.0


def test_all_in_cost_total_is_reconciled_and_missing_scope_is_disclosed() -> None:
    annual = pd.read_csv(OUTPUT / "annual_all_in_reserve_cost.csv")
    selected = annual.dropna(subset=["selected_all_in_reserve_investment_usd"])
    assert len(selected) > 0
    assert selected["selected_all_in_reserve_investment_usd"].gt(0).all()
    assert selected["reported_total_component_reconciliation_error"].le(0.05).all()
    assert selected["selected_all_in_source_tags"].str.len().gt(0).all()
    assert selected["included_scope"].eq(
        "DEVELOPMENT_EXPLORATION_PROVED_AND_UNPROVED_ACQUISITION"
    ).all()
    assert selected["excluded_or_unproven_scope"].str.contains(
        "INFRASTRUCTURE_CORPORATE_CAPITAL"
    ).all()


def test_production_mix_and_terminal_gates_remain_conservative() -> None:
    mix = pd.read_csv(OUTPUT / "production_mix_coverage.csv").set_index("ticker")
    gate = pd.read_csv(OUTPUT / "v1_5_gate.csv").iloc[0]
    assert bool(mix.loc["AR", "actual_mix_ready"])
    assert bool(mix.loc["CNX", "actual_mix_ready"]) is False
    assert bool(mix.loc["FANG", "actual_mix_ready"]) is False
    assert mix.loc["FANG", "group_prior_allocated_mix_years"] == 4
    assert int(gate["route_aware_reserve_chain_ready_tickers"]) == 4
    assert int(gate["accounting_perimeter_reconciliation_pass_tickers"]) == 0
    assert int(gate["reserve_coverage_target_tickers"]) == 8
    assert bool(gate["reserve_coverage_target_met"]) is False
    assert int(gate["company_incremental_roic_validated_tickers"]) == 0
    assert int(gate["terminal_anchor_ready_tickers"]) == 0
    assert bool(gate["terminal_anchor_replacement_allowed"]) is False
    assert bool(gate["wacc_range_recalibrated"]) is False
    assert int(gate["risk_channel_duplicate_count"]) == 0
    assert bool(gate["production_eligible"]) is False
    assert gate["live_matched_observations"] == "0/20"
