from __future__ import annotations

import json

import pandas as pd
import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v2.benchmark import verify_cmi_v2


OUTPUT = PROJECT_ROOT / "output/industrials_v3_lmt_aerospace_research"


def test_lmt_sources_ir_segments_backlog_and_deliveries_are_complete() -> None:
    source = pd.read_csv(OUTPUT / "lmt_source_audit_summary.csv").iloc[0]
    parser = pd.read_csv(OUTPUT / "lmt_ir_parser_summary.csv").iloc[0]
    assert source["source_gate_pass"]
    assert (source["sec_filings"], source["sec_10k_filings"], source["sec_10q_filings"]) == (23, 6, 17)
    assert source["ir_earnings_releases"] == 27
    assert source["note_families_audited"] == 16
    assert source["event_conditional_note_families"] == 2
    assert source["coverage_denominators_are_applicability_aware"]
    assert source["note_family_minimum_coverage_pct"] == 100.0
    assert parser["parser_gate_pass"]
    assert parser["segment_quarter_rows"] == 108
    assert parser["backlog_segment_quarter_rows"] == 108
    assert parser["backlog_coverage_pct"] == 100.0
    assert parser["delivery_period_coverage_pct"] == 100.0
    assert parser["segment_sales_coverage_pct"] == 100.0
    assert parser["segment_operating_profit_coverage_pct"] == 100.0
    assert parser["pdf_parsing_used"] == False  # noqa: E712


def test_lmt_sec_segment_and_backlog_values_reconcile_to_ir() -> None:
    summary = pd.read_csv(OUTPUT / "lmt_sec_ir_segment_reconciliation_summary.csv").iloc[0]
    cross = pd.read_csv(OUTPUT / "lmt_sec_ir_segment_reconciliation.csv")
    backlog = pd.read_csv(OUTPUT / "lmt_sec_rpo_ir_backlog_reconciliation.csv")
    gate = pd.read_csv(OUTPUT / "industrials_v3_lmt_gate.csv").iloc[0]
    assert summary["segment_and_backlog_reconciliation_gate_pass"]
    assert summary["selected_segment_metric_cells"] == 184
    assert summary["sec_ir_segment_identity_pass_cells"] == 184
    assert summary["maximum_segment_absolute_difference_usd"] == 0.0
    assert cross["identity_pass"].all()
    assert summary["rpo_backlog_identity_pass_periods"] == 23
    assert summary["rpo_backlog_maximum_absolute_difference_pct"] <= 0.05
    assert backlog["rounding_identity_pass"].all()
    assert gate["sec_ir_segment_reconciliation_pass"]


def test_lmt_program_loss_normalization_never_allocates_an_undisclosed_residual() -> None:
    cross = pd.read_csv(OUTPUT / "lmt_sec_ir_program_loss_reconciliation.csv").set_index("period")
    summary = pd.read_csv(OUTPUT / "lmt_sec_ir_segment_reconciliation_summary.csv").iloc[0]
    assert set(cross.index) == {"2024Q4", "2025Q2"}
    assert cross.loc["2024Q4", "unallocated_sec_program_losses_usd"] == 245_000_000
    assert cross.loc["2025Q2", "unallocated_sec_program_losses_usd"] == 0
    assert cross["no_overallocation_pass"].all()
    assert summary["program_loss_unallocated_residual_usd"] == 245_000_000
    assert summary["program_loss_no_overallocation_gate_pass"]


