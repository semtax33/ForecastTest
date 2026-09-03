from __future__ import annotations

import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.noc.benchmark import (
    verify_noc_v4_evidence,
)


def test_noc_v4_evidence_and_cross_company_experiment_manifest_is_intact() -> None:
    manifest = verify_noc_v4_evidence(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"]
    assert manifest["research_frozen"]
    assert assertions["benchmark_scope"] == "NOC_EVIDENCE_PARSER_AND_CROSS_COMPANY_EXPERIMENT_RECORD_ONLY"
    assert assertions["source_gate_pass"]
    assert assertions["parser_gate_pass"]
    assert assertions["sec_filings"] == 23
    assert assertions["ir_earnings_releases"] == 26
    assert assertions["segment_quarter_rows"] == 104
    assert assertions["funded_backlog_coverage_pct"] == 100.0
    assert assertions["scope_recast_excluded_cells"] == 18
    assert assertions["scope_comparable_identity_pass_cells"] == 166
    assert assertions["company_oos_observations"] == 6
    assert assertions["company_revenue_mase"] == pytest.approx(0.937448, abs=1e-5)
    assert assertions["funded_vs_total_mase_improvement_pct"] == pytest.approx(1.492706, abs=1e-5)
    assert assertions["segment_expected_rows"] == 24
    assert assertions["segment_model_rows"] == 10
    assert not assertions["missing_segment_rows_imputed"]
    assert assertions["research_freeze_eligible"]
    assert assertions["evidence_parser_freeze_eligible"]
    assert not assertions["forecast_freeze_eligible"]
    assert assertions["fixed_validation_window"] == "2025Q1-2026Q2"
    assert assertions["lmt_v31_parent_unchanged"]
    assert not assertions["terminal_input_allowed"]
    assert not assertions["production_promoted"]
    assert not assertions["new_dcf_run"]
    assert not assertions["new_reverse_dcf_run"]
    assert not assertions["pdf_parsing_used"]
