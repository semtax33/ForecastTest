from __future__ import annotations

import json

import pandas as pd
import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.aggregate_revenue_v1 import (
    verify_noc_aggregate_revenue_v1,
)
from equity_platform.sectors.industrials.aerospace_defense.lmt_v31.benchmark import (
    verify_lmt_v31_evidence,
)
from equity_platform.sectors.industrials.aerospace_defense.noc.benchmark import (
    verify_noc_v4_evidence,
)


OUTPUT = PROJECT_ROOT / "output/industrials_v5_hii_third_company_research"


def test_hii_was_selected_outcome_blind_before_forecast_evaluation() -> None:
    selected = pd.read_csv(OUTPUT / "ad_third_company_selected.csv").iloc[0]
    metadata = json.loads((OUTPUT / "ad_third_company_selection_metadata.json").read_text(encoding="utf-8"))
    assert selected["ticker"] == "HII"
    assert selected["all_predeclared_criteria_pass"]
    assert selected["selection_outcome_blind"]
    assert not selected["forecast_performance_inspected"]
    assert selected["unambiguous_quarterly_earnings_releases"] == 43
    assert metadata["performance_fields_read"] == []
    assert metadata["assertion"] == "COMPANY_SELECTED_WITHOUT_FORECAST_OR_VALUATION_OUTCOMES"


def test_hii_10k_10q_and_note_sources_are_hashed_and_complete() -> None:
    source = pd.read_csv(OUTPUT / "hii_sec_source_summary.csv").iloc[0]
    manifest = pd.read_csv(OUTPUT / "hii_sec_manifest_summary.csv").iloc[0]
    assert (source["sec_filings"], source["sec_10k_filings"], source["sec_10q_filings"]) == (27, 7, 20)
    assert source["sec_hash_matches"] == 27
    assert source["concept_families_audited"] == 13
    assert source["concept_family_minimum_coverage_pct"] == 100.0
    assert source["source_gate_pass"]
    assert manifest["six_year_criterion_pass"]
    assert not source["pdf_parsing_used"]


def test_hii_ir_parser_preserves_dual_histories_and_exact_2026q2_values() -> None:
    parser = pd.read_csv(OUTPUT / "hii_ir_parser_summary.csv").iloc[0]
    history = pd.read_csv(OUTPUT / "hii_segment_as_reported_pit_history.csv")
    comparable = pd.read_csv(OUTPUT / "hii_segment_currently_recast_comparable_history.csv")
    assert parser["selected_quarterly_ir_releases"] == 27
    assert parser["selected_ir_hash_matches"] == 27
    assert parser["segment_quarter_rows"] == 81
    assert parser["company_quarter_rows"] == 27
    assert parser["company_revenue_reconciliation_max_abs_usd"] == 0.0
    assert parser["as_reported_and_currently_recast_histories_separate"]
    assert history["history_authority"].eq("AS_REPORTED_PIT_HISTORY").all()
    assert comparable["history_authority"].eq("CURRENTLY_RECAST_COMPARABLE_HISTORY").all()
    q2 = history.loc[history["period"].eq("2026Q2")].set_index("segment")
    assert q2.loc["ingalls_shipbuilding", "sales_usd"] == 845_000_000
    assert q2.loc["newport_news_shipbuilding", "sales_usd"] == 1_849_000_000
    assert q2.loc["mission_technologies", "sales_usd"] == 760_000_000
    assert q2.loc["ingalls_shipbuilding", "operating_profit_usd"] == 58_000_000


def test_hii_sec_ir_segment_reconciliation_covers_full_periodic_window() -> None:
    source = pd.read_csv(OUTPUT / "hii_sec_source_summary.csv").iloc[0]
    cross = pd.read_csv(OUTPUT / "hii_sec_ir_segment_reconciliation.csv")
    comparable = cross.loc[cross["sec_value_usd"].notna() & cross["ir_value_usd"].notna()]
    assert source["segment_metric_comparable_cells"] == 156
    assert source["segment_metric_identity_pass_cells"] == 156
    assert source["segment_metric_identity_pass_pct"] == 100.0
    assert comparable["identity_pass"].all()
    assert comparable["difference_usd"].abs().max() == 0.0
    assert set(comparable["comparison_basis"]) == {
        "SEC_DISCRETE_QUARTER_VS_AS_REPORTED_IR_QUARTER",
        "SEC_ANNUAL_VS_SUM_AS_REPORTED_IR_QUARTERS",
    }


