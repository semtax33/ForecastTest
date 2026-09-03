from __future__ import annotations

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_ad_aggregate_replication_v1,
)


OUTPUT = PROJECT_ROOT / "output/aerospace_defense_aggregate_revenue_replication_v1"


def test_three_company_replication_is_not_overclaimed_as_industry_law() -> None:
    summary = pd.read_csv(OUTPUT / "ad_aggregate_replication_summary.csv").iloc[0]
    assert (summary["companies"], summary["aggregate_pass"], summary["aggregate_total"]) == (3, 3, 3)
    assert (summary["segment_pass"], summary["segment_total"]) == (6, 10)
    assert summary["cross_company_replication"]
    assert not summary["cross_regime_replication"]
    assert summary["status"] == "REPLICATED_RESEARCH_HYPOTHESIS_NOT_INDUSTRY_LAW"
    assert not summary["terminal_input_allowed"]
    assert not summary["production_promoted"]


def test_replication_manifest_is_immutable_and_narrow() -> None:
    manifest = verify_ad_aggregate_replication_v1(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"]
    assert assertions["aggregate_pass"] == 3
    assert assertions["aggregate_total"] == 3
    assert assertions["segment_pass"] == 6
    assert assertions["segment_total"] == 10
    assert assertions["cross_company_replication"]
    assert not assertions["cross_regime_replication"]
    assert not assertions["terminal_input_allowed"]
    assert not assertions["production_promoted"]
