from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v12.benchmark import verify_v12_architecture
from scripts.industrials.valuation_v1_3_lite import main


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output/industrials_valuation_v1_3_lite_research"


@pytest.fixture(scope="module", autouse=True)
def generated() -> None:
    assert main() == 0


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_parent_v12_architecture_stays_byte_verified() -> None:
    verified = verify_v12_architecture(ROOT)
    assert verified["verified_files"] == 45
    assert verified["assertions"]["benchmark_scope"] == "ARCHITECTURE_NOT_FORECAST_PERFORMANCE"


def test_arcana_ir_html_is_hashed_parsed_and_recasts_are_explicit() -> None:
    summary = read("ir_parser_summary").iloc[0]
    assert summary["earnings_release_count"] == 23
    assert summary["parsed_quarters"] == 23
    assert summary["parsed_segments"] == 4
    assert summary["cross_release_cells"] == 152
    assert summary["cross_release_exact_matches"] == 125
    assert summary["cross_release_recast_or_scope_change_cells"] == 27
    assert bool(summary["all_selected_source_hashes_match"])
    assert bool(summary["within_release_comparable_basis_used"])
    assert bool(summary["parser_gate_pass"])


def test_latest_ir_gold_cells_and_comparable_prior_basis() -> None:
    history = read("ir_segment_quarterly_history")
    q2 = history.loc[history["period"].eq("2026Q2")].set_index("segment")
    assert np.isclose(q2.loc["construction", "sales_usd"], 8.346e9)
    assert np.isclose(q2.loc["resource", "sales_usd"], 4.648e9)
    assert np.isclose(q2.loc["power_energy", "sales_usd"], 8.238e9)
    assert np.isclose(q2.loc["mpe", "sales_usd"], 19.581e9)
    assert np.isclose(q2.loc["construction", "segment_profit_usd"], 1.947e9)
    assert np.isclose(q2.loc["power_energy", "comparable_prior_sales_usd"], 7.037e9)


def test_capture_is_segment_specific_shrunk_and_non_pit_fail_closed() -> None:
    summary = read("capture_calibration_summary")
    assert set(summary["segment"]) == {"construction", "resource", "power_energy"}
    assert set(summary["target"]) == {"REVENUE", "COST"}
    assert summary["calibration_observations"].eq(14).all()
    assert summary["validation_observations"].eq(6).all()
    assert summary["shrunk_capture_beta"].nunique() == 6
    assert not np.isclose(summary["shrunk_capture_beta"], 1.0).any()
    assert summary["shrinkage_weight"].between(0.0, 1.0, inclusive="neither").all()
    assert (~summary["historical_pit_vintages_available"].astype(bool)).all()
    assert (~summary["capture_validated"].astype(bool)).all()
    assert (~summary["terminal_input_allowed"].astype(bool)).all()


def test_temporal_diagnostics_include_intervals_and_revenue_level_ape() -> None:
    validation = read("capture_temporal_validation")
    assert len(validation) == 18
    assert (validation["revenue_prediction_lower_pct"] <= validation["predicted_revenue_growth_pct"]).all()
    assert (validation["predicted_revenue_growth_pct"] <= validation["revenue_prediction_upper_pct"]).all()
    assert validation["revenue_level_ape_pct"].ge(0.0).all()
    assert (~validation["performance_claim_allowed"].astype(bool)).all()


def test_margin_and_reinvestment_gates_fail_closed() -> None:
    margin = read("margin_validation_summary")
    reinvestment = read("reinvestment_validation_summary").iloc[0]
    assert margin["validation_observations"].eq(6).all()
    assert margin["minimum_observations_met"].astype(bool).all()
    assert (~margin["margin_model_validated"].astype(bool)).all()
    assert margin["margin_mase_vs_prior_year"].gt(1.0).all()
    assert reinvestment["validation_observations"] == 3
    assert bool(reinvestment["minimum_observations_met"])
    assert not bool(reinvestment["full_forecast_oos_validated"])
    assert not bool(reinvestment["reinvestment_bridge_validated"])


