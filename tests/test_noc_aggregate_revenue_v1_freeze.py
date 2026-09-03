from __future__ import annotations

import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.aggregate_revenue_v1 import (
    verify_noc_aggregate_revenue_v1,
)


def test_noc_aggregate_revenue_v1_is_narrow_and_immutable() -> None:
    manifest = verify_noc_aggregate_revenue_v1(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"]
    assert manifest["research_frozen"]
    assert assertions["benchmark_scope"] == "NOC_AGGREGATE_SEGMENT_GROSS_REVENUE_POINT_RESEARCH_ONLY"
    assert assertions["research_freeze_eligible"]
    assert assertions["aggregate_revenue_point_authority"]
    assert not assertions["aggregate_is_gaap_consolidated_revenue"]
    assert assertions["validation_observations"] == 6
    assert assertions["fixed_validation_window"] == "2025Q1-2026Q2"
    assert assertions["revenue_mase"] == pytest.approx(0.937448, abs=1e-5)
    assert assertions["revenue_mean_ape_pct"] == pytest.approx(4.740289, abs=1e-5)
    assert assertions["funded_backlog_incremental_value"] == "NOT_IDENTIFIED"
    assert assertions["funded_vs_total_mase_improvement_pct"] == pytest.approx(1.492706, abs=1e-5)
    assert not assertions["segment_revenue_attribution_authority"]
    assert assertions["segment_expected_rows"] == 24
    assert assertions["segment_model_rows"] == 10
    assert not assertions["margin_authority"]
    assert assertions["margin_claim_observations"] == 1
    assert not assertions["uncertainty_authority"]
    assert not assertions["terminal_authority"]
    assert not assertions["production_authority"]
    assert not assertions["forecast_freeze_eligible"]
    assert not assertions["new_dcf_run"]
    assert not assertions["new_reverse_dcf_run"]