def test_hii_contract_program_and_industry_evidence_are_pit_and_fail_closed() -> None:
    parser = pd.read_csv(OUTPUT / "hii_ir_parser_summary.csv").iloc[0]
    contract = pd.read_csv(OUTPUT / "hii_contract_backlog_evidence.csv")
    programs = pd.read_csv(OUTPUT / "hii_program_timing_evidence.csv")
    segment_walk = pd.read_csv(OUTPUT / "hii_segment_walk_forward.csv")
    industry = pd.read_csv(OUTPUT / "hii_industry_data_summary.csv").iloc[0]
    audit = pd.read_csv(OUTPUT / "hii_pit_vintage_selection_audit.csv")
    assert parser["backlog_disclosure_quarters"] == 25
    assert parser["contract_award_disclosure_quarters"] == 24
    assert contract["historical_pit_input"].all()
    assert not contract["segment_backlog_available"].any()
    assert programs["historical_pit_input"].all()
    assert not segment_walk["program_evidence_used_as_point_override"].any()
    assert industry["bls_model_series"] == 3
    assert industry["bls_archive_vintage_rows"] == 810
    assert industry["historical_pit_ready"]
    assert not industry["dedicated_shipbuilding_output_series_available"]
    assert not industry["census_or_bea_revised_data_used_in_oos"]
    assert audit["cutoff_respected"].all()
    assert pd.to_datetime(audit["selected_vintage_date"]).le(pd.to_datetime(audit["forecast_as_of"])).all()


def test_hii_fixed_oos_aggregate_revenue_beats_naive_without_backlog_overclaim() -> None:
    walk = pd.read_csv(OUTPUT / "hii_company_walk_forward.csv")
    metrics = pd.read_csv(OUTPUT / "hii_company_route_metrics.csv").set_index("route")
    authority = pd.read_csv(OUTPUT / "hii_forecast_authority.csv").iloc[0]
    assert len(walk) == 6
    assert (walk["period"].min(), walk["period"].max()) == ("2025Q1", "2026Q2")
    assert walk["actual_after_forecast"].all()
    assert walk["historical_pit_input"].all()
    assert metrics.loc["PIT_INDUSTRY_BRIDGE", "mase"] == pytest.approx(0.6781519925)
    assert metrics.loc["PIT_INDUSTRY_BRIDGE", "mean_ape_pct"] == pytest.approx(6.338076389)
    assert metrics.loc["TOTAL_BACKLOG_BRIDGE", "mase"] == pytest.approx(0.8955159332)
    assert metrics.loc["PRIOR_YEAR_NAIVE", "mase"] == 1.0
    assert authority["aggregate_revenue_point_authority"]
    assert authority["aggregate_revenue_champion_route"] == "PIT_INDUSTRY_BRIDGE"
    assert not authority["backlog_point_authority"]
    assert authority["funded_backlog_incremental_value"] == "NOT_TESTABLE_NO_FUNDED_DISCLOSURE"


def test_hii_segment_and_margin_results_remain_research_not_authority() -> None:
    coverage = pd.read_csv(OUTPUT / "hii_forecast_coverage.csv").iloc[0]
    revenue = pd.read_csv(OUTPUT / "hii_segment_revenue_champions.csv")
    margin = pd.read_csv(OUTPUT / "hii_segment_margin_champions.csv")
    authority = pd.read_csv(OUTPUT / "hii_forecast_authority.csv").iloc[0]
    uncertainty = pd.read_csv(OUTPUT / "hii_uncertainty_gate.csv").iloc[0]
    assert coverage["company_model_oos_rows"] == 6
    assert coverage["segment_model_oos_rows"] == 18
    assert not coverage["missing_rows_imputed"]
    assert not coverage["segment_backlog_imputed"]
    assert revenue["beats_prior_year_naive"].all()
    assert margin["beats_prior_year_naive"].all()
    assert not authority["segment_revenue_attribution_authority"]
    assert not authority["margin_authority"]
    assert not authority["uncertainty_authority"]
    assert uncertainty["company_calibration_observations"] == 6
    assert uncertainty["minimum_required_calibration_observations"] == 10
    assert not uncertainty["company_interval_eligible"]


