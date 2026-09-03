from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161
from energy_nowcast.research.ep_v174.benchmark import verify_v174
from scripts.energy.research.ep.v1_7_4_cohort_closure import (
    _v173_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_7_4_research"
PARENT_OUTPUT = ROOT / "output" / "energy_valuation_v1_7_3_research"


def _csv(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_v174_preserves_parent_hashes_and_all_model_locks() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    gate = _csv("v1_7_4_gate").iloc[0]
    assert metadata["v1_6_1_manifest_sha256"] == verify_v161(ROOT)[
        "manifest_sha256"
    ]
    assert metadata["v1_7_3_parent_snapshot_sha256"] == _v173_snapshot()
    assert metadata["frozen_v1_6_1_mutated"] is False
    assert metadata["v1_7_3_parent_mutated"] is False
    assert metadata["normal_roic_claimed"] is False
    assert not bool(gate["terminal_anchor_replacement_allowed"])
    assert not bool(gate["wacc_recalibrated"])
    assert not bool(gate["production_promoted"])
    assert gate["live_matched_observations"] == "0/20"


def test_fang_source_registry_is_hash_checked_and_retrospective() -> None:
    evidence = _csv("fang_transaction_perimeter_evidence")
    assert len(evidence) == 15
    assert evidence["source_check_passed"].all()
    assert evidence["research_evidence_available_by_closure_cutoff"].all()
    assert set(evidence["directness_grade"]) == {"A"}
    assert set(evidence["validation_temporality"]) == {
        "RETROSPECTIVE_TRANSACTION_CLOSURE_NOT_DEAL_DATE_PIT"
    }
    local = evidence.loc[evidence["source_kind"].eq("LOCAL_SEC_IR")]
    assert len(local) == 14
    assert local["source_file_sha256"].str.len().eq(64).all()
    assert evidence["evidence_record_sha256"].str.len().eq(64).all()


def test_fang_divestiture_production_and_nopat_are_disclosure_bounded() -> None:
    row = _csv("fang_divestiture_nopat_range").iloc[0]
    assert np.isclose(row["asset_total_production_low_mboe_per_day"], 6.45)
    assert np.isclose(row["asset_total_production_high_mboe_per_day"], 6.55)
    assert np.isclose(row["missing_production_low_mboe"], 6.45 * 184.0)
    assert np.isclose(row["missing_production_high_mboe"], 6.55 * 184.0)
    assert 0 < row["asset_oil_mix_low"] < row["asset_oil_mix_high"] < 1
    assert row["asset_loe_per_boe_low"] < row["asset_loe_per_boe_high"]
    assert row["after_tax_unit_margin_low"] < row["after_tax_unit_margin_high"]
    assert 0 < row["missing_after_tax_operating_contribution_low_usd"]
    assert (
        row["missing_after_tax_operating_contribution_low_usd"]
        < row["missing_after_tax_operating_contribution_high_usd"]
    )
    assert bool(row["divested_production_proven"])
    assert bool(row["divested_nopat_bounded"])
    assert bool(row["material_transaction_perimeter_resolved"])


def test_fang_acquisition_full_yearization_closes_2019_perimeter() -> None:
    row = _csv("fang_divestiture_nopat_range").iloc[0]
    annualized_production = 26_709.0 * 365.0 / 273.0
    assert np.isclose(row["energen_annualized_production_mboe"], annualized_production)
    assert np.isclose(
        row["energen_2019_retained_production_low_mboe"],
        annualized_production - row["missing_production_high_mboe"],
    )
    assert np.isclose(
        row["energen_2019_retained_production_high_mboe"],
        annualized_production - row["missing_production_low_mboe"],
    )
    assert np.isclose(
        row["energen_incremental_production_low_mboe"],
        row["energen_2019_retained_production_low_mboe"]
        - row["energen_event_year_production_proxy_mboe"],
    )
    assert np.isclose(
        row["energen_event_year_nopat_proxy_usd"],
        row["energen_full_year_triangulated_nopat_usd"] * 33.0 / 365.0,
    )
    assert (
        row["energen_incremental_nopat_low_usd"]
        < row["energen_incremental_nopat_high_usd"]
    )
    assert bool(row["acquisition_full_yearization_bounded"])


def test_dvn_reconciliation_uses_exact_wpx_continuing_scope() -> None:
    row = _csv("dvn_nopat_discrepancy_reconciliation").iloc[0]
    assert np.isclose(row["parent_attributable_net_income_ytd_usd"], -952_000_000)
    assert np.isclose(row["consolidated_net_income_ytd_usd"], -949_000_000)
    assert np.isclose(row["noncontrolling_interest_ytd_usd"], 3_000_000)
    assert np.isclose(
        row["discontinued_operations_net_of_tax_ytd_usd"], -182_000_000
    )
    assert np.isclose(row["continuing_consolidated_net_income_ytd_usd"], -767_000_000)
    assert np.isclose(row["operating_income_ytd_usd"], -811_000_000)
    assert np.isclose(row["interest_expense_ytd_usd"], 145_000_000)
    assert np.isclose(row["tax_rate"], 194.0 / 961.0)
    assert int(row["period_mismatch_days"]) == 0


def test_dvn_scope_adjustment_explains_original_25pct_gap() -> None:
    row = _csv("dvn_nopat_discrepancy_reconciliation").iloc[0]
    assert np.isclose(row["headline_route_gap_pct"], 25.478118, atol=1e-5)
    assert np.isclose(row["scope_adjusted_route_gap_pct"], 0.614628, atol=1e-5)
    assert float(row["predeclared_tolerance_pct"]) == 10.0
    assert bool(row["scope_adjusted_two_route_triangulated"])
    assert abs(row["unexplained_difference_usd"]) < 0.01
    assert abs(row["parent_scope_identity_error_usd"]) < 0.01
    assert abs(row["continuing_income_identity_error_usd"]) < 0.01
    assert abs(row["route_reconciliation_identity_error_usd"]) < 0.01
    assert np.isclose(row["impairment_oil_gas_ytd_usd"], 967_000_000)
    assert np.isclose(row["impairment_gap_adjustment_usd"], 0.0)


def test_dvn_parent_failure_is_preserved_beside_reconciled_validation_route() -> None:
    panel = _csv("scope_adjusted_nopat_triangulation").set_index(
        ["ticker", "fiscal_year"]
    )
    row = panel.loc[("DVN", 2021)]
    assert not bool(row["v1_7_3_two_route_nopat_triangulated"])
    assert bool(row["validation_scope_adjustment_applied"])
    assert bool(row["v1_7_4_scope_adjusted_two_route_triangulated"])
    assert np.isclose(row["validation_route_gap_pct"], 0.614628, atol=1e-5)
    assert panel.loc[("FANG", 2018), "v1_7_4_scope_adjusted_two_route_triangulated"]


def test_closed_cohorts_preserve_parent_columns_and_add_bounded_fang_adjustment() -> None:
    parent = pd.read_csv(PARENT_OUTPUT / "normalization_attribution_cohorts.csv")
    closed = _csv("closed_three_year_cohorts")
    parent_columns = list(parent.columns)
    pd.testing.assert_frame_equal(
        closed[parent_columns].reset_index(drop=True),
        parent.reset_index(drop=True),
        check_dtype=False,
    )
    fang = closed.loc[closed["ticker"].eq("FANG")].sort_values("cohort_offset")
    assert fang["material_transaction_perimeter_resolved"].all()
    t1 = fang.loc[fang["cohort_offset"].eq(1)].iloc[0]
    assert (
        t1["v174_reported_organic_nopat_low_usd"]
        < t1["v174_reported_organic_nopat_high_usd"]
    )
    assert t1["v174_reported_organic_nopat_high_usd"] < t1[
        "reported_organic_nopat_usd"
    ]


def test_two_three_year_cohorts_are_complete_only_on_mature_rows() -> None:
    cohorts = _csv("closed_three_year_cohorts")
    mature = cohorts.loc[cohorts["cohort_offset"].eq(2)]
    immature = cohorts.loc[cohorts["cohort_offset"].lt(2)]
    assert int(mature["v174_reported_3y_cohort_complete"].sum()) == 2
    assert int(mature["v174_independent_full_cycle_3y_cohort_complete"].sum()) == 2
    assert not immature["v174_reported_3y_cohort_complete"].any()
    assert not immature["v174_independent_full_cycle_3y_cohort_complete"].any()
    assert mature["material_transaction_perimeter_resolved"].all()


def test_validated_roic_is_a_company_research_range_not_normal_or_terminal() -> None:
    validation = _csv("organic_roic_validation_ranges").set_index("ticker")
    assert set(validation.index) == {"FANG", "DVN"}
    assert validation["organic_company_roic_validated"].all()
    assert validation["reported_cohort_complete"].all()
    assert validation["independent_full_cycle_cohort_complete"].all()
    assert validation["two_route_nopat_triangulated"].all()
    assert validation["material_transaction_perimeter_resolved"].all()
    assert (
        validation["economically_comparable_roic_low_pct"]
        <= validation["economically_comparable_roic_high_pct"]
    ).all()
    assert np.isclose(
        validation.loc["DVN", "economically_comparable_roic_low_pct"],
        -2.175785,
        atol=1e-5,
    )
    assert np.isclose(
        validation.loc["DVN", "economically_comparable_roic_high_pct"],
        39.301492,
        atol=1e-5,
    )
    assert not validation["normal_roic_claimed"].any()
    assert not validation["terminal_input_allowed"].any()


def test_predeclared_v174_freeze_gate_passes_exactly_without_unlocking_terminal() -> None:
    gate = _csv("v1_7_4_gate").iloc[0]
    assert int(gate["complete_reported_3y_cohort_tickers"]) == 2
    assert int(gate["complete_independent_full_cycle_cohort_tickers"]) == 2
    assert int(gate["triangulated_nopat_validated_cohort_tickers"]) == 2
    assert int(gate["validated_organic_roic_tickers"]) == 2
    assert int(gate["unresolved_material_transaction_perimeters"]) == 0
    assert bool(gate["v1_7_4_research_freeze_eligible"])
    assert gate["development_status"] == "RESEARCH_GATE_PASSED_FREEZE_ELIGIBLE"
    assert bool(gate["terminal_replacement_remains_locked"])
    assert not bool(gate["terminal_anchor_replacement_allowed"])


def test_frozen_v174_manifest_verifies() -> None:
    manifest = verify_v174(ROOT)
    assert manifest["immutable"] is True
    assert manifest["research_frozen"] is True
    assert manifest["validated_organic_roic_tickers"] == 2
    assert manifest["normal_roic_claimed"] is False
    assert manifest["terminal_anchor_replacement_allowed"] is False
    assert manifest["verified_files"] == 18
