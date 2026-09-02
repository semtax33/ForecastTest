from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_3_research"


def test_v1_3_frozen_research_manifest_verifies() -> None:
    manifest = verify_v13(ROOT)
    assert manifest["research_frozen"] is True
    assert manifest["unit_economics_cross_check_frozen"] is True
    assert manifest["independent_wacc_range_frozen"] is True
    assert manifest["risk_channel_policy_frozen"] is True
    assert manifest["terminal_anchor_ready"] == 0
    assert manifest["production_promoted"] is False
    assert manifest["live_matched_observations"] == "0/20"
    assert manifest["verified_files"] == 23


def test_v1_3_is_research_only_and_preserves_all_frozen_parents() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["v1_manifest_sha256"] == verify_v1(ROOT)["manifest_sha256"]
    assert metadata["v1_1_manifest_sha256"] == verify_v11(ROOT)["manifest_sha256"]
    assert metadata["v1_2_manifest_sha256"] == verify_v12(ROOT)["manifest_sha256"]
    assert metadata["frozen_parent_mutated"] is False
    assert metadata["single_appropriate_wacc_claim_allowed"] is False
    assert metadata["market_price_calibration_used"] is False
    assert metadata["production_promoted"] is False
    assert metadata["live_matched_observations"] == "0/20"


def test_data_coverage_fails_closed_without_inventing_reserve_inputs() -> None:
    coverage = pd.read_csv(OUTPUT / "data_coverage.csv")
    assert len(coverage) == coverage["ticker"].nunique() == 14
    assert coverage["production_mix_status"].eq("PRICE_VOLUME_PROXY_READY").sum() == 13
    assert coverage["reserve_chain_status"].eq(
        "STANDARDIZED_RESERVE_CHAIN_KPI_SCALE_VERIFIED"
    ).sum() == 3
    assert coverage["unit_economics_status"].eq(
        "CORE_STANDARDIZED_RESERVE_REPLACEMENT_CROSS_CHECK"
    ).sum() == 3
    assert coverage["strict_realized_gas_price_quarters"].gt(0).sum() == 4


def test_quantity_units_are_kpi_calibrated_and_auditable() -> None:
    panel = pd.read_csv(OUTPUT / "reserve_quantity_panel.csv")
    assert panel["ticker"].nunique() == 4
    assert panel["production_calibration_ratio"].between(0.75, 1.25).all()
    assert panel["quantity_scale_status"].eq("KPI_CALIBRATED_WITHIN_25PCT").all()
    assert panel["quantity_factor_to_mboe"].gt(0).all()
    assert panel["quantity_source_tags"].str.len().gt(0).all()
    assert panel["quantity_scale_power10"].ne(0).any()
    prior = panel.dropna(subset=["begin_reserves_mboe"])
    assert prior["year"].sub(prior["begin_reserves_source_year"]).eq(1).all()


def test_price_normalization_excludes_recent_regime_and_is_monotonic() -> None:
    reference = pd.read_csv(OUTPUT / "normalized_price_reference.csv").set_index(
        "reference"
    )
    assert set(reference.index) == {"Q25", "Q50", "Q75"}
    assert reference["history_start_quarter"].eq("2015Q1").all()
    assert reference["history_end_quarter"].eq("2024Q4").all()
    assert (~reference["hormuz_long_run_anchor"]).all()
    for column in ("wti_usd_per_bbl", "henry_usd_per_mcf", "propane_usd_per_bbl"):
        assert reference.loc["Q25", column] <= reference.loc["Q50", column]
        assert reference.loc["Q50", column] <= reference.loc["Q75", column]


def test_full_unit_economics_are_finite_and_partial_rows_remain_empty() -> None:
    cross = pd.read_csv(OUTPUT / "unit_economics_cross_check.csv")
    full = cross.loc[cross["unit_economics_status"].eq(
        "CORE_STANDARDIZED_RESERVE_REPLACEMENT_CROSS_CHECK"
    )]
    partial = cross.loc[cross["unit_economics_status"].ne(
        "CORE_STANDARDIZED_RESERVE_REPLACEMENT_CROSS_CHECK"
    )]
    assert len(full) == 3
    columns = [
        "reserve_life_median_years", "normalized_lifting_cost_per_boe",
        "normalized_dda_per_boe", "normalized_development_cost_per_added_boe",
        "commodity_normalized_accounting_margin_q50_pct",
        "reserve_replacement_cash_margin_q50_pct",
        "reserve_replacement_roic_proxy_q50_pct",
    ]
    assert np.isfinite(full[columns].to_numpy(dtype=float)).all()
    assert partial["commodity_normalized_accounting_margin_q50_pct"].isna().all()
    assert (~cross["production_eligible"]).all()
    assert cross["realized_basis_status"].eq(
        "DEFERRED_NO_COMMON_CROSS_COMMODITY_BASIS"
    ).all()
    assert cross["terminal_anchor_status"].eq(
        "LOCKED_INCOMPLETE_TRANSPORT_TAX_AND_REALIZED_BASIS"
    ).all()
    assert full["margin_cross_check_status"].eq(
        "DIRECTIONALLY_CONSISTENT_WITH_V12_WITHIN_10PPT"
    ).sum() == 2
    assert full["roic_cross_check_status"].eq(
        "PLAUSIBILITY_REVIEW_REQUIRED_ABOVE_100PCT"
    ).sum() == 2


def test_wacc_research_is_an_independent_range_not_a_price_fit() -> None:
    beta = pd.read_csv(OUTPUT / "beta_term_structure.csv")
    ranges = pd.read_csv(OUTPUT / "wacc_reference_range.csv")
    summary = pd.read_csv(OUTPUT / "wacc_reference_summary.csv").iloc[0]
    available = ranges.loc[
        ranges["wacc_reference_status"].eq("INDEPENDENT_RANGE_AVAILABLE")
    ]
    assert len(beta) == len(ranges) == 14
    assert len(available) == 13
    assert (~beta["market_price_fit_used"]).all()
    assert (~beta["expectations_surface_used"]).all()
    assert (~ranges["market_price_fit_used"]).all()
    assert (~ranges["expectations_surface_used"]).all()
    assert available["return_based_wacc_low_pct"].le(
        available["return_based_wacc_high_pct"]
    ).all()
    assert bool(summary["single_appropriate_wacc_claim_allowed"]) is False
    comparison = pd.read_csv(OUTPUT / "wacc_cross_comparison.csv").iloc[0]
    assert comparison[
        "v1_3_independent_symmetric_return_wacc_median_pct"
    ] > comparison["v1_1_base_wacc_median_pct"]
    assert comparison[
        "v1_3_symmetric_minus_v1_2_conditional_pct_points"
    ] > 0


def test_risk_channels_pass_new_gate_and_flag_frozen_coupling() -> None:
    policy = pd.read_csv(OUTPUT / "risk_allocation_policy.csv")
    audit = pd.read_csv(OUTPUT / "v11_scenario_risk_coupling_audit.csv")
    gate = pd.read_csv(OUTPUT / "double_count_gate.csv").iloc[0]
    assert policy.groupby("risk")["allocated_channel"].nunique().le(1).all()
    assert int(gate["proposed_policy_duplicate_risk_channels"]) == 0
    assert bool(gate["proposed_v1_3_double_count_gate"]) is True
    assert bool(gate["hormuz_wacc_premium_applied"]) is False
    assert int(gate["inherited_v1_1_coupled_nonbase_rows"]) == 28
    coupled = audit.loc[audit["coupled_channels"]]
    assert len(coupled) == 28
    assert coupled["v1_1_mutation_allowed"].eq(False).all()
