from __future__ import annotations

import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii.benchmark import (
    verify_hii_v5_evidence,
)


@pytest.fixture(scope="module")
def manifest() -> dict[str, object]:
    return verify_hii_v5_evidence(PROJECT_ROOT)


def test_hii_v5_evidence_manifest_is_immutable_and_complete(manifest: dict[str, object]) -> None:
    assert manifest["immutable"]
    assert manifest["research_frozen"]
    assert manifest["verified_files"] >= 90
    assert manifest["parents"]["noc_aggregate_v1_manifest"] == "8459fc962cf496043f9eb9f67cfe9421cb5b04450dcf56d3bc33d3b967d1a4b7"


def test_hii_v5_freeze_keeps_authorities_narrow(manifest: dict[str, object]) -> None:
    assertions = manifest["assertions"]
    assert assertions["selected_ticker"] == "HII"
    assert assertions["selection_outcome_blind"]
    assert assertions["sec_filings"] == 27
    assert assertions["sec_ir_comparable_cells"] == 156
    assert assertions["sec_ir_identity_pass_cells"] == 156
    assert assertions["ir_earnings_releases"] == 27
    assert assertions["aggregate_revenue_point_authority"]
    assert assertions["aggregate_revenue_mase"] == pytest.approx(0.6781519925)
    assert assertions["funded_backlog_incremental_value"] == "NOT_TESTABLE_NO_FUNDED_DISCLOSURE"
    assert not assertions["segment_revenue_attribution_authority"]
    assert not assertions["margin_authority"]
    assert not assertions["uncertainty_authority"]
    assert assertions["roic_reinvestment_authority"] == "HISTORICAL_DIAGNOSTIC_ONLY"
    assert assertions["three_company_aggregate_pass"]
    assert assertions["three_company_segment_timing_mixed"]
    assert not assertions["industry_conclusion_allowed"]
    assert not assertions["forecast_freeze_eligible"]
    assert not assertions["terminal_input_allowed"]
    assert not assertions["production_promoted"]
    assert not assertions["new_dcf_run"]
    assert not assertions["new_reverse_dcf_run"]
    assert not assertions["pdf_parsing_used"]
