from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.lmt_v31.benchmark import (
    verify_lmt_v31_evidence,
)


def test_lmt_v31_evidence_and_rejected_experiment_manifest_is_intact() -> None:
    manifest = verify_lmt_v31_evidence(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"]
    assert manifest["research_frozen"]
    assert assertions["benchmark_scope"] == "LMT_PROGRAM_EVIDENCE_AND_REJECTED_CHALLENGER_RECORD_ONLY"
    assert assertions["research_freeze_eligible"]
    assert not assertions["forecast_research_freeze_eligible"]
    assert assertions["program_narrative_cells"] == 216
    assert assertions["program_narrative_coverage_pct"] == 100.0
    assert assertions["sec_10q_program_identity_cells"] == 70
    assert assertions["backlog_horizon_10k_filings"] == 6
    assert assertions["program_level_backlog_amount_coverage_pct"] == 0.0
    assert assertions["program_level_backlog_fail_closed"]
    assert assertions["challengers_tested"] == 3
    assert assertions["challengers_accepted"] == 0
    assert assertions["rejected_experiment_record_immutable"]
    assert assertions["selected_joint_champions"] == 1
    assert assertions["fixed_validation_window"] == "2025Q1-2026Q2"
    assert not assertions["terminal_input_allowed"]
    assert not assertions["production_promoted"]
    assert not assertions["new_dcf_run"]
    assert not assertions["new_reverse_dcf_run"]
    assert not assertions["pdf_parsing_used"]
