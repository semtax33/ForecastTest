from __future__ import annotations

import pandas as pd
import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii_v521 import (
    verify_hii_v521_consensus,
)


OUTPUT = PROJECT_ROOT / "output/industrials_v5_2_1_hii_consensus_overlay_research"


def test_required_arcana_consensus_providers_are_present_and_out_of_fit() -> None:
    coverage = pd.read_csv(OUTPUT / "hii_consensus_provider_coverage.csv")
    assert {"ALPHA_VANTAGE", "FMP", "FINNWORLDS"}.issubset(set(coverage["provider"]))
    assert "YAHOO" in set(coverage["provider"])
    assert not coverage["used_to_fit_dcf"].any()
    targets = pd.read_csv(OUTPUT / "hii_analyst_price_target_vintages.csv").set_index("provider")
    assert targets.loc["FINNWORLDS", "target_average"] == 363.5
    assert targets.loc["FINNWORLDS", "analyst_count"] == 6
    assert not targets.loc["FINNWORLDS", "reference_price_quality_pass"]
    assert not targets["reference_price_used_for_valuation"].any()
    comparison = pd.read_csv(OUTPUT / "hii_model_vs_analyst_expectations.csv").iloc[0]
    assert comparison["official_market_close"] == pytest.approx(324.0150146484)
    assert comparison["official_close_remains_reverse_dcf_target"]
    assert not comparison["analyst_target_used_to_fit_dcf"]


def test_v521_consensus_overlay_is_frozen_without_terminal_authority() -> None:
    manifest = verify_hii_v521_consensus(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"]
    assert assertions["required_providers_present"]
    assert assertions["all_consensus_is_out_of_model_fit"]
    assert assertions["bad_reference_price_cannot_replace_official_close"]
    assert not assertions["terminal_input_allowed"]
    assert not assertions["production_promoted"]
