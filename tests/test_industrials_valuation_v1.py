from pathlib import Path

import pandas as pd

from equity_platform.sectors.industrials import build_annual_financial_bridge
from equity_platform.sectors.industrials.model import build_anchor_validation


ROOT = Path(__file__).resolve().parents[1]
COMPANYFACTS = (
    ROOT.parent / "Arcana/data-lake/bronze/sec/companyfacts/CIK0000018230.json"
)


def test_cat_financial_bridge_is_point_in_time_and_economically_reconciled() -> None:
    frame = build_annual_financial_bridge(COMPANYFACTS, pd.Timestamp("2026-09-03"))
    complete = frame.loc[frame["financial_complete"]]
    assert len(complete) >= 8
    assert complete["financial_available_at"].le(pd.Timestamp("2026-09-03")).all()
    expected = (
        complete["cfo_usd"]
        + complete["interest_expense_usd"].fillna(0.0)
        * (1.0 - complete["effective_tax_rate"])
        - complete["capex_usd"]
    )
    assert (complete["fcff_usd"] - expected).abs().max() <= 1e-6


def test_backlog_anchor_fails_closed_when_it_underperforms_naive() -> None:
    frame = build_annual_financial_bridge(COMPANYFACTS, pd.Timestamp("2026-09-03"))
    _, gate = build_anchor_validation(frame, 3, 3)
    row = gate.iloc[0]
    assert row["walk_forward_validation_observations"] >= 3
    assert row["anchor_revenue_mase_vs_prior_year_naive"] > 1.0
    assert not row["anchor_promoted"]
    assert row["selected_forecast_route"] == "PRIOR_YEAR_REVENUE_NAIVE_BASELINE"
