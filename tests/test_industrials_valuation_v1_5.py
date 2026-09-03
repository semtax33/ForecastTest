from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from equity_platform.artifacts import hash_files
from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v12.benchmark import verify_v12_architecture
from equity_platform.sectors.industrials.v15.pit import VINTAGE_COLUMNS
from scripts.industrials.valuation_v1_5 import main


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output/industrials_valuation_v1_5_research"


@pytest.fixture(scope="module", autouse=True)
def generated() -> None:
    assert main() == 0


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(OUTPUT / f"{name}.csv")


def test_frozen_parents_remain_verified_and_v14_sources_unchanged() -> None:
    architecture = verify_v12_architecture(ROOT)
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert architecture["manifest_sha256"] == "e36d9989337417536f798cda6a05e43589c111bc683f3acb4edd930d44f707ef"
    assert metadata["parent_v1_2_verified_after"]
    assert metadata["parent_v1_4_source_hashes_unchanged"]
    assert metadata["arcana_ir_directory"].endswith(r"Arcana\data-lake\bronze\sec\fillings\ir\CAT")
    assert hash_files(ROOT, metadata["source_hashes"].keys()) == metadata["source_hashes"]


def test_official_bls_archive_is_hash_verified_without_pdf_parsing() -> None:
    audit = read("bls_ppi_vintage_audit").iloc[0]
    reports = read("bls_ppi_archive_sources")
    schedules = read("bls_release_schedule_sources")
    assert audit["archive_report_files"] == 54
    assert audit["release_schedule_files"] == 5
    assert audit["archive_report_hash_mismatches"] == 0
    assert audit["release_schedule_hash_mismatches"] == 0
    assert audit["required_series"] == audit["parsed_series"] == 13
    assert audit["vintage_rows"] == 3509
    assert bool(audit["historical_pit_ready"])
    assert reports["hash_match"].astype(bool).all()
    assert schedules["hash_match"].astype(bool).all()
    assert (~reports["pdf_parsing_used"].astype(bool)).all()
    assert (~schedules["pdf_parsing_used"].astype(bool)).all()
    assert reports["source_path"].str.endswith(".xlsx").all()


def test_vintage_canonical_has_real_release_revision_and_hash_fields() -> None:
    canonical = read("bls_ppi_vintage_canonical")
    coverage = read("bls_ppi_vintage_coverage")
    assert list(canonical.columns) == VINTAGE_COLUMNS
    assert canonical["release_date"].notna().all()
    assert canonical["available_at"].notna().all()
    assert canonical["source_hash"].str.fullmatch(r"[0-9a-f]{64}").all()
    assert canonical["vintage_value"].notna().all()
    assert set(canonical["vintage_status"]).issubset(
        {"INITIAL_RELEASE", "SUBSEQUENT_PUBLICATION", "LEFT_CENSORED_KNOWN_AS_OF_RELEASE"}
    )
    assert coverage["changed_republications"].sum() > 1000
    assert canonical["pit_eligible"].astype(bool).all()


def test_feature_selection_respects_every_historical_cutoff() -> None:
    features = read("pit_segment_features")
    selection = read("pit_vintage_selection_audit")
    summary = read("pit_feature_summary").iloc[0]
    assert summary["forecast_periods"] == 14
    assert summary["feature_rows"] == 42
    assert summary["minimum_series_coverage_pct"] == 100.0
    assert summary["cutoff_violations"] == 0
    assert bool(summary["historical_pit_ready"])
    assert features["historical_pit_eligible"].astype(bool).all()
    assert selection["cutoff_respected"].astype(bool).all()
    assert (pd.to_datetime(selection["latest_selected_release_date"]) <= pd.to_datetime(selection["forecast_as_of"])).all()


def test_cat_retail_html_parser_preserves_equal_adjacent_quarters_and_rename() -> None:
    audit = read("cat_retail_parser_audit").iloc[0]
    sources = read("cat_retail_ir_sources")
    validation = read("segment_route_walk_forward")
    assert audit["source_files"] == 22
    assert audit["source_hash_mismatches"] == 0
    assert audit["segments"] == 3
    assert audit["quarters"] == 25
    assert audit["vintage_rows"] == 946
    assert bool(audit["retail_pit_ready"])
    assert sources["hash_match"].astype(bool).all()
    assert validation["retail_lag_quarters"].eq(1).all()
    assert validation["retail_reference_period"].eq(
        validation["period"].map(lambda value: str(pd.Period(value, freq="Q") - 1))
    ).all()


def test_outer_walk_forward_is_true_pit_and_never_uses_target_release() -> None:
    validation = read("segment_route_walk_forward")
    origins = read("forecast_origins")
    assert len(validation) == 18
    assert set(validation["training_quarters"]) == {8, 9, 10, 11, 12, 13}
    assert validation.groupby("segment")["training_quarters"].apply(list).map(
        lambda values: values == [8, 9, 10, 11, 12, 13]
    ).all()
    assert validation["historical_pit_input"].astype(bool).all()
    assert validation["actual_after_forecast"].astype(bool).all()
    assert validation["performance_claim_allowed"].astype(bool).all()
    assert (pd.to_datetime(validation["forecast_as_of"]) < pd.to_datetime(validation["actual_available_at"])).all()
    assert origins["actual_after_forecast"].astype(bool).all()


