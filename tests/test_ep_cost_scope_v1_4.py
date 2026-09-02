from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.research.ep_v14.benchmark import verify_v14
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1_4_research"


def test_v1_4_frozen_research_manifest_verifies() -> None:
    manifest = verify_v14(ROOT)
    assert manifest["research_frozen"] is True
    assert manifest["cost_scope_framework_frozen"] is True
    assert manifest["realized_basis_diagnostic_frozen"] is True
    assert manifest["hedge_non_netting_policy_frozen"] is True
    assert manifest["standardized_complete_cost_scope_tickers"] == 1
    assert manifest["terminal_anchor_ready"] == 0
    assert manifest["production_promoted"] is False
    assert manifest["live_matched_observations"] == "0/20"
    assert manifest["verified_files"] == 15


def test_v1_4_is_research_only_and_preserves_every_frozen_parent() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["v1_manifest_sha256"] == verify_v1(ROOT)["manifest_sha256"]
    assert metadata["v1_1_manifest_sha256"] == verify_v11(ROOT)["manifest_sha256"]
    assert metadata["v1_2_manifest_sha256"] == verify_v12(ROOT)["manifest_sha256"]
    assert metadata["v1_3_manifest_sha256"] == verify_v13(ROOT)["manifest_sha256"]
    assert metadata["frozen_parent_mutated"] is False
    assert metadata["v1_1_mutation_allowed"] is False
    assert metadata["wacc_range_recalibrated"] is False
    assert metadata["single_appropriate_wacc_claim_allowed"] is False


def test_standardized_cost_scope_coverage_is_auditable_and_fails_closed() -> None:
    coverage = pd.read_csv(OUTPUT / "cost_scope_coverage.csv").set_index("ticker")
    assert len(coverage) == 14
    assert coverage["standardized_complete_cost_scope"].sum() == 1
    assert bool(coverage.loc["CNX", "standardized_complete_cost_scope"])
    assert coverage.loc["CNX", "transport_cost_per_boe_years_5y"] == 5
    assert coverage.loc["CNX", "production_tax_per_boe_years_5y"] == 5
    assert coverage.loc["CNX", "g_and_a_per_boe_years_5y"] == 5
    assert coverage.loc["CNX", "exact_realized_basis_years_5y"] == 5
    assert coverage.loc["AR", "transport_cost_per_boe_years_5y"] == 0
    assert coverage.loc["FANG", "transport_cost_per_boe_years_5y"] == 0

    panel = pd.read_csv(OUTPUT / "annual_cost_scope_panel.csv")
    source_columns = [column for column in panel if column.endswith("_source_tag")]
    scope_columns = [column for column in panel if column.endswith("_scope")]
    assert source_columns and scope_columns
    assert panel[source_columns].notna().any().all()
    assert panel[scope_columns].notna().any().all()


def test_realized_basis_has_explicit_semantics_and_no_fake_locked_values() -> None:
    basis = pd.read_csv(OUTPUT / "annual_realized_basis_panel.csv")
    assert basis["basis_semantics"].eq(
        "UPSTREAM_REVENUE_PER_BOE_MINUS_BENCHMARK_MIX_NOT_PURE_PRICE_DIFFERENTIAL"
    ).all()
    exact = basis["upstream_revenue_scope"].eq("UPSTREAM_EXACT")
    assert basis.loc[exact, "realized_revenue_basis_per_boe"].notna().all()
    assert basis.loc[~exact, "realized_revenue_basis_per_boe"].isna().all()
    recent = basis.loc[basis["year"].between(2021, 2025)]
    medians = recent.groupby("ticker")["realized_revenue_basis_per_boe"].median()
    assert np.isclose(medians["AR"], -1.334091, atol=1e-4)
    assert np.isclose(medians["CNX"], -4.732342, atol=1e-4)
    assert np.isclose(medians["FANG"], -6.638326, atol=1e-4)


def test_cnx_complete_cost_scope_reduces_extreme_roic_and_margin_gap() -> None:
    cross = pd.read_csv(OUTPUT / "expanded_core_cross_check.csv").set_index("ticker")
    cnx = cross.loc["CNX"]
    assert cnx["v14_cost_scope_status"] == (
        "COMPLETE_STANDARDIZED_COST_SCOPE_CROSS_CHECK"
    )
    assert cnx["v13_core_roic_proxy_q50_pct"] > 300.0
    assert cnx["v14_known_cost_roic_proxy_q50_pct"] < 100.0
    assert cnx["roic_proxy_reduction_vs_v13_pct_points"] > 250.0
    assert abs(cnx["v14_margin_gap_vs_v13_historical_q50_pct_points"]) < 5.0
    assert cnx["absolute_margin_gap_improvement_vs_v13_core_pct_points"] > 40.0
    assert cnx["basis_hedge_correlation"] > 0.99
    assert cnx["hedge_inclusion_diagnostic"] == (
        "STRONG_EXACT_HEDGE_ASSOCIATION_REVENUE_INCLUSION_NOT_PROVEN"
    )
    assert bool(cnx["hedge_adjusted_basis_applied"]) is False
    assert cnx["basis_dispersion_status"] == (
        "HIGH_DISPERSION_GT_25PCT_OF_ADJUSTED_PRICE"
    )


def test_incomplete_core_rows_remain_upper_bounds_and_hedging_is_separate() -> None:
    cross = pd.read_csv(OUTPUT / "expanded_core_cross_check.csv").set_index("ticker")
    ar = cross.loc["AR"]
    fang = cross.loc["FANG"]
    assert ar["v14_cost_scope_status"] == (
        "UPPER_BOUND_MISSING_TRANSPORT_AND_PRODUCTION_TAX"
    )
    assert fang["v14_cost_scope_status"] == "UPPER_BOUND_MISSING_TRANSPORT"
    assert ar["margin_semantics"] == (
        "KNOWN_COST_UPPER_BOUND_MISSING_COMPONENTS_NOT_ZERO_FILLED"
    )
    assert fang["margin_semantics"] == (
        "KNOWN_COST_UPPER_BOUND_MISSING_COMPONENTS_NOT_ZERO_FILLED"
    )
    assert ar["roic_cross_check_status"] == (
        "UPPER_BOUND_BELOW_100PCT_STILL_INCOMPLETE"
    )
    core = cross.loc[["AR", "CNX", "FANG"]]
    assert core["normalized_hedge_gain_loss_per_boe"].eq(0.0).all()
    assert core["hedge_normalization_status"].eq(
        "QUANTIFIED_SEPARATELY_ZERO_LONG_RUN_NOT_NETTED_WITHOUT_REVENUE_INCLUSION_PROOF"
    ).all()


def test_terminal_and_production_gates_remain_locked() -> None:
    gate = pd.read_csv(OUTPUT / "cost_scope_gate.csv").iloc[0]
    cross = pd.read_csv(OUTPUT / "expanded_core_cross_check.csv")
    assert int(gate["terminal_anchor_ready_tickers"]) == 0
    assert bool(gate["terminal_anchor_replacement_allowed"]) is False
    assert bool(gate["v1_1_mutation_allowed"]) is False
    assert bool(gate["wacc_range_recalibrated"]) is False
    assert int(gate["risk_channel_duplicate_count"]) == 0
    assert int(gate["v14_complete_core_roic_below_100pct_tickers"]) == 1
    assert int(gate["high_basis_dispersion_core_tickers"]) == 1
    assert bool(gate["production_eligible"]) is False
    assert gate["live_matched_observations"] == "0/20"
    assert (~cross["terminal_anchor_ready"]).all()
    assert (~cross["production_eligible"]).all()
