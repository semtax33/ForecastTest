from __future__ import annotations

import json

import pandas as pd
import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.lmt_v31.benchmark import (
    verify_lmt_v31_evidence,
)


OUTPUT = PROJECT_ROOT / "output/industrials_v4_noc_cross_company_research"


def test_noc_sources_and_ir_parser_have_complete_hashed_coverage() -> None:
    source = pd.read_csv(OUTPUT / "noc_source_audit_summary.csv").iloc[0]
    parser = pd.read_csv(OUTPUT / "noc_ir_parser_summary.csv").iloc[0]
    assert source["source_gate_pass"]
    assert (source["sec_filings"], source["sec_10k_filings"], source["sec_10q_filings"]) == (23, 6, 17)
    assert source["sec_hash_matches"] == 23
    assert source["ir_earnings_releases"] == 26
    assert source["ir_hash_matches"] == 26
    assert source["concept_families_audited"] == 13
    assert source["concept_family_minimum_coverage_pct"] == 100.0
    assert parser["parser_gate_pass"]
    assert parser["segment_quarter_rows"] == 104
    assert parser["backlog_segment_quarter_rows"] == 104
    assert parser["segment_sales_coverage_pct"] == 100.0
    assert parser["segment_operating_profit_coverage_pct"] == 100.0
    assert parser["total_backlog_coverage_pct"] == 100.0
    assert parser["funded_backlog_coverage_pct"] == 100.0
    assert parser["material_scope_change_rows"] == 18
    assert parser["pdf_parsing_used"] == False  # noqa: E712


def test_noc_parser_preserves_exact_2026q2_segment_and_backlog_values() -> None:
    history = pd.read_csv(OUTPUT / "noc_segment_quarterly_history.csv")
    backlog = pd.read_csv(OUTPUT / "noc_backlog_history.csv")
    aero = history.loc[(history["period"] == "2026Q2") & (history["segment"] == "aeronautics_systems")].iloc[0]
    defense = history.loc[(history["period"] == "2026Q2") & (history["segment"] == "defense_systems")].iloc[0]
    assert aero["sales_usd"] == 3_519_000_000
    assert aero["operating_profit_usd"] == 362_000_000
    assert defense["sales_usd"] == 2_093_000_000
    row = backlog.loc[(backlog["period"] == "2026Q2") & (backlog["segment"] == "defense_systems")].iloc[0]
    assert row["funded_backlog_usd"] == 9_392_000_000
    assert row["unfunded_backlog_usd"] == 25_286_000_000
    assert row["backlog_usd"] == 34_678_000_000
    assert row["funded_share_pct"] == pytest.approx(27.083453, abs=1e-5)


def test_noc_sec_ir_reconciliation_is_scope_and_precision_aware() -> None:
    summary = pd.read_csv(OUTPUT / "noc_sec_ir_segment_reconciliation_summary.csv").iloc[0]
    cross = pd.read_csv(OUTPUT / "noc_sec_ir_segment_reconciliation.csv")
    backlog = pd.read_csv(OUTPUT / "noc_sec_rpo_ir_backlog_reconciliation.csv")
    assert summary["expected_segment_metric_cells"] == 184
    assert summary["selected_segment_metric_cells"] == 184
    assert summary["scope_comparable_cells"] == 166
    assert summary["scope_recast_excluded_cells"] == 18
    assert summary["sec_ir_segment_identity_pass_cells"] == 166
    assert summary["maximum_applicable_segment_absolute_difference_usd"] == 0.0
    assert summary["segment_and_backlog_reconciliation_gate_pass"]
    assert cross.loc[cross["scope_comparable"], "identity_pass"].all()
    assert len(backlog) == 23
    assert backlog["rounding_identity_pass"].all()
    assert summary["rpo_backlog_maximum_absolute_difference_pct"] <= 0.07


def test_noc_industry_features_are_historical_pit_only() -> None:
    industry = pd.read_csv(OUTPUT / "noc_industry_data_summary.csv").iloc[0]
    authority = pd.read_csv(OUTPUT / "noc_industry_sensor_authority.csv")
    audit = pd.read_csv(OUTPUT / "noc_pit_vintage_selection_audit.csv")
    assert industry["bls_model_series"] == 4
    assert industry["bls_archive_vintage_rows"] == 1080
    assert industry["historical_pit_ready"]
    assert not industry["revised_census_used_in_oos_claim"]
    assert authority.loc[authority["source"].eq("BLS"), "model_input_allowed"].all()
    assert not authority.loc[authority["source"].isin(["Census", "BEA"]), "model_input_allowed"].any()
    assert audit["historical_pit_eligible"].all()
    assert pd.to_datetime(audit["selected_vintage_date"]).le(pd.to_datetime(audit["forecast_as_of"])).all()


