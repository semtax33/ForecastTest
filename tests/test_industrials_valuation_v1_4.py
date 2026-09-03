from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from equity_platform.artifacts import hash_files
from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v12.benchmark import verify_v12_architecture
from equity_platform.sectors.industrials.v14.data import VINTAGE_COLUMNS
from scripts.industrials.valuation_v1_4 import main


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output/industrials_valuation_v1_4_research"


@pytest.fixture(scope="module", autouse=True)
def generated() -> None:
    assert main() == 0


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_parent_architecture_and_v13_sources_remain_verified() -> None:
    parent = verify_v12_architecture(ROOT)
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert parent["manifest_sha256"] == "e36d9989337417536f798cda6a05e43589c111bc683f3acb4edd930d44f707ef"
    assert metadata["parent_v1_2_verified_after"]
    assert metadata["parent_v1_3_lite_source_hashes_unchanged"]
    assert metadata["arcana_ir_directory"].endswith(r"Arcana\data-lake\bronze\sec\fillings\ir\CAT")
    assert hash_files(ROOT, metadata["source_hashes"].keys()) == metadata["source_hashes"]


def test_ir_price_volume_bridge_is_exact_and_source_hashed() -> None:
    summary = read("ir_segment_pq_summary").iloc[0]
    bridge = read("ir_segment_pq_bridge")
    assert summary["quarter_segment_rows"] == 69
    assert summary["quarters"] == 23
    assert summary["segments"] == 3
    assert summary["bridge_identity_mismatches"] == 0
    assert summary["reported_change_mismatches"] == 0
    assert bool(summary["pq_bridge_gate_pass"])
    assert bridge["source_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert bridge["bridge_identity_error_usd"].abs().max() <= 1.0


def test_segment_cost_and_output_price_sensors_are_dedicated_and_complete() -> None:
    registry = read("segment_sensor_registry")
    coverage = read("segment_sensor_coverage")
    assert set(registry["segment"]) == {"construction", "resource", "power_energy"}
    assert {"material", "component", "freight", "labor", "output_price"}.issubset(set(registry["role"]))
    for (_, role), group in registry.groupby(["segment", "role"]):
        if role == "output_price":
            assert group["weight"].sum() == pytest.approx(1.0)
    for _, group in registry.loc[registry["role"].ne("output_price")].groupby("segment"):
        assert group["weight"].sum() == pytest.approx(1.0)
    assert coverage["latest_period"].eq("2026Q2").all()
    assert coverage["full_quarter_observations"].eq(22).all()


def test_pit_schema_is_ready_but_historical_vintages_fail_closed() -> None:
    canonical = read("pit_vintage_canonical")
    audit = read("pit_vintage_schema_audit").iloc[0]
    assert list(canonical.columns) == VINTAGE_COLUMNS
    assert audit["observation_rows"] == 946
    assert audit["series_count"] == 12
    assert audit["release_date_coverage_pct"] == 0.0
    assert audit["available_at_coverage_pct"] == 100.0
    assert audit["source_hash_coverage_pct"] == 100.0
    assert audit["pit_eligible_rows"] == 0
    assert not bool(audit["historical_pit_ready"])
    assert (~canonical["pit_eligible"].astype(bool)).all()


def test_margin_walk_forward_improves_v13_but_does_not_clear_absolute_gate() -> None:
    summary = read("segment_margin_validation_summary").set_index("segment")
    assert summary["validation_observations"].eq(6).all()
    assert (summary["margin_mae_improvement_vs_v13_pct"] > 0.0).all()
    assert summary.loc["construction", "margin_mase_vs_prior"] == pytest.approx(1.123574, abs=1e-5)
    assert summary.loc["power_energy", "margin_mase_vs_prior"] == pytest.approx(1.308459, abs=1e-5)
    assert summary.loc["resource", "margin_mase_vs_prior"] == pytest.approx(0.648045, abs=1e-5)
    assert int(summary["margin_mase_vs_prior"].lt(1.0).sum()) == 1
    assert (~summary["margin_model_validated"].astype(bool)).all()
    assert (~summary["performance_claim_allowed"].astype(bool)).all()


def test_margin_reliability_shrinkage_uses_only_bounded_prior_weight() -> None:
    validation = read("segment_margin_walk_forward")
    assert validation["margin_shrinkage_weight"].between(0.0, 1.0).all()
    assert (validation["predicted_margin_lower_pct"] <= validation["predicted_margin_pct"]).all()
    assert (validation["predicted_margin_pct"] <= validation["predicted_margin_upper_pct"]).all()
    assert (validation["bridge_predicted_cost_usd"] > 0.0).all()
    assert (~validation["historical_pit_input"].astype(bool)).all()


def test_price_volume_cost_diagnostics_preserve_mixed_evidence() -> None:
    components = read("segment_component_validation_summary").set_index(["segment", "component"])
    summary = read("segment_margin_validation_summary").set_index("segment")
    assert components.loc[("power_energy", "PRICE"), "mae_pct"] < 0.4
    assert components.loc[("construction", "COST"), "mae_pct"] > 10.0
    assert summary.loc["power_energy", "revenue_mae_improvement_vs_unit_pct"] > 0.0
    assert summary.loc["resource", "revenue_mae_improvement_vs_unit_pct"] > 0.0
    assert summary.loc["construction", "revenue_mae_improvement_vs_unit_pct"] < 0.0
    coefficients = read("segment_cost_economics_coefficients")
    slope_columns = ["industry_activity_beta", "output_price_beta", "dedicated_cost_beta"]
    assert (coefficients[slope_columns].fillna(0.0) >= 0.0).all().all()


def test_freeze_gate_is_predeclared_and_fails_only_margin_count() -> None:
    freeze = read("v1_3_lite_freeze_readiness").iloc[0]
    assert freeze["segments_with_margin_mase_below_one"] == 1
    assert freeze["minimum_segments_required"] == 2
    assert freeze["maximum_segment_margin_mase"] < freeze["catastrophic_margin_mase_threshold"]
    assert bool(freeze["no_catastrophic_segment_regression"])
    assert bool(freeze["capture_improved_vs_unit"])
    assert bool(freeze["explicit_calibration_only_disposition"])
    assert not bool(freeze["v1_3_lite_freeze_ready"])
    assert freeze["failed_gates"] == "MARGIN_MASE_SEGMENT_COUNT"
    assert freeze["status"] == "HOLD_RESEARCH_UNFROZEN"


def test_full_chain_reinvestment_propagates_forecast_error_and_fails_closed() -> None:
    validation = read("reinvestment_full_chain_walk_forward")
    summary = read("reinvestment_full_chain_summary").iloc[0]
    assert len(validation) == 1
    assert validation.iloc[0]["fiscal_year"] == 2025
    assert validation.iloc[0]["forecast_quarter_rows"] == 12
    assert validation.iloc[0]["core_revenue_ape_pct"] == pytest.approx(1.509448, abs=1e-5)
    assert summary["full_chain_reinvestment_mase"] < 1.0
    assert bool(summary["upstream_forecast_errors_propagated"])
    assert not bool(summary["minimum_observations_met"])
    assert not bool(summary["perimeter_exact"])
    assert not bool(summary["full_forecast_oos_validated"])
    assert not bool(summary["reinvestment_bridge_validated"])


def test_valuation_roic_terminal_and_production_stay_locked() -> None:
    authority = read("v1_4_valuation_authority").iloc[0]
    gate = read("industrials_v1_4_gate").iloc[0]
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert bool(gate["research_complete"])
    assert not bool(gate["roic_model_changed"])
    assert not bool(gate["valuation_update_allowed"])
    assert not bool(gate["backlog_model_changed"])
    assert gate["backlog_oos_observations"] == 2
    assert bool(gate["pdf_parsing_deferred"])
    assert not bool(gate["terminal_input_allowed"])
    assert not bool(gate["production_promoted"])
    assert str(gate["live_matched_observations"]) == "0/20"
    assert not bool(authority["valuation_update_allowed"])
    assert authority["new_reverse_dcf_result"] == "NOT_RUN_BY_DESIGN"
    assert np.isnan(authority["new_dcf_value_per_share"])
    assert metadata["v1_3_lite_reference_value_per_share"] == pytest.approx(399.117520479533)
