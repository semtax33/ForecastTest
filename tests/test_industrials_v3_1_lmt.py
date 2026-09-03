from __future__ import annotations

import json

import pandas as pd
import pytest

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT


OUTPUT = PROJECT_ROOT / "output/industrials_v3_1_lmt_program_conversion_research"
PARENT = PROJECT_ROOT / "output/industrials_v3_lmt_aerospace_research"


def test_v31_inherits_the_full_sec_ir_note_and_industry_authority() -> None:
    source = pd.read_csv(OUTPUT / "lmt_v31_inherited_source_authority.csv").iloc[0]
    assert source["inherited_source_gate_pass"]
    assert (source["sec_10k_filings"], source["sec_10q_filings"]) == (6, 17)
    assert source["note_families_audited"] == 16
    assert source["ir_earnings_releases"] == 27
    assert source["ir_segment_rows"] == 108
    assert source["sec_ir_segment_identity_cells"] == 184
    assert source["sec_rpo_ir_backlog_identity_periods"] == 23
    assert source["bls_vintage_rows"] == 1080
    assert source["census_context_rows"] == 486
    assert source["bea_context_only"]


def test_v31_program_narratives_and_backlog_horizon_are_complete_but_fail_closed() -> None:
    evidence = pd.read_csv(OUTPUT / "lmt_v31_program_evidence_summary.csv").iloc[0]
    horizon = pd.read_csv(OUTPUT / "lmt_v31_backlog_conversion_horizon.csv")
    assert evidence["evidence_gate_pass"]
    assert evidence["parsed_segment_metric_narratives"] == 216
    assert evidence["segment_metric_narrative_coverage_pct"] == 100.0
    assert evidence["rms_sikorsky_attribution_periods"] == 25
    assert evidence["aero_f35_attribution_periods"] == 26
    assert evidence["space_profit_booking_attribution_periods"] == 23
    assert evidence["annual_backlog_horizon_filings"] == 6
    assert evidence["annual_backlog_horizon_coverage_pct"] == 100.0
    assert evidence["sec_10q_program_amount_cells"] == 70
    assert evidence["sec_10q_program_amount_identity_pass_cells"] == 70
    assert evidence["sec_10q_program_amount_identity_pct"] == 100.0
    assert evidence["program_level_backlog_amount_coverage_pct"] == 0.0
    assert evidence["program_level_backlog_fail_closed"]
    assert horizon["backlog_expected_within_12m_pct"].tolist() == [39.0, 38.0, 37.0, 36.0, 35.0, 37.0]
    assert horizon["backlog_expected_within_24m_pct"].tolist() == [61.0, 60.0, 61.0, 62.0, 60.0, 60.0]
    assert not horizon["program_level_backlog_amount_disclosed"].any()
    assert pd.read_csv(OUTPUT / "lmt_v31_sec_10q_program_crosscheck.csv")[
        "sec_10q_crosscheck_pass"
    ].all()


def test_v31_parser_preserves_exact_recent_program_attributions() -> None:
    history = pd.read_csv(OUTPUT / "lmt_v31_program_attribution_history.csv").set_index(["period", "segment"])
    assert history.loc[("2026Q2", "aeronautics"), "aero_f35_sales_delta_usd"] == 475_000_000
    assert history.loc[("2026Q2", "rotary_mission_systems"), "rms_sikorsky_sales_delta_usd"] == 255_000_000
    assert history.loc[("2026Q1", "rotary_mission_systems"), "rms_sikorsky_sales_delta_usd"] == -110_000_000
    assert history.loc[("2026Q1", "space"), "space_profit_booking_adjustment_delta_usd"] == -125_000_000


def test_v31_program_features_are_historical_pit_and_rms_weights_are_nonnegative() -> None:
    panel = pd.read_csv(OUTPUT / "lmt_v31_feature_panel.csv")
    weights = pd.read_csv(OUTPUT / "lmt_v31_rms_delivery_value_weights.csv")
    assert len(panel) == 56
    assert panel["historical_pit_input"].all()
    assert panel["program_evidence_cutoff_pass"].all()
    assert panel["backlog_horizon_cutoff_pass"].all()
    assert (
        pd.to_datetime(weights["training_max_available_at"])
        <= pd.to_datetime(weights["forecast_as_of"])
    ).all()
    coefficient_columns = [
        column for column in weights if column.endswith("marginal_revenue_usd_per_delivery")
    ]
    assert (weights[coefficient_columns] >= 0.0).all().all()
    assert weights.loc[weights["forecast_period"].eq("2025Q1"), "training_observations"].iloc[0] == 19


