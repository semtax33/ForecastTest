from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii_v53 import (
    verify_hii_v53_margin_research,
)


def test_v53_manifest_is_immutable_and_narrow() -> None:
    manifest = verify_hii_v53_margin_research(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"] and manifest["research_frozen"]
    assert assertions["research_freeze_eligible"]
    assert assertions["all_10k_parsed"] and assertions["all_10q_parsed"]
    assert assertions["ir_history_coverage_complete"]
    assert assertions["ir_source_hashes_verified"]
    assert assertions["contract_mix_identities_pass"]
    assert assertions["catchup_identities_pass"]
    assert assertions["fas_cas_identities_pass"]
    assert assertions["backlog_identities_pass"]
    assert assertions["dcf_crosscheck_run"]
    assert not assertions["fair_value_claim_allowed"]
    assert not assertions["terminal_input_allowed"]
    assert not assertions["production_promoted"]
