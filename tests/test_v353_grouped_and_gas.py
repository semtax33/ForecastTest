from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.sectors.energy.research.revenue.v35.adapters import (
    StandardizedKPIBundle,
)
from equity_platform.sectors.energy.research.revenue.v35.strategy import (
    KPIHierarchicalStrategy,
    V35StrategyConfig,
)
from equity_platform.sectors.energy.research.revenue.v35.taxonomy import (
    E_AND_P_GROUPS,
    all_tickers,
    group_for_ticker,
)
from energy_nowcast.research.v353.gas_prices import (
    classify_gas_price_label,
    merge_strict_gas_prices,
)
from energy_nowcast.research.v353.gas_validation import gas_research_gate
from energy_nowcast.research.v353.validation import (
    group_promotion_table,
    grouped_success_gate,
)


def _group_score() -> pd.DataFrame:
    rows = []
    for ticker in all_tickers():
        gas = group_for_ticker(ticker) == "gas_heavy"
        rows.append({
            "ticker": ticker,
            "observations": 8,
            "mase": 0.90 if gas else 0.60,
            "improvement_log_points": -5.0 if gas else 2.0,
            "pi_80_coverage": 0.80,
            "directional_hit_rate": 0.70,
        })
    return pd.DataFrame(rows)


def test_group_promotion_isolates_failing_gas_heavy() -> None:
    promotion = group_promotion_table(_group_score(), _group_score()).set_index("group")
    assert promotion.loc["oil_heavy", "active_model"] == "CLEAN_COMPONENT"
    assert promotion.loc["mixed", "active_model"] == "CLEAN_COMPONENT"
    assert promotion.loc["gas_heavy", "active_model"] == "LEGACY"
    assert bool(promotion.loc["oil_heavy", "macro_research_unlocked"])
    assert not bool(promotion.loc["gas_heavy", "macro_research_unlocked"])
    assert int(promotion.loc["gas_heavy", "time_severe_regression_count"]) == 4


def test_grouped_success_gate_uses_feedback_thresholds() -> None:
    score = pd.DataFrame({
        "ticker": [f"T{i}" for i in range(13)],
        "mase": [0.60] * 13,
        "improvement_log_points": [1.0] * 12 + [-1.0],
    })
    summary = pd.Series({
        "median_ticker_mase": 0.60,
        "mean_ticker_mase": 0.65,
        "mean_pi_80_coverage": 0.80,
        "mean_directional_hit_rate": 0.70,
    })
    gate = grouped_success_gate(score, summary, live_matches=0)
    assert gate["grouped_component_gate"].all()
    assert not gate["production_eligible"].any()
    detail = gate.loc[
        gate["condition"].eq("time_legacy_no_regression_at_least_85pct"), "detail"
    ].item()
    assert detail == "12/13 evaluable = 92.3%"


def test_strict_gas_label_filter_rejects_toc_and_differentials() -> None:
    assert classify_gas_price_label(
        "Market Mix and Natural Gas Price Reconciliation................................"
    ) is None
    assert classify_gas_price_label(
        "Natural Gas Realized Price Differential to NYMEX ($/Mcf)"
    ) is None
    assert classify_gas_price_label(
        "Realized Price Before Financial Hedging (per Mcf)"
    ) == "PRE_HEDGE_REALIZED"
    assert classify_gas_price_label(
        "Average natural gas price, including cash settled derivatives ($/Mcf)"
    ) == "HEDGE_ADJUSTED_REALIZED"


def test_strict_gas_merge_replaces_false_price_only_for_gas_component() -> None:
    base = pd.DataFrame([{
        "ticker": "CNX",
        "quarter": "2024Q2",
        "realized_oil_price": 60.0,
        "realized_ngl_price": 22.0,
        "realized_gas_price": 8.0,
        "hedge_included": False,
        "filing_date": "2024-07-25",
        "source_url": "old",
        "source_path": "old",
        "quality_score": 0.7,
        "adapter": "OLD",
    }])
    strict = pd.DataFrame([{
        "ticker": "CNX",
        "quarter": "2024Q2",
        "realized_gas_price": 2.01,
        "hedge_included": False,
        "filing_date": "2024-07-25",
        "source_url": "strict",
        "source_path": "strict",
        "quality_score": 0.92,
    }])
    merged = merge_strict_gas_prices(base, strict).iloc[0]
    assert merged["realized_gas_price"] == 2.01
    assert merged["realized_oil_price"] == 60.0
    assert merged["realized_ngl_price"] == 22.0


def test_gas_basis_mode_normalizes_mcf_price_to_boe() -> None:
    realized = pd.DataFrame([{
        "ticker": "EQT",
        "quarter": "2023Q1",
        "realized_oil_price": np.nan,
        "realized_ngl_price": np.nan,
        "realized_gas_price": 2.0,
        "hedge_included": False,
        "filing_date": "2023-04-20",
        "source_url": "test",
        "source_path": "test",
        "quality_score": 0.9,
        "adapter": "TEST",
    }])
    bundle = StandardizedKPIBundle(
        production_actuals=pd.DataFrame(),
        production_guidance=pd.DataFrame(),
        realized_prices=realized,
        coverage=pd.DataFrame(),
    )
    prices = pd.DataFrame([
        {"quarter": "2023Q1", "wti_price": 75.0, "propane_price_bbl": 30.0, "henry_price": 3.0},
        {"quarter": "2024Q1", "wti_price": 80.0, "propane_price_bbl": 32.0, "henry_price": 4.0},
    ])
    strategy = KPIHierarchicalStrategy(
        bundle,
        pd.DataFrame({"quarter": pd.Series(dtype=str)}),
        prices,
        V35StrategyConfig(
            use_company_basis=False,
            gas_heavy_price_mode="REALIZED_ADDITIVE_BASIS",
        ),
    )
    actual = strategy._actual_realized_prices(  # noqa: SLF001
        "EQT",
        "2023Q1",
        pd.Timestamp("2024-03-01"),
        {"oil": 75.0, "ngl": 30.0, "gas": 18.0},
    )
    forecast, basis, company_n, _ = strategy._gas_realized_basis_forecast(  # noqa: SLF001
        "EQT", "2024Q1", pd.Timestamp("2024-03-01")
    )
    assert actual["gas"] == 12.0
    assert basis == -1.0
    assert forecast == 3.0
    assert company_n == 1


def test_failed_gas_research_retains_legacy_and_macro_lock() -> None:
    score = _group_score().loc[lambda frame: frame["ticker"].isin(E_AND_P_GROUPS["gas_heavy"])]
    strict = pd.DataFrame({"ticker": list(E_AND_P_GROUPS["gas_heavy"])})
    gate = gas_research_gate(score, strict)
    assert not gate["gas_research_gate"].any()
    assert gate["active_group_model"].eq("LEGACY").all()
    assert not gate["gas_macro_research_unlocked"].any()
