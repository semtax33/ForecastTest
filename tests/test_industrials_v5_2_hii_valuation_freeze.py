from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_hii_v52_valuation,
)


def test_v52_conditional_valuation_manifest_is_immutable_and_narrow() -> None:
    manifest = verify_hii_v52_valuation(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"]
    assert manifest["research_frozen"]
    assert assertions["research_freeze_eligible"]
    assert assertions["quarterly_nwc_chain_complete"]
    assert assertions["fcff_identity_pass"]
    assert assertions["solver_round_trip_pass"]
    assert assertions["ev_to_equity_identity_pass"]
    assert assertions["dcf_run"] and assertions["reverse_dcf_run"]
    assert assertions["high_terminal_dependence"]
    assert not assertions["terminal_input_allowed"]
    assert not assertions["production_promoted"]
