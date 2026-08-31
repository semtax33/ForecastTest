import json

import pandas as pd
import pytest

from energy_nowcast.data.consensus import (
    current_model_vs_consensus,
    load_arcana_consensus,
    point_in_time_consensus,
)


def test_arcana_provider_adapters_and_point_in_time_ensemble(tmp_path):
    fmp = (
        tmp_path
        / "fmp"
        / "analyst-estimates"
        / "period=quarter"
        / "snapshot_date=2026-07-31"
    )
    av = tmp_path / "alpha-vantage" / "earnings-estimates" / "snapshot_date=2026-07-26"
    fw = tmp_path / "finnworlds" / "company-ratings" / "snapshot_date=2026-07-31"
    fmp.mkdir(parents=True)
    av.mkdir(parents=True)
    fw.mkdir(parents=True)
    (fmp / "ticker=EOG.json").write_text(
        json.dumps(
            {
                "data": [
                    {
                        "date": "2026-09-30",
                        "revenueAvg": 8_000_000_000,
                        "revenueLow": 7_000_000_000,
                        "revenueHigh": 9_000_000_000,
                        "numAnalystsRevenue": 10,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (av / "ticker=EOG.json").write_text(
        json.dumps(
            {
                "estimates": [
                    {
                        "date": "2026-09-30",
                        "horizon": "next fiscal quarter",
                        "revenue_estimate_average": "7000000000",
                        "revenue_estimate_low": "6500000000",
                        "revenue_estimate_high": "8000000000",
                        "revenue_estimate_analyst_count": "6",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (fw / "ticker=EOG.json").write_text(
        json.dumps({"dataset": "COMPANY_RATINGS", "data": []}), encoding="utf-8"
    )

    normalized, coverage = load_arcana_consensus(tmp_path, ("EOG",))
    assert set(normalized["provider"]) == {"FMP", "ALPHA_VANTAGE"}
    assert coverage.loc[0, "revenue_consensus_available"] == False  # noqa: E712
    pit = point_in_time_consensus(normalized, 61)
    assert pit.loc[0, "consensus_revenue"] == pytest.approx(7_500_000_000)
    assert pit.loc[0, "provider_count"] == 2

    nowcast = pd.DataFrame(
        {"ticker": ["EOG"], "nowcast_quarter": ["2026Q3"], "predicted_revenue_B": [7.0]}
    )
    gap = current_model_vs_consensus(nowcast, pit)
    assert gap.loc[0, "model_minus_consensus"] == pytest.approx(-500_000_000)