def test_hii_roic_and_reinvestment_are_complete_historical_diagnostics_only() -> None:
    summary = pd.read_csv(OUTPUT / "hii_reinvestment_roic_summary.csv").iloc[0]
    annual = pd.read_csv(OUTPUT / "hii_annual_reinvestment_roic_bridge.csv")
    alias = pd.read_csv(OUTPUT / "hii_annual_alias_completion_audit.csv")
    assert summary["critical_annual_metric_minimum_coverage_pct"] == 100.0
    assert summary["reported_roic_years"] == 6
    assert summary["alias_completed_annual_cells"] == 18
    assert summary["latest_reported_roic_pct"] == pytest.approx(11.845865615)
    assert summary["latest_through_cycle_roic_median_pct"] == pytest.approx(10.361747755)
    assert summary["latest_core_reinvestment_rate_pct"] == pytest.approx(-3.909581494)
    assert summary["latest_innovation_adjusted_reinvestment_rate_pct"] == pytest.approx(1.172874448)
    assert alias["alias_applied"].sum() == 18
    assert annual["historical_diagnostic_only"].all()
    assert not annual["terminal_input_allowed"].any()
    assert not summary["segment_roic_claim_allowed"]
    assert not summary["terminal_input_allowed"]


def test_three_company_aggregate_pattern_repeats_but_segment_timing_is_mixed() -> None:
    company = pd.read_csv(OUTPUT / "aerospace_defense_three_company_company_level.csv")
    segment = pd.read_csv(OUTPUT / "aerospace_defense_three_company_segment_level.csv")
    result = pd.read_csv(OUTPUT / "aerospace_defense_three_company_hypothesis.csv").iloc[0]
    assert set(company["company"]) == {"LMT", "NOC", "HII"}
    assert company["validation_observations"].eq(6).all()
    assert company["revenue_champion_eligible"].all()
    assert len(segment) == 10
    assert result["all_three_aggregate_revenue_pass"]
    assert result["segments_beating_naive"] == 6
    assert result["segment_timing_mixed_across_three_companies"]
    assert result["platform_hypothesis"] == "THREE_COMPANY_AGGREGATE_REPEATED_SEGMENT_TIMING_MIXED_RESEARCH_HYPOTHESIS"
    assert not result["industry_conclusion_allowed"]
    assert not result["production_authority"]


def test_hii_gate_keeps_dcf_terminal_and_production_locked_and_parents_unchanged() -> None:
    gate = pd.read_csv(OUTPUT / "industrials_v5_hii_gate.csv").iloc[0]
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert gate["evidence_parser_freeze_eligible"]
    assert gate["aggregate_revenue_research_pass"]
    assert not gate["forecast_freeze_eligible"]
    assert not gate["terminal_gate_pass"]
    assert not gate["production_gate_pass"]
    assert not gate["new_dcf_run"]
    assert not gate["new_reverse_dcf_run"]
    assert metadata["parents_unchanged"]
    assert metadata["parent_manifest_sha256"]["lmt_v31"] == verify_lmt_v31_evidence(PROJECT_ROOT)["manifest_sha256"]
    assert metadata["parent_manifest_sha256"]["noc_v4"] == verify_noc_v4_evidence(PROJECT_ROOT)["manifest_sha256"]
    assert metadata["parent_manifest_sha256"]["noc_aggregate_v1"] == verify_noc_aggregate_revenue_v1(PROJECT_ROOT)["manifest_sha256"]