def test_lmt_parser_preserves_exact_2025q2_values_and_program_losses() -> None:
    history = pd.read_csv(OUTPUT / "lmt_segment_quarterly_history.csv")
    backlog = pd.read_csv(OUTPUT / "lmt_backlog_history.csv")
    deliveries = pd.read_csv(OUTPUT / "lmt_aircraft_delivery_history.csv")
    losses = pd.read_csv(OUTPUT / "lmt_program_loss_registry.csv")
    aero = history.loc[(history["period"] == "2025Q2") & (history["segment"] == "aeronautics")].iloc[0]
    rms = history.loc[(history["period"] == "2025Q2") & (history["segment"] == "rotary_mission_systems")].iloc[0]
    assert aero["sales_usd"] == 7_420_000_000
    assert aero["operating_profit_usd"] == -98_000_000
    assert rms["sales_usd"] == 3_995_000_000
    assert rms["operating_profit_usd"] == -172_000_000
    assert backlog.loc[(backlog["period"] == "2025Q2") & (backlog["segment"] == "aeronautics"), "backlog_usd"].iloc[0] == 52_165_000_000
    assert deliveries.loc[(deliveries["period"] == "2025Q2") & (deliveries["delivery_program"] == "F-35"), "quarter_deliveries"].iloc[0] == 50
    assert deliveries.loc[(deliveries["period"] == "2025Q2") & (deliveries["delivery_program"] == "F-35"), "prior_year_quarter_deliveries"].iloc[0] == 0
    expected = {
        ("2024Q4", "aeronautics"): 410_000_000,
        ("2024Q4", "missiles_fire_control"): 1_310_000_000,
        ("2025Q2", "aeronautics"): 950_000_000,
    }
    totals = losses.groupby(["period", "segment"])["pretax_program_loss_usd"].sum().to_dict()
    for key, value in expected.items():
        assert totals[key] == value
    assert totals[("2025Q2", "rotary_mission_systems")] == 665_000_000


def test_lmt_fixed_oos_is_pit_and_target_authorities_are_separate() -> None:
    walk = pd.read_csv(OUTPUT / "lmt_portability_walk_forward.csv")
    summary = pd.read_csv(OUTPUT / "lmt_portability_summary.csv")
    assert len(walk) == 24
    assert walk.groupby("segment").size().eq(6).all()
    assert walk["period"].min() == "2025Q1"
    assert walk["period"].max() == "2026Q2"
    assert walk["historical_pit_input"].all()
    assert walk["actual_after_forecast"].all()
    assert walk["revenue_and_margin_champions_separate"].all()
    assert walk["revenue_performance_claim_allowed"].all()
    assert (~walk["margin_performance_claim_allowed"]).sum() == 2
    assert walk.loc[~walk["margin_performance_claim_allowed"], "period"].eq("2025Q2").all()
    assert summary["structural_anchor_coverage_pct"].eq(100.0).all()
    assert summary["validation_observations"].eq(6).all()


def test_lmt_point_results_hold_research_without_hiding_successes() -> None:
    summary = pd.read_csv(OUTPUT / "lmt_portability_summary.csv")
    gate = pd.read_csv(OUTPUT / "industrials_v3_lmt_gate.csv").iloc[0]
    mfc = summary.loc[summary["segment"] == "missiles_fire_control"].iloc[0]
    assert summary["revenue_champion_eligible"].sum() == 2
    assert summary["margin_champion_eligible"].sum() == 3
    assert summary["joint_champion"].sum() == 1
    assert mfc["revenue_mase"] == pytest.approx(0.313234, abs=1e-5)
    assert mfc["margin_mase"] == pytest.approx(0.042353, abs=1e-5)
    assert gate["fixed_oos_window_pass"]
    assert gate["margin_boundary_saturation_pass"]
    assert not gate["research_freeze_eligible"]
    assert gate["status"] == "HOLD_RESEARCH_UNFROZEN"
    assert gate["failed_conditions"] == "PORTABILITY_POINT_PERFORMANCE"


def test_lmt_sec_notes_reinvestment_and_roic_coverage_are_explicit() -> None:
    notes = pd.read_csv(OUTPUT / "lmt_reinvestment_roic_summary.csv").iloc[0]
    annual = pd.read_csv(OUTPUT / "lmt_annual_reinvestment_roic_bridge.csv")
    quarterly = pd.read_csv(OUTPUT / "lmt_quarterly_reinvestment_note_bridge.csv")
    assert notes["research_evidence_ready"]
    assert notes["critical_annual_metric_minimum_coverage_pct"] == 100.0
    assert notes["quarterly_statement_chain_complete_rows"] == 22
    assert notes["quarterly_note_contract_chain_complete_rows"] == 23
    assert notes["reported_roic_years"] == 5
    assert notes["latest_reported_roic_pct"] == pytest.approx(27.053072, abs=1e-5)
    assert notes["latest_pension_adjusted_roic_pct"] == pytest.approx(22.930185, abs=1e-5)
    assert annual["terminal_input_allowed"].eq(False).all()  # noqa: E712
    assert quarterly["terminal_input_allowed"].eq(False).all()  # noqa: E712