def test_v31_predeclared_challengers_are_rejected_without_oos_feature_substitution() -> None:
    challenger = pd.read_csv(OUTPUT / "lmt_v31_challenger_summary.csv").set_index("segment")
    decisions = pd.read_csv(OUTPUT / "lmt_v31_route_decisions.csv").set_index("segment")
    assert challenger.loc["aeronautics", "revenue_mase"] == pytest.approx(1.298279, abs=1e-6)
    assert challenger.loc["rotary_mission_systems", "revenue_mase"] == pytest.approx(1.690106, abs=1e-6)
    assert challenger.loc["space", "margin_mase"] == pytest.approx(1.095821, abs=1e-6)
    assert decisions["revenue_challenger_tested"].sum() == 2
    assert decisions["margin_challenger_tested"].sum() == 1
    assert not decisions["revenue_challenger_accepted"].any()
    assert not decisions["margin_challenger_accepted"].any()
    assert decisions["selection_policy"].eq(
        "CHALLENGER_MUST_BEAT_PARENT_AND_NAIVE_ON_FIXED_OOS"
    ).all()


def test_v31_selected_champions_and_untouched_targets_equal_parent_v3() -> None:
    selected = pd.read_csv(OUTPUT / "lmt_v31_walk_forward.csv").sort_values(["segment", "period"])
    parent = pd.read_csv(PARENT / "lmt_portability_walk_forward.csv").sort_values(["segment", "period"])
    summary = pd.read_csv(OUTPUT / "lmt_v31_summary.csv")
    assert len(selected) == 24
    assert selected.groupby("segment").size().eq(6).all()
    assert selected["period"].min() == "2025Q1"
    assert selected["period"].max() == "2026Q2"
    assert selected["predicted_sales_usd"].to_numpy() == pytest.approx(parent["predicted_sales_usd"].to_numpy())
    assert selected["predicted_operating_margin_pct"].to_numpy() == pytest.approx(
        parent["predicted_operating_margin_pct"].to_numpy()
    )
    assert summary["revenue_champion_eligible"].sum() == 2
    assert summary["margin_champion_eligible"].sum() == 3
    assert summary["joint_champion"].sum() == 1


def test_v31_gate_uncertainty_financial_bridge_and_valuation_remain_locked() -> None:
    gate = pd.read_csv(OUTPUT / "industrials_v3_1_lmt_gate.csv").iloc[0]
    uncertainty = pd.read_csv(OUTPUT / "lmt_uncertainty_gate.csv").iloc[0]
    bridge = pd.read_csv(OUTPUT / "lmt_company_financial_bridge_summary.csv").iloc[0]
    valuation = pd.read_csv(OUTPUT / "industrials_v3_1_lmt_valuation_authority.csv").iloc[0]
    assert gate["program_evidence_gate_pass"]
    assert gate["historical_pit_cutoff_pass"]
    assert gate["fixed_oos_window_pass"]
    assert gate["parent_preservation_pass"]
    assert not gate["research_freeze_eligible"]
    assert gate["status"] == "HOLD_RESEARCH_UNFROZEN"
    assert gate["failed_conditions"] == "PORTABILITY_POINT_PERFORMANCE"
    assert uncertainty["uncertainty_champions"] == 0
    assert bridge["financial_bridge_claim_periods"] == 0
    assert not gate["terminal_gate_pass"]
    assert not gate["production_gate_pass"]
    assert not gate["new_dcf_run"]
    assert not gate["new_reverse_dcf_run"]
    assert valuation["lmt_v31_reverse_dcf_result"] == "NOT_RUN_BY_DESIGN"


def test_v31_metadata_binds_the_exact_parent_inputs() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["parent_status"] == "HOLD_RESEARCH_UNFROZEN"
    assert metadata["parent_metadata_sha256"] == sha256_file(PARENT / "metadata.json")
    for name, expected_hash in metadata["parent_input_hashes"].items():
        assert sha256_file(PARENT / name) == expected_hash
    assert metadata["fixed_validation_window"] == "2025Q1-2026Q2"
    assert not metadata["program_level_backlog_claim_allowed"]
    assert not metadata["terminal_input_allowed"]
    assert not metadata["production_promotable"]
    assert not metadata["pdf_parsing_used"]
