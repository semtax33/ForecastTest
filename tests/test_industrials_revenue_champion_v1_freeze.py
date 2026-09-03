from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v16.benchmark import verify_revenue_champion_v1


def test_cat_revenue_champion_is_frozen_without_margin_or_valuation_authority() -> None:
    manifest = verify_revenue_champion_v1(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"]
    assert assertions["benchmark_scope"] == "CAT_SEGMENT_REVENUE_FORECAST_ONLY"
    assert assertions["segments"] == 3
    assert assertions["oos_observations_per_segment"] == 6
    assert assertions["historical_pit_coverage_pct"] == 100.0
    assert assertions["champion_segments"] == 3
    assert assertions["maximum_revenue_mase"] < 1.0
    assert assertions["all_wape_below_naive"]
    assert assertions["minimum_direction_accuracy_pct"] >= 50.0
    assert assertions["all_no_material_regression"]
    assert not assertions["margin_model_in_scope"]
    assert not assertions["reinvestment_model_in_scope"]
    assert not assertions["roic_model_in_scope"]
    assert not assertions["terminal_input_allowed"]
    assert not assertions["production_promoted"]