def test_segment_capex_history_is_extracted_but_not_equated_to_reinvestment() -> None:
    history = read("segment_capex_history")
    summary = read("segment_capex_summary").iloc[0]
    context = read("reinvestment_capex_context").iloc[0]
    assert list(history["fiscal_year"]) == [2021, 2022, 2023, 2024, 2025]
    assert np.isclose(summary["latest_total_capex_usd"], 4.286e9)
    assert np.isclose(summary["latest_financial_products_capex_usd"], 1.341e9)
    assert np.isclose(summary["latest_mpe_capex_proxy_usd"], 2.945e9)
    assert context["required_reinvestment_to_latest_mpe_capex_pct"] > 100.0
    assert not bool(summary["net_reinvestment_identity_claim_allowed"])
    assert not bool(context["accounting_identity_claim_allowed"])
    assert not bool(context["reinvestment_bridge_validated"])


def test_capture_bridge_reduces_v12_margin_and_incremental_roic_extremes() -> None:
    bridge = read("capture_calibrated_financial_bridge").iloc[0]
    v12 = pd.read_csv(ROOT / "output/industrials_valuation_v1_2_research/industry_financial_bridge.csv").iloc[0]
    assert np.isclose(bridge["base_revenue_usd"], 63.980e9)
    assert np.isclose(bridge["forecast_revenue_growth_pct"], 25.937356, atol=1e-5)
    assert bridge["forecast_operating_margin_pct"] < v12["forecast_operating_margin_pct"]
    assert bridge["incremental_roic_pct"] < v12["incremental_roic_pct"]
    assert bridge["incremental_roic_pct"] < 100.0
    assert not bool(bridge["forecast_performance_claim_allowed"])
    assert not bool(bridge["terminal_input_allowed"])


def test_cfsc_194m_residual_is_reconciled_at_bridge_not_subcomponent_level() -> None:
    audit = read("financial_products_residual_bridge_audit").iloc[0]
    assert np.isclose(audit["pretax_perimeter_residual_usd"], 243e6)
    assert np.isclose(audit["tax_perimeter_residual_usd"], 50e6)
    assert np.isclose(audit["reported_net_perimeter_residual_usd"], 194e6)
    assert np.isclose(audit["bridge_implied_net_residual_usd"], 193e6)
    assert np.isclose(audit["rounding_and_affiliate_residual_usd"], 1e6)
    assert bool(audit["bridge_level_attribution_identified"])
    assert not bool(audit["economic_subcomponent_attribution_identified"])


def test_cap_surface_preserves_non_identification_and_locks_terminal() -> None:
    summary = read("cap_surface_summary").iloc[0]
    surface = read("cap_surface_margin_roic_duration")
    assert summary["margin_cap_points"] == 24
    assert summary["margin_roic_cap_points"] == 96
    assert summary["market_match_points"] == 3
    assert summary["nearest_absolute_gap_pct"] < 0.25
    assert bool(summary["non_identification_preserved"])
    assert not bool(summary["appropriate_cap_claim_allowed"])
    assert not bool(summary["terminal_input_allowed"])
    assert set(surface["cap_years"]) == {3, 5, 7, 10, 15, 20}


def test_final_gate_keeps_performance_terminal_and_production_locked() -> None:
    gate = read("industrials_v1_3_lite_gate").iloc[0]
    assert bool(gate["parent_v1_2_architecture_verified"])
    assert bool(gate["arcana_ir_html_used"])
    assert bool(gate["pdf_parsing_deferred"])
    assert not bool(gate["historical_industry_pit_vintages_available"])
    assert not bool(gate["capture_forecast_performance_validated"])
    assert not bool(gate["margin_forecast_performance_validated"])
    assert not bool(gate["reinvestment_bridge_validated"])
    assert not bool(gate["backlog_model_changed"])
    assert gate["backlog_oos_observations"] == 2
    assert not bool(gate["terminal_input_allowed"])
    assert not bool(gate["production_promoted"])
    assert str(gate["live_matched_observations"]) == "0/20"
