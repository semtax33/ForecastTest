from pathlib import Path

import pytest

from equity_platform.domain import ForecastSnapshot
from equity_platform.storage import LiveForwardStore
from equity_platform.valuation import DcfAssumptions, enterprise_value, solve_implied_growth


def _snapshot() -> ForecastSnapshot:
    return ForecastSnapshot(
        forecast_as_of="2026-09-03",
        model_version="TEST_V1",
        sector="Industrials",
        subindustry="Machinery",
        ticker="CAT",
        target_period="2026FY",
        input_hash="input",
        revenue_forecast_usd=100.0,
        ebit_forecast_usd=10.0,
        margin_forecast_pct=10.0,
        fcff_forecast_usd=8.0,
        roic_forecast_pct=12.0,
        forward_dcf_value_per_share=50.0,
        reverse_dcf_metric="IMPLIED_GROWTH",
        reverse_dcf_value=2.0,
        expectations_gap_pct=5.0,
        consensus_value_usd=98.0,
        consensus_as_of="2026-09-02",
        source_manifest_sha256="manifest",
    )


def test_live_store_is_append_only_and_settles_forward_actuals(tmp_path: Path) -> None:
    with LiveForwardStore(tmp_path / "live.sqlite") as store:
        assert store.add_snapshot(_snapshot()) == "INSERTED"
        assert store.add_snapshot(_snapshot()) == "UNCHANGED"
        altered = ForecastSnapshot(**{**_snapshot().__dict__, "fcff_forecast_usd": 9.0})
        with pytest.raises(RuntimeError, match="Immutable forecast_snapshots"):
            store.add_snapshot(altered)
        store.add_actual(
            {
                "ticker": "CAT",
                "target_period": "2026FY",
                "release_date": "2027-02-01",
                "actual_revenue_usd": 110.0,
                "actual_ebit_usd": 11.0,
                "actual_fcff_usd": 7.0,
                "actual_roic_pct": 11.0,
                "market_price": 55.0,
                "source_path": "actual.csv",
                "source_hash": "actual",
            }
        )
        settled = store.settle_available()
        assert len(settled) == 1
        error = store.table("error_attributions").iloc[0]
        assert error["margin_error_pct_points"] == pytest.approx(0.0)
        assert error["valuation_error_pct"] == pytest.approx(-9.09090909)


def test_reverse_dcf_round_trip_and_unbracketed_status() -> None:
    assumptions = DcfAssumptions(
        base_revenue_usd=100.0,
        near_term_growth_pct=4.0,
        operating_margin_pct=15.0,
        tax_rate_pct=21.0,
        roic_pct=12.0,
        wacc_pct=9.0,
        terminal_growth_pct=2.0,
    )
    _, value = enterprise_value(assumptions)
    solved = solve_implied_growth(assumptions, value, tolerance_usd=1e-9)
    assert solved["status"] == "SOLVED"
    assert solved["implied_growth_pct"] == pytest.approx(4.0, abs=1e-7)
    unbracketed = solve_implied_growth(assumptions, value * 100.0)
    assert unbracketed["status"] == "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"
