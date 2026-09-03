from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v17.benchmark import verify_margin_v1_7


def test_cat_margin_v1_7_is_a_research_only_frozen_benchmark() -> None:
    manifest = verify_margin_v1_7(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"]
    assert manifest["research_frozen"]
    assert assertions["benchmark_scope"] == "CAT_SEGMENT_MARGIN_RESEARCH_ONLY"
    assert assertions["research_freeze_eligible"]
    assert assertions["margin_champion_segments"] == 2
    assert assertions["maximum_selected_margin_mase"] < 1.5
    assert assertions["oos_observations_per_segment"] == 6
    assert assertions["historical_pit_coverage_pct"] == 100.0
    assert assertions["sec_periodic_filings"] == 23
    assert assertions["ir_earnings_releases"] == 23
    assert assertions["quarterly_discrete_note_rows_complete"] == 20
    assert assertions["unforecastable_scope_change_rows"] == 4
    assert not assertions["terminal_input_allowed"]
    assert not assertions["new_dcf_run"]
    assert not assertions["new_reverse_dcf_run"]
    assert not assertions["production_promoted"]
    assert not assertions["pdf_parsing_used"]
