from pathlib import Path

from equity_platform.sectors.industrials.v12.benchmark import verify_v12_architecture


ROOT = Path(__file__).resolve().parents[1]


def test_industrials_v1_2_is_frozen_as_architecture_only() -> None:
    manifest = verify_v12_architecture(ROOT)
    assertions = manifest["assertions"]
    assert manifest["research_frozen"] is True
    assert assertions["benchmark_scope"] == "ARCHITECTURE_NOT_FORECAST_PERFORMANCE"
    assert assertions["gics_sector_count"] == 11
    assert assertions["sensor_count"] == 59
    assert assertions["cat_sensor_count"] == 6
    assert assertions["historical_pit_backtest_allowed"] is False
    assert assertions["parser_cross_filing_mismatches"] == 0
    assert assertions["non_identification_preserved"] is True
    assert assertions["backlog_model_changed"] is False
    assert assertions["terminal_input_allowed"] is False
    assert assertions["production_promoted"] is False
