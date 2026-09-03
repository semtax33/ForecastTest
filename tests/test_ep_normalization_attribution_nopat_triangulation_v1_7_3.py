from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161
from scripts.energy.research.ep.v1_7_3_normalization_attribution import (
    _v172_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_7_3_research"


def _csv(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_v173_preserves_frozen_and_parent_snapshots_and_model_locks() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    gate = _csv("v1_7_3_gate").iloc[0]
    assert metadata["v1_6_1_manifest_sha256"] == verify_v161(ROOT)[
        "manifest_sha256"
    ]
    assert metadata["v1_7_2_parent_snapshot_sha256"] == _v172_snapshot()
    assert metadata["frozen_v1_6_1_mutated"] is False
    assert metadata["v1_7_2_parent_mutated"] is False
    assert not bool(gate["terminal_anchor_replacement_allowed"])
    assert not bool(gate["wacc_recalibrated"])
    assert not bool(gate["production_promoted"])
    assert gate["live_matched_observations"] == "0/20"


def test_energen_ppa_and_target_evidence_reconcile_to_source_facts() -> None:
    row = _csv("historical_energen_acquisition_evidence").iloc[0]
    assert row["ticker"] == "FANG"
    assert np.isclose(row["acquiree_revenue_since_close_usd"], 101_700_000.0)
    assert np.isclose(row["post_close_direct_operating_expense_usd"], 17_100_000.0)
    assert np.isclose(row["post_close_direct_operating_contribution_usd"], 84_600_000.0)
    assert row["post_close_direct_operating_contribution_status"] == (
        "NOT_NOPAT_DDA_GA_TAX_SCOPE_MISSING"
    )
    assert np.isclose(row["ppa_assets_usd"], 10_103_671_000.0)
    assert np.isclose(row["ppa_liabilities_usd"], 2_967_634_000.0)
    assert np.isclose(
        row["recognized_net_assets_usd"],
        row["ppa_assets_usd"] - row["ppa_liabilities_usd"],
    )
    assert np.isclose(row["recognized_net_assets_usd"], row["total_consideration_usd"])
    assert np.isclose(
        row["acquired_invested_capital_usd"],
        row["recognized_net_assets_usd"]
        + row["assumed_long_term_debt_usd"]
        - row["cash_acquired_proxy_usd"],
    )
    assert len(row["source_evidence_bundle_sha256"]) == 64
    assert bool(row["classification_phrase_proven"])


def test_energen_same_period_routes_triangulate_below_predeclared_tolerance() -> None:
    row = _csv("historical_energen_acquisition_evidence").iloc[0]
    tax_rate = 50_695_000.0 / (160_617_000.0 + 50_695_000.0)
    route_a = (
        160_617_000.0 + 32_601_000.0 * (1.0 - tax_rate)
    ) * 365.0 / 273.0
    route_b = 243_220_000.0 * (1.0 - tax_rate) * 365.0 / 273.0
    assert np.isclose(row["predeal_normalized_tax_rate"], tax_rate)
    assert np.isclose(row["route_a_net_income_plus_after_tax_interest_usd"], route_a)
    assert np.isclose(row["route_b_operating_income_after_tax_usd"], route_b)
    assert np.isclose(row["route_a_b_symmetric_gap_pct"], 0.2845218862)
    assert float(row["triangulation_tolerance_pct"]) == 10.0
    assert bool(row["two_route_nopat_triangulated"])
    assert row["triangulation_status"] == "EVIDENCE_TRIANGULATED_NOPAT"


def test_nopat_triangulation_passes_only_predeclared_same_period_pairs() -> None:
    panel = _csv("nopat_route_triangulation").set_index(["ticker", "fiscal_year"])
    assert bool(panel.loc[("FANG", 2018), "two_route_nopat_triangulated"])
    assert bool(panel.loc[("COP", 2021), "two_route_nopat_triangulated"])
    assert not bool(panel.loc[("DVN", 2021), "two_route_nopat_triangulated"])
    assert np.isclose(
        panel.loc[("DVN", 2021), "route_a_b_symmetric_gap_pct"],
        25.478118,
        atol=1e-5,
    )
    assert int(panel["two_route_nopat_triangulated"].sum()) == 2
    assert int(panel["evidence_backed_nopat_bridge"].sum()) == 3
    assert int(panel["triangulation_economic_run_rate_positive"].sum()) == 1


def test_acquisition_returns_preserve_parent_bridges_and_keep_energen_semantics_distinct() -> None:
    panel = _csv("nopat_route_triangulation").set_index(["ticker", "fiscal_year"])
    assert np.isclose(
        panel.loc[("COP", 2021), "evidence_backed_acquisition_return_proxy_pct"],
        14.905298,
        atol=1e-5,
    )
    assert np.isclose(
        panel.loc[("DVN", 2021), "evidence_backed_acquisition_return_proxy_pct"],
        18.198379,
        atol=1e-5,
    )
    energen = panel.loc[("FANG", 2018)]
    assert np.isclose(
        energen["evidence_backed_acquisition_return_proxy_pct"],
        3.016281,
        atol=1e-5,
    )
    assert energen["evidence_backed_nopat_bridge_semantics"] == (
        "PREDEAL_TARGET_SAME_PERIOD_TWO_ROUTE_RUN_RATE_NOT_POST_CLOSE_CONTRIBUTION"
    )


def test_independent_cost_source_cells_and_attribution_identities_all_pass() -> None:
    evidence = _csv("independent_cost_annual_evidence")
    annual = _csv("normalization_attribution_annual")
    assert int(evidence["source_cell_checks"].sum()) == 48
    assert int(evidence["source_cell_checks_passed"].sum()) == 48
    assert evidence["source_cells_fully_verified"].all()
    assert evidence["independent_complete_cost_scope"].all()
    assert set(evidence["normalization_confidence_grade"]) == {"A"}
    assert annual["normalization_attribution_annual_complete"].all()
    assert annual["normalization_attribution_identity_error_usd"].abs().max() < 0.01


def test_annual_price_and_cost_normalization_are_economically_separable() -> None:
    annual = _csv("normalization_attribution_annual").set_index(["ticker", "year"])
    row = annual.loc[("DVN", 2022)]
    volume = row["production_mboe"] * 1_000.0
    price_effect = (
        row["normalized_price_per_boe"] - row["actual_price_per_boe"]
    ) * volume * (1.0 - row["actual_tax_rate"])
    cost_effect = (
        row["actual_unit_cost_per_boe"] - row["normalized_unit_cost_per_boe"]
    ) * volume * (1.0 - row["actual_tax_rate"])
    assert np.isclose(row["price_normalization_effect_usd"], price_effect)
    assert np.isclose(row["cost_normalization_effect_usd"], cost_effect)
    assert price_effect < 0
    assert cost_effect < 0


def test_confidence_policy_prevents_hierarchical_rows_from_outvoting_independent_data() -> None:
    policy = _csv("normalization_confidence_policy").set_index(
        "normalization_confidence_grade"
    )
    tickers = _csv("normalization_confidence_by_ticker").set_index("ticker")
    assert float(policy.loc["A", "sector_inference_weight"]) == 1.0
    assert float(policy.loc["B", "sector_inference_weight"]) == 0.5
    assert float(policy.loc["C", "sector_inference_weight"]) == 0.0
    assert tickers.loc["DVN", "normalization_confidence_grade"] == "A"
    assert tickers.loc["FANG", "normalization_confidence_grade"] == "A"
    assert tickers.loc["EOG", "normalization_confidence_grade"] == "C"
    assert float(tickers.loc["EOG", "sector_inference_weight"]) == 0.0


def test_dvn_attribution_identifies_price_as_primary_normalization_driver() -> None:
    cohorts = _csv("normalization_attribution_cohorts")
    mature = cohorts.loc[
        cohorts["ticker"].eq("DVN") & cohorts["cohort_offset"].eq(2)
    ].iloc[0]
    assert np.isclose(
        mature["reported_cumulative_organic_roic_pct"], 139.394105, atol=1e-5
    )
    assert np.isclose(
        mature["reported_economic_cumulative_organic_roic_pct"],
        39.301492,
        atol=1e-5,
    )
    assert np.isclose(
        mature["price_only_normalized_cumulative_organic_roic_pct"],
        -15.511348,
        atol=1e-5,
    )
    assert np.isclose(
        mature["cost_only_normalized_cumulative_organic_roic_pct"],
        49.102024,
        atol=1e-5,
    )
    assert np.isclose(
        mature["full_cycle_normalized_cumulative_organic_roic_pct"],
        -2.175785,
        atol=1e-5,
    )
    assert bool(mature["reported_cohort_complete"])
    assert bool(mature["full_cycle_normalized_cohort_complete"])


def test_fang_methodology_coverage_expands_without_false_organic_validation() -> None:
    cohorts = _csv("normalization_attribution_cohorts")
    t1 = cohorts.loc[
        cohorts["ticker"].eq("FANG") & cohorts["cohort_offset"].eq(1)
    ].iloc[0]
    mature = cohorts.loc[
        cohorts["ticker"].eq("FANG") & cohorts["cohort_offset"].eq(2)
    ].iloc[0]
    assert np.isclose(t1["organic_invested_capital_proxy_usd"], 2_036_916_000.0)
    assert t1["perimeter_status"] == (
        "DIVESTITURE_BOOK_CAPITAL_PROVEN_OPERATING_CONTRIBUTION_MISSING"
    )
    assert bool(mature["methodology_attribution_complete"])
    assert bool(mature["independent_cost_normalized_cohort_complete"])
    assert not bool(mature["reported_cohort_complete"])
    assert not bool(mature["full_cycle_normalized_cohort_complete"])
    assert np.isnan(mature["full_cycle_normalized_cumulative_organic_roic_pct"])


def test_validation_stays_fail_closed_for_all_events() -> None:
    validation = _csv("organic_roic_validation")
    assert int(validation["organic_company_roic_validated"].sum()) == 0
    dvn = validation.loc[
        validation["ticker"].eq("DVN") & validation["fiscal_year"].eq(2021)
    ].iloc[0]
    assert dvn["validation_status"] == "LOCKED__NOPAT_TWO_ROUTE_NOT_TRIANGULATED"
    fang = validation.loc[
        validation["ticker"].eq("FANG") & validation["fiscal_year"].eq(2018)
    ].iloc[0]
    assert "REPORTED_ORGANIC_3Y_COHORT_INCOMPLETE" in fang["validation_status"]


def test_v173_gate_meets_coverage_targets_without_false_freeze() -> None:
    gate = _csv("v1_7_3_gate").iloc[0]
    assert int(gate["evidence_backed_nopat_bridge_deals"]) == 3
    assert int(gate["two_route_nopat_triangulated_deals"]) == 2
    assert int(gate["normalization_attribution_tickers"]) == 2
    assert int(gate["independent_cost_normalized_cohort_tickers"]) == 2
    assert int(gate["complete_3y_reported_cohort_tickers"]) == 1
    assert int(gate["complete_3y_cycle_normalized_cohort_tickers"]) == 1
    assert int(gate["validated_organic_roic_tickers"]) == 0
    assert bool(gate["v1_7_3_research_gate"])
    assert not bool(gate["v1_7_3_research_freeze_eligible"])
    assert gate["development_status"] == "RESEARCH_GATE_PASSED_FREEZE_DEFERRED"
