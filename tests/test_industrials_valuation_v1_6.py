from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from equity_platform.artifacts import hash_files
from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v15.benchmark import verify_v15_pit_data
from scripts.industrials.valuation_v1_6 import main


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output/industrials_valuation_v1_6_research"


@pytest.fixture(scope="module", autouse=True)
def generated() -> None:
    assert main() == 0


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_v1_5_pit_data_benchmark_is_verified_before_and_after() -> None:
    manifest = verify_v15_pit_data(ROOT)
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert manifest["manifest_sha256"] == metadata["v1_5_pit_data_manifest_sha256"]
    assert manifest["verified_files"] == 81
    assert metadata["v1_5_pit_data_verified_after"]
    assert not metadata["v1_5_forecast_model_frozen"]
    assert hash_files(ROOT, metadata["source_hashes"].keys()) == metadata["source_hashes"]
    assert hash_files(ROOT, metadata["parent_forecast_input_hashes"].keys()) == metadata["parent_forecast_input_hashes"]


def test_cost_perimeter_identity_separates_recast_from_economic_cost() -> None:
    audit = read("cost_perimeter_audit").iloc[0]
    frame = read("segment_cost_perimeter")
    assert audit["validation_rows"] == 18
    assert audit["identity_mismatches"] == 0
    assert bool(audit["cost_perimeter_identity_proven"])
    assert not bool(audit["reported_cost_used_as_economic_target"])
    assert not bool(audit["unexpected_recast_forecasted"])
    assert frame["cost_perimeter_identity_error_usd"].abs().max() <= 1.0
    assert np.allclose(
        frame["total_reported_cost_delta_usd"],
        frame["recast_scope_delta_usd"] + frame["comparable_economic_cost_delta_usd"],
        atol=1.0,
    )


def test_resource_cost_gap_is_identified_as_scope_plus_economics() -> None:
    summary = read("segment_cost_perimeter_summary").set_index("segment")
    resource = summary.loc["resource"]
    assert resource["material_recast_rows"] == 2
    assert resource["mean_comparable_economic_cost_growth_pct"] == pytest.approx(8.934743, abs=1e-5)
    assert resource["mean_reported_cost_growth_pct"] == pytest.approx(21.381355, abs=1e-5)
    assert resource["reported_minus_comparable_growth_pct"] == pytest.approx(12.446613, abs=1e-5)
    assert bool(resource["comparable_cost_identity_proven"])
    assert not bool(resource["homogeneous_reported_scope"])
    assert bool(summary.loc["construction", "homogeneous_reported_scope"])


def test_p_and_e_recognition_lags_are_compared_but_not_forced() -> None:
    scores = read("cost_route_inner_validation")
    summary = read("cost_timing_validation_summary").set_index("segment")
    p_and_e = scores.loc[scores["segment"].eq("power_energy")]
    lag_routes = p_and_e.loc[p_and_e["route"].str.startswith("PPI_RECOGNITION")]
    assert set(lag_routes["recognition_lag_quarters"].dropna().astype(int)) == {0, 1, 2, 3}
    assert scores.groupby(["segment", "forecast_period"])["selected"].sum().eq(1).all()
    assert summary.loc["power_energy", "champion_cost_route"] == "LAGGED_ACTUAL_COMPARABLE_COST"
    assert summary.loc["power_energy", "champion_route_selection_share_pct"] == 100.0
    assert summary.loc["power_energy", "comparable_cost_mase"] == pytest.approx(1.0)


def test_construction_load_mix_route_is_narrow_and_training_only() -> None:
    scores = read("cost_route_inner_validation")
    validation = read("cost_timing_walk_forward")
    construction_routes = set(scores.loc[scores["segment"].eq("construction"), "route"])
    assert "CONSTRUCTION_LOAD_MIX_LAG_1" in construction_routes
    assert "CONSTRUCTION_LOAD_MIX_LAG_1" not in set(scores.loc[scores["segment"].ne("construction"), "route"])
    assert validation.groupby("segment").size().eq(6).all()
    assert set(validation["training_quarters"]) == {8, 9, 10, 11, 12, 13}
    assert validation["historical_pit_input"].astype(bool).all()
    assert validation["actual_after_forecast"].astype(bool).all()
    assert (~validation["unexpected_recast_forecasted"].astype(bool)).all()


