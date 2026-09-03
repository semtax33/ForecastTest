from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v15.benchmark import verify_v15_pit_data


def test_v1_5_pit_data_is_frozen_separately_from_forecast_model() -> None:
    manifest = verify_v15_pit_data(PROJECT_ROOT)
    assertions = manifest["assertions"]
    assert manifest["immutable"]
    assert manifest["research_frozen"]
    assert assertions["benchmark_scope"] == "PIT_DATA_INFRASTRUCTURE_NOT_FORECAST_MODEL"
    assert assertions["bls_archive_report_files"] == 54
    assert assertions["bls_release_schedule_files"] == 5
    assert assertions["bls_vintage_rows"] == 3509
    assert assertions["bls_series_count"] == 13
    assert assertions["pit_feature_rows"] == 42
    assert assertions["pit_series_coverage_pct"] == 100.0
    assert assertions["cutoff_violations"] == 0
    assert assertions["cat_retail_vintage_rows"] == 946
    assert assertions["historical_pit_ready"]
    assert not assertions["pdf_parsing_used"]
    assert not assertions["forecast_model_frozen"]
    assert not assertions["research_freeze_eligible"]
    assert not assertions["terminal_evidence_eligible"]
    assert not assertions["production_promotable"]
