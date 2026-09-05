from __future__ import annotations

import json

import numpy as np
import pandas as pd

from equity_platform.sectors.energy.research.revenue.v35.adapters import (
    _guidance_period_semantics,
)
from energy_nowcast.research.v351.revenue import load_companyfacts_quarterly_revenue
from equity_platform.validation.cross_section_metrics import ticker_scorecard


def _fact(start: str, end: str, value: float, filed: str, fy: int, fp: str, form: str, accn: str) -> dict[str, object]:
    return {
        "start": start,
        "end": end,
        "val": value,
        "accn": accn,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
        "frame": None,
    }


def test_companyfacts_loader_selects_direct_quarters_and_derives_q4(tmp_path) -> None:
    rows = [
        _fact("2022-01-01", "2022-03-31", 100.0, "2022-04-25", 2022, "Q1", "10-Q", "q1"),
        _fact("2022-01-01", "2022-06-30", 250.0, "2022-07-25", 2022, "Q2", "10-Q", "q2"),
        _fact("2022-04-01", "2022-06-30", 150.0, "2022-07-25", 2022, "Q2", "10-Q", "q2"),
        _fact("2022-01-01", "2022-09-30", 450.0, "2022-10-25", 2022, "Q3", "10-Q", "q3"),
        _fact("2022-07-01", "2022-09-30", 200.0, "2022-10-25", 2022, "Q3", "10-Q", "q3"),
        _fact("2022-01-01", "2022-12-31", 700.0, "2023-02-20", 2022, "FY", "10-K", "fy"),
        # Later comparative copy must not be relabeled as a 2023 fact.
        _fact("2022-01-01", "2022-03-31", 100.0, "2023-04-25", 2023, "Q1", "10-Q", "later"),
    ]
    payload = {
        "facts": {"us-gaap": {"Revenues": {"units": {"USD": rows}}}},
    }
    path = tmp_path / "CIK0001070412.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = load_companyfacts_quarterly_revenue(tmp_path, ["CNX"])
    values = result.set_index("quarter")["revenue"].to_dict()
    assert values == {"2022Q1": 100.0, "2022Q2": 150.0, "2022Q3": 200.0, "2022Q4": 250.0}
    assert result.set_index("quarter").loc["2022Q2", "duration_days"] == 91
    assert result.set_index("quarter").loc["2022Q4", "revenue_method"] == "DERIVED_Q4_FY_MINUS_Q1_Q2_Q3"


def test_directional_hit_counts_numpy_boole_in_object_series() -> None:
    predictions = pd.DataFrame({
        "ticker": ["EOG"] * 8,
        "actual_log_yoy": np.arange(1.0, 9.0),
        "legacy_prediction": np.arange(1.0, 9.0),
        "candidate_prediction": np.arange(1.0, 9.0),
        "candidate_revenue_ape_pct": [1.0] * 8,
        "covered_80": [True] * 8,
        "direction_correct": pd.Series([np.bool_(True)] * 8, dtype=object),
    })
    score = ticker_scorecard(predictions, minimum_observations=8)
    assert score.loc[0, "directional_hit_rate"] == 1.0


def test_guidance_period_semantics_fail_closed() -> None:
    assert _guidance_period_semantics("Second quarter guidance") == "QUARTERLY_EXPLICIT"
    assert _guidance_period_semantics("Full-year production guidance") == "ANNUAL"
    assert _guidance_period_semantics("Second quarter and full year guidance") == "MIXED_PERIOD_TABLE"
    assert _guidance_period_semantics("Production guidance") == "UNRESOLVED"
