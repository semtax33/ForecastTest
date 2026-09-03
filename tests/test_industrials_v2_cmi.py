from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v17.benchmark import verify_margin_v1_7


OUTPUT = PROJECT_ROOT / "output/industrials_v2_cmi_portability_research"


def test_cmi_v2_sources_and_ir_parser_have_full_declared_coverage() -> None:
    source = pd.read_csv(OUTPUT / "cmi_source_audit_summary.csv").iloc[0]
    parser = pd.read_csv(OUTPUT / "cmi_ir_parser_summary.csv").iloc[0]
    assert source["source_gate_pass"]
    assert source["sec_filings"] == 23
    assert source["sec_10k_filings"] == 6
    assert source["sec_10q_filings"] == 17
    assert source["ir_earnings_releases"] == 27
    assert parser["parser_gate_pass"]
    assert parser["parsed_quarters"] == 27
    assert parser["parsed_segments"] == 5
    assert parser["segment_sales_coverage_pct"] == 100.0
    assert parser["segment_ebitda_coverage_pct"] == 100.0


def test_cmi_v2_walk_forward_is_pit_and_keeps_target_authorities_separate() -> None:
    walk = pd.read_csv(OUTPUT / "cmi_portability_walk_forward.csv")
    summary = pd.read_csv(OUTPUT / "cmi_portability_summary.csv")
    assert len(walk) == 30
    assert walk.groupby("segment").size().eq(6).all()
    assert walk["historical_pit_input"].all()
    assert walk["actual_after_forecast"].all()
    assert walk["revenue_and_margin_champions_separate"].all()
    assert summary["revenue_mase"].notna().all()
    assert summary["margin_mase"].notna().all()
    components = walk.loc[(walk["segment"] == "components") & (walk["period"] == "2025Q1")].iloc[0]
    assert components["unforecastable_scope_change"]
    assert not components["performance_claim_allowed"]


def test_cmi_v2_industry_data_and_note_evidence_fail_closed() -> None:
    industry = pd.read_csv(OUTPUT / "cmi_industry_data_summary.csv").iloc[0]
    notes = pd.read_csv(OUTPUT / "cmi_reinvestment_roic_summary.csv").iloc[0]
    authority = pd.read_csv(OUTPUT / "cmi_target_route_authority.csv")
    assert industry["historical_pit_ready"]
    assert industry["cutoff_violations"] == 0
    assert not industry["revised_census_used_in_oos_claim"]
    assert notes["research_evidence_ready"]
    assert notes["reported_roic_years"] >= 5
    assert not notes["segment_roic_claim_allowed"]
    assert not authority["reinvestment_forecast_claim_allowed"].any()
    assert not authority["roic_forecast_claim_allowed"].any()
    assert not authority["terminal_input_allowed"].any()


def test_cmi_v2_point_uncertainty_terminal_and_production_gates_are_independent() -> None:
    uncertainty = pd.read_csv(OUTPUT / "portability_uncertainty_gate.csv").iloc[0]
    gate = pd.read_csv(OUTPUT / "industrials_v2_gate.csv").iloc[0]
    valuation = pd.read_csv(OUTPUT / "industrials_v2_valuation_authority.csv").iloc[0]
    assert uncertainty["point_champion_equals_uncertainty_champion_policy"] == False  # noqa: E712
    assert uncertainty["uncertainty_champions"] == 0
    assert not gate["terminal_gate_pass"]
    assert not gate["production_gate_pass"]
    assert not gate["new_dcf_run"]
    assert not gate["new_reverse_dcf_run"]
    assert valuation["cmi_reverse_dcf_result"] == "NOT_RUN_BY_DESIGN"


def test_cmi_v2_does_not_modify_cat_v1_7_parent() -> None:
    manifest = verify_margin_v1_7(PROJECT_ROOT)
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["cat_v1_7_parent_unchanged"]
    assert metadata["cat_v1_7_parent_manifest_sha256"] == manifest["manifest_sha256"]
