from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii_v54 import (
    verify_hii_v54_margin_mechanism_research,
)


def test_v54_manifest_is_immutable_narrow_and_fail_closed() -> None:
    manifest = verify_hii_v54_margin_mechanism_research(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"] and manifest["research_frozen"]
    assert assertions["research_freeze_eligible"]
    assert assertions["all_10k_available"] and assertions["all_10q_available"]
    assert assertions["all_ir_hashes_verified"]
    assert assertions["guidance_vintage_coverage_complete"]
    assert assertions["bls_series_complete"] and assertions["bls_cutoff_enforced"]
    assert assertions["all_lineage_hashes_verified"]
    assert assertions["dcf_reverse_crosscheck_run"]
    assert not assertions["contract_vintage_margin_identified"]
    assert not assertions["direct_labor_hours_identified"]
    assert not assertions["price_reset_lag_identified"]
    assert not assertions["contemporaneous_eight_pct_observed"]
    assert not assertions["structural_eight_to_ten_mechanism_proven"]
    assert not assertions["valuation_upgrade_allowed"]
    assert not assertions["fair_value_claim_allowed"]
    assert not assertions["terminal_input_allowed"]
    assert not assertions["production_promoted"]
    assert assertions["recent_contemporaneous_normalized_max_pct"] < 8.0