def test_segment_routes_are_selected_independently_using_inner_validation() -> None:
    scores = read("segment_route_inner_validation")
    validation = read("segment_route_walk_forward")
    assert scores.groupby(["segment", "forecast_period"])["selected"].sum().eq(1).all()
    assert scores["inner_validation_observations"].eq(3).all()
    assert "REGIONAL_DEALER_TRANSMISSION" in set(scores.loc[scores["segment"].eq("construction"), "route"])
    assert "REGIONAL_DEALER_TRANSMISSION" not in set(scores.loc[scores["segment"].ne("construction"), "route"])
    assert validation.groupby("segment")["selected_volume_route"].nunique().gt(1).all()


def test_margin_result_is_not_promoted_when_component_errors_cancel() -> None:
    summary = read("segment_route_validation_summary").set_index("segment")
    assert summary.loc["construction", "margin_mase_vs_prior"] == pytest.approx(0.635094, abs=1e-5)
    assert summary.loc["power_energy", "margin_mase_vs_prior"] == pytest.approx(1.331958, abs=1e-5)
    assert summary.loc["resource", "margin_mase_vs_prior"] == pytest.approx(0.947794, abs=1e-5)
    assert int(summary["margin_mase_vs_prior"].lt(1.0).sum()) == 2
    assert bool(summary.loc["construction", "component_cancellation_lock"])
    assert bool(summary.loc["resource", "component_cancellation_lock"])
    assert not bool(summary.loc["power_energy", "component_cancellation_lock"])
    assert summary.loc["construction", "mean_component_cancellation_ratio"] > 0.8
    assert summary.loc["resource", "gross_component_mae_pct"] > 30.0


def test_feedback_experiments_report_mixed_evidence_instead_of_hiding_regressions() -> None:
    components = read("segment_component_pit_validation_summary").set_index(["segment", "component"])
    summary = read("segment_route_validation_summary").set_index("segment")
    assert components.loc[("construction", "VOLUME"), "mae_change_vs_v1_4_pct"] < 0.0
    assert components.loc[("power_energy", "COST"), "mae_change_vs_v1_4_pct"] > 0.0
    assert components.loc[("resource", "VOLUME"), "mae_change_vs_v1_4_pct"] > 0.0
    assert summary["revenue_no_material_regression"].astype(bool).all()
    assert summary["performance_claim_allowed"].astype(bool).all()


def test_strengthened_freeze_gate_stays_unfrozen() -> None:
    freeze = read("v1_5_freeze_readiness").iloc[0]
    assert bool(freeze["historical_pit_archive_ready"])
    assert bool(freeze["historical_pit_features_ready"])
    assert bool(freeze["historical_pit_validation_ready"])
    assert freeze["segments_with_margin_mase_below_one"] == 2
    assert freeze["maximum_segment_margin_mase"] < freeze["worst_segment_margin_mase_threshold"]
    assert bool(freeze["all_segments_revenue_no_material_regression"])
    assert not bool(freeze["component_cancellation_gate_pass"])
    assert not bool(freeze["reinvestment_pit_oos_gate_pass"])
    assert not bool(freeze["freeze_ready"])
    assert freeze["status"] == "HOLD_RESEARCH_UNFROZEN"


def test_reinvestment_valuation_terminal_and_production_fail_closed() -> None:
    reinvestment = read("reinvestment_pit_full_chain_summary").iloc[0]
    authority = read("v1_5_valuation_authority").iloc[0]
    gate = read("industrials_v1_5_gate").iloc[0]
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert reinvestment["validation_observations"] == 1
    assert reinvestment["full_chain_reinvestment_mase"] == pytest.approx(0.422898, abs=1e-5)
    assert not bool(reinvestment["minimum_observations_met"])
    assert not bool(reinvestment["reinvestment_bridge_validated"])
    assert bool(gate["research_complete"])
    assert gate["backlog_oos_observations"] == 2
    assert not bool(gate["valuation_update_allowed"])
    assert not bool(gate["terminal_input_allowed"])
    assert not bool(gate["production_promoted"])
    assert str(gate["live_matched_observations"]) == "0/20"
    assert authority["new_reverse_dcf_result"] == "NOT_RUN_BY_DESIGN"
    assert np.isnan(authority["new_dcf_value_per_share"])
    assert authority["reference_value_per_share_usd"] == pytest.approx(399.1175)
    assert metadata["branch_status"] == "HOLD_RESEARCH_UNFROZEN"
    assert not metadata["valuation_update_allowed"]


def test_no_model_source_or_acquired_artifact_uses_pdf() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    source_names = list(metadata["source_hashes"])
    acquired = read("bls_ppi_archive_sources")["source_path"].tolist()
    assert metadata["pdf_parsing_deferred"]
    assert not any(str(path).lower().endswith(".pdf") for path in source_names + acquired)