def test_noc_company_oos_is_complete_and_funded_backlog_gain_is_small() -> None:
    walk = pd.read_csv(OUTPUT / "noc_company_walk_forward.csv")
    summary = pd.read_csv(OUTPUT / "noc_company_portability_summary.csv").iloc[0]
    assert len(walk) == 6
    assert (walk["period"].min(), walk["period"].max()) == ("2025Q1", "2026Q2")
    assert walk["historical_pit_input"].all()
    assert walk["actual_after_forecast"].all()
    assert summary["funded_backlog_revenue_mase"] == pytest.approx(0.937448, abs=1e-5)
    assert summary["total_backlog_revenue_mase"] == pytest.approx(0.951653, abs=1e-5)
    assert summary["funded_vs_total_mase_improvement_pct"] == pytest.approx(1.492706, abs=1e-5)
    assert summary["funded_backlog_revenue_champion_eligible"]
    assert summary["program_adjustment_periods"] == 5
    assert summary["margin_claim_observations"] == 1
    assert not summary["margin_champion_eligible"]


def test_noc_segment_model_fails_closed_across_realignments() -> None:
    coverage = pd.read_csv(OUTPUT / "noc_segment_model_coverage.csv").set_index("segment")
    summary = pd.read_csv(OUTPUT / "noc_portability_summary.csv").set_index("segment")
    assert coverage["expected_validation_rows"].eq(6).all()
    assert coverage["model_validation_rows"].sum() == 10
    assert coverage.loc["defense_systems", "model_validation_rows"] == 0
    assert coverage.loc["mission_systems", "model_validation_rows"] == 6
    assert not coverage["missing_rows_imputed"].any()
    assert summary.loc["mission_systems", "funded_backlog_revenue_mase"] == pytest.approx(0.615109, abs=1e-5)
    assert summary.loc["space_systems", "funded_backlog_revenue_mase"] > 1.0
    assert summary.loc["aeronautics_systems", "revenue_claim_observations"] == 2
    assert not summary.loc["aeronautics_systems", "funded_backlog_revenue_champion_eligible"]


def test_noc_reinvestment_roic_is_complete_but_not_terminal_authority() -> None:
    summary = pd.read_csv(OUTPUT / "noc_reinvestment_roic_summary.csv").iloc[0]
    annual = pd.read_csv(OUTPUT / "noc_annual_reinvestment_roic_bridge.csv")
    assert summary["research_evidence_ready"]
    assert summary["critical_annual_metric_minimum_coverage_pct"] == 100.0
    assert summary["reported_roic_years"] == 5
    assert summary["latest_reported_roic_pct"] == pytest.approx(13.492247, abs=1e-5)
    assert summary["latest_core_reinvestment_rate_pct"] == pytest.approx(107.028412, abs=1e-5)
    assert summary["latest_innovation_adjusted_reinvestment_rate_pct"] == pytest.approx(136.579429, abs=1e-5)
    assert annual["terminal_input_allowed"].eq(False).all()  # noqa: E712
    assert not summary["segment_roic_claim_allowed"]
    assert not summary["terminal_input_allowed"]


def test_noc_authorities_remain_separate_and_lmt_parent_is_unchanged() -> None:
    gate = pd.read_csv(OUTPUT / "industrials_v4_noc_gate.csv").iloc[0]
    authority = pd.read_csv(OUTPUT / "industrials_v4_noc_authority.csv").iloc[0]
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    manifest = verify_lmt_v31_evidence(PROJECT_ROOT)
    assert gate["evidence_parser_freeze_eligible"]
    assert gate["fixed_oos_window_pass"]
    assert not gate["segment_model_full_coverage_pass"]
    assert not gate["forecast_freeze_eligible"]
    assert gate["status"] == "EVIDENCE_FREEZE_ELIGIBLE_FORECAST_UNFROZEN"
    assert authority["research_evidence_authority"]
    assert not authority["forecast_authority"]
    assert not authority["terminal_input_allowed"]
    assert not authority["production_promotable"]
    assert authority["dcf_result"] == "NOT_RUN_BY_DESIGN"
    assert authority["reverse_dcf_result"] == "NOT_RUN_BY_DESIGN"
    assert metadata["lmt_v31_evidence_parent_unchanged"]
    assert metadata["lmt_v31_evidence_manifest_sha256"] == manifest["manifest_sha256"]


def test_cross_company_result_does_not_overclaim_industry_conclusion() -> None:
    company = pd.read_csv(OUTPUT / "aerospace_defense_cross_company_company_level.csv")
    segment = pd.read_csv(OUTPUT / "aerospace_defense_cross_company_summary.csv")
    assert company["validation_observations"].eq(6).all()
    assert company["revenue_champion_eligible"].all()
    assert company["cross_company_timing_classification"].eq(
        "AGGREGATE_REVENUE_CHAMPION_BOTH_SEGMENT_TIMING_UNRESOLVED"
    ).all()
    assert not company["two_company_sample_is_industry_conclusion"].any()
    assert segment["cross_company_timing_classification"].eq(
        "MIXED_NOT_IDENTIFIED_WITH_TWO_COMPANIES"
    ).all()
    assert not segment["two_company_sample_is_industry_conclusion"].any()
