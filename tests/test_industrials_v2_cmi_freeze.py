from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v2.benchmark import verify_cmi_v2


def test_cmi_v2_is_frozen_as_portability_research_only() -> None:
    manifest = verify_cmi_v2(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"]
    assert manifest["research_frozen"]
    assert assertions["benchmark_scope"] == "CMI_CROSS_COMPANY_PORTABILITY_RESEARCH_ONLY"
    assert assertions["research_freeze_eligible"]
    assert assertions["sec_periodic_filings"] == 23
    assert assertions["ir_earnings_releases"] == 27
    assert assertions["segment_quarters"] == 135
    assert assertions["segment_sales_coverage_pct"] == 100.0
    assert assertions["segment_ebitda_coverage_pct"] == 100.0
    assert assertions["historical_pit_coverage_pct"] == 100.0
    assert assertions["cutoff_violations"] == 0
    assert assertions["revenue_champions"] == 4
    assert assertions["margin_champions"] == 3
    assert assertions["joint_champions"] == 3
    assert assertions["structural_joint_champion"] == "engine"
    assert assertions["uncertainty_champions"] == 0
    assert not assertions["terminal_input_allowed"]
    assert not assertions["production_promoted"]
    assert not assertions["pdf_parsing_used"]