def test_revenue_champions_pass_scaled_metrics_independently() -> None:
    revenue = read("revenue_champion_validation").set_index("segment")
    assert revenue["validation_observations"].eq(6).all()
    assert revenue["revenue_level_mase"].lt(1.0).all()
    assert (revenue["revenue_wape_pct"] < revenue["naive_revenue_wape_pct"]).all()
    assert revenue["revenue_direction_accuracy_pct"].ge(50.0).all()
    assert revenue["no_material_regression"].astype(bool).all()
    assert revenue["target_level_scaled_metric_pass"].astype(bool).all()
    assert revenue["revenue_champion_eligible"].astype(bool).all()
    assert revenue.loc["construction", "revenue_level_mase"] == pytest.approx(0.614143, abs=1e-5)
    assert revenue.loc["power_energy", "revenue_level_mase"] == pytest.approx(0.941192, abs=1e-5)
    assert revenue.loc["resource", "revenue_level_mase"] == pytest.approx(0.891968, abs=1e-5)


def test_no_margin_route_survives_cancellation_and_perimeter_locks() -> None:
    margin = read("margin_route_validation").set_index("segment")
    assert margin["validated_margin_route"].sum() == 0
    assert bool(margin.loc["construction", "component_cancellation_lock"])
    assert bool(margin.loc["resource", "component_cancellation_lock"])
    assert bool(margin.loc["resource", "cost_perimeter_uncertainty_lock"])
    assert bool(margin.loc["power_energy", "cost_perimeter_uncertainty_lock"])
    assert margin.loc["power_energy", "margin_mase_vs_prior"] > 1.5
    assert margin.loc["resource", "margin_mae_change_vs_v1_5_pct"] < 0.0
    assert not bool(margin.loc["resource", "validated_margin_route"])


def test_research_terminal_and_production_gates_are_separate() -> None:
    layers = read("v1_6_gate_layers").set_index("gate")
    research = layers.loc["RESEARCH_FREEZE_ELIGIBLE"]
    terminal = layers.loc["TERMINAL_EVIDENCE_ELIGIBLE"]
    production = layers.loc["PRODUCTION_PROMOTABLE"]
    assert not bool(research["eligible"])
    assert bool(research["independent_of_terminal_and_production"])
    assert "TERMINAL" not in research["failed_conditions"]
    assert "PRODUCTION" not in research["failed_conditions"]
    assert research["failed_conditions"] == "VALIDATED_MARGIN_ROUTE_COUNT|WORST_MARGIN_MASE"
    assert not bool(terminal["eligible"])
    assert not bool(production["eligible"])


def test_pending_evidence_does_not_get_retuned_or_mislabelled() -> None:
    gate = read("industrials_v1_6_gate").iloc[0]
    assert gate["revenue_champion_segments"] == 3
    assert gate["validated_margin_segments"] == 0
    assert not bool(gate["research_freeze_eligible"])
    assert gate["reinvestment_evidence_observations"] == 1
    assert not bool(gate["reinvestment_evidence_gate_pass"])
    assert gate["backlog_oos_observations"] == 2
    assert not bool(gate["backlog_evidence_gate_pass"])
    assert not bool(gate["terminal_evidence_eligible"])
    assert str(gate["live_matched_observations"]) == "0/20"
    assert not bool(gate["production_promotable"])
    assert gate["status"] == "HOLD_RESEARCH_UNFROZEN"


def test_dcf_reverse_dcf_roic_and_terminal_remain_locked() -> None:
    authority = read("v1_6_valuation_authority").iloc[0]
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert not bool(authority["valuation_update_allowed"])
    assert not bool(authority["terminal_evidence_eligible"])
    assert authority["new_reverse_dcf_result"] == "NOT_RUN_BY_DESIGN"
    assert np.isnan(authority["new_dcf_value_per_share"])
    assert not bool(authority["roic_reestimate_allowed"])
    assert not bool(authority["terminal_replacement_allowed"])
    assert authority["reference_value_per_share_usd"] == pytest.approx(399.1175)
    assert metadata["fixed_validation_window"] == "2025Q1-2026Q2"
    assert metadata["pdf_parsing_deferred"]