def test_lmt_xbrl_coverage_uses_applicability_and_auditable_zero_rules() -> None:
    coverage = pd.read_csv(OUTPUT / "lmt_periodic_note_fact_coverage.csv").set_index("metric")
    selections = pd.read_csv(OUTPUT / "lmt_periodic_note_fact_selections.csv")
    families = pd.read_csv(OUTPUT / "lmt_sec_concept_family_summary.csv")
    assert coverage.loc["depreciation_amortization_usd", "filings_available"] == 23
    assert coverage.loc["research_development_usd", "applicable_filings"] == 6
    assert coverage.loc["research_development_usd", "coverage_pct"] == 100.0
    assert coverage.loc["fas_cas_pension_adjustment_usd", "applicable_filings"] == 12
    assert coverage.loc["fas_cas_pension_adjustment_usd", "coverage_pct"] == 100.0
    derived_debt = selections.loc[
        selections["metric"].eq("debt_current_usd") & selections["derived_value"]
    ]
    assert set(derived_debt["period"]) == {"2022Q2", "2022Q3", "2026Q2"}
    assert derived_debt["value_usd"].eq(0.0).all()
    assert derived_debt["selection_rule"].eq(
        "ZERO_WHEN_CURRENT_DEBT_NOT_REPORTED_AND_NONCURRENT_DEBT_IS_REPORTED"
    ).all()
    annual_only = families.loc[
        families["family"].isin(["note_rd", "note_leases", "note_property_plant_equipment"])
    ]
    assert annual_only["coverage_denominator_policy"].eq("ANNUAL_10K_ONLY").all()
    assert annual_only.loc[annual_only["form"].eq("10-K"), "coverage_pct"].eq(100.0).all()


def test_lmt_industry_data_uses_bls_vintages_but_not_revised_context() -> None:
    industry = pd.read_csv(OUTPUT / "lmt_industry_data_summary.csv").iloc[0]
    authority = pd.read_csv(OUTPUT / "lmt_industry_sensor_authority.csv")
    census = pd.read_csv(OUTPUT / "lmt_census_m3_aerospace_context.csv")
    assert industry["bls_model_series"] == 4
    assert industry["bls_archive_vintage_rows"] == 1080
    assert industry["bls_historical_pit_ready"]
    assert industry["historical_pit_ready"]
    assert industry["census_aerospace_defense_context_rows"] == 486
    assert not industry["revised_census_used_in_oos_claim"]
    assert authority.loc[authority["source"] == "BLS", "model_input_allowed"].all()
    assert not authority.loc[authority["source"].isin(["Census", "BEA"]), "model_input_allowed"].any()
    assert not census["historical_pit_eligible"].any()


def test_lmt_uncertainty_terminal_production_and_dcf_stay_locked() -> None:
    uncertainty = pd.read_csv(OUTPUT / "lmt_uncertainty_gate.csv").iloc[0]
    gate = pd.read_csv(OUTPUT / "industrials_v3_lmt_gate.csv").iloc[0]
    valuation = pd.read_csv(OUTPUT / "industrials_v3_lmt_valuation_authority.csv").iloc[0]
    bridge = pd.read_csv(OUTPUT / "lmt_company_financial_bridge_summary.csv").iloc[0]
    assert uncertainty["uncertainty_champions"] == 0
    assert uncertainty["insufficient_calibration_targets"] == 8
    assert bridge["forecast_periods"] == 6
    assert bridge["financial_bridge_claim_periods"] == 0
    assert not gate["terminal_gate_pass"]
    assert not gate["production_gate_pass"]
    assert not gate["new_dcf_run"]
    assert not gate["new_reverse_dcf_run"]
    assert valuation["lmt_reverse_dcf_result"] == "NOT_RUN_BY_DESIGN"


def test_lmt_branch_preserves_frozen_cmi_parent() -> None:
    manifest = verify_cmi_v2(PROJECT_ROOT)
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["cmi_v2_parent_unchanged"]
    assert metadata["cmi_v2_parent_manifest_sha256"] == manifest["manifest_sha256"]
