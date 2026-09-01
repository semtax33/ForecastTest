from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.v35.adapters import (
    ACTUAL_COLUMNS,
    COMPANY_ADAPTERS,
    GUIDANCE_COLUMNS,
    PRICE_COLUMNS,
    StandardizedKPIBundle,
    _guidance_scale_sanity,
)
from energy_nowcast.research.v35.strategy import KPIHierarchicalStrategy, V35StrategyConfig
from energy_nowcast.research.v35.taxonomy import E_AND_P_GROUPS, all_tickers, group_for_ticker
from energy_nowcast.research.v35.validation import v35_promotion_gate


ROOT = Path(__file__).resolve().parents[1]


def _row(columns: list[str], **values: object) -> dict[str, object]:
    return {column: values.get(column, np.nan) for column in columns}


def _strategy(
    *,
    late_guidance_total: float | None = None,
    drop_eog_prior: bool = False,
    use_company_basis: bool = True,
) -> KPIHierarchicalStrategy:
    actual_rows = [
        _row(ACTUAL_COLUMNS, ticker="EOG", quarter="2022Q2", oil_mbpd=60.0, ngl_mbpd=15.0,
             gas_mmcfd=150.0, total_mboed=100.0, filing_date="2022-08-01", quality_score=0.9,
             mna_flag=False, adapter="TEST"),
        _row(ACTUAL_COLUMNS, ticker="EOG", quarter="2023Q2", oil_mbpd=66.0, ngl_mbpd=16.0,
             gas_mmcfd=168.0, total_mboed=110.0, filing_date="2023-08-01", quality_score=0.9,
             mna_flag=False, adapter="TEST"),
        _row(ACTUAL_COLUMNS, ticker="PR", quarter="2022Q2", oil_mbpd=120.0, ngl_mbpd=30.0,
             gas_mmcfd=300.0, total_mboed=200.0, filing_date="2022-08-01", quality_score=0.9,
             mna_flag=False, adapter="TEST"),
        _row(ACTUAL_COLUMNS, ticker="PR", quarter="2023Q2", oil_mbpd=126.0, ngl_mbpd=31.0,
             gas_mmcfd=318.0, total_mboed=210.0, filing_date="2023-08-01", quality_score=0.9,
             mna_flag=False, adapter="TEST"),
    ]
    if drop_eog_prior:
        actual_rows = [row for row in actual_rows if not (row["ticker"] == "EOG" and row["quarter"] == "2023Q2")]
    guidance_rows: list[dict[str, object]] = []
    if late_guidance_total is not None:
        guidance_rows.append(_row(
            GUIDANCE_COLUMNS,
            ticker="EOG",
            target_quarter="2024Q2",
            total_mboed_low=late_guidance_total,
            total_mboed_high=late_guidance_total,
            total_mboed_mid=late_guidance_total,
            filing_date="2024-07-15",
            quality_score=0.9,
            adapter="TEST_LATE_GUIDANCE",
        ))
    bundle = StandardizedKPIBundle(
        production_actuals=pd.DataFrame(actual_rows, columns=ACTUAL_COLUMNS),
        production_guidance=pd.DataFrame(guidance_rows, columns=GUIDANCE_COLUMNS),
        realized_prices=pd.DataFrame(columns=PRICE_COLUMNS),
        coverage=pd.DataFrame(),
    )
    panel_rows = []
    for ticker, revenue_2022, revenue_2023 in (("EOG", 1000.0, 1100.0), ("PR", 1900.0, 2100.0)):
        panel_rows.extend([
            {"ticker": ticker, "quarter": "2022Q2", "quarter_ordinal": pd.Period("2022Q2", freq="Q").ordinal,
             "revenue": revenue_2022, "prior_year_revenue": revenue_2022 / 1.1, "report_date": "2022-08-01"},
            {"ticker": ticker, "quarter": "2023Q2", "quarter_ordinal": pd.Period("2023Q2", freq="Q").ordinal,
             "revenue": revenue_2023, "prior_year_revenue": revenue_2022, "report_date": "2023-08-01"},
        ])
    panel_rows.append({
        "ticker": "EOG", "quarter": "2024Q2", "quarter_ordinal": pd.Period("2024Q2", freq="Q").ordinal,
        "revenue": 1200.0, "prior_year_revenue": 1100.0, "report_date": "2024-08-01",
    })
    prices = pd.DataFrame([
        {"quarter": "2022Q2", "wti_price": 100.0, "propane_price_bbl": 40.0, "henry_price": 6.0},
        {"quarter": "2023Q2", "wti_price": 75.0, "propane_price_bbl": 30.0, "henry_price": 2.5},
        {"quarter": "2024Q2", "wti_price": 80.0, "propane_price_bbl": 32.0, "henry_price": 2.0},
    ])
    return KPIHierarchicalStrategy(
        bundle,
        pd.DataFrame(panel_rows),
        prices,
        V35StrategyConfig(use_company_basis=use_company_basis),
    )


def test_fixed_taxonomy_is_exact_and_disjoint() -> None:
    assert E_AND_P_GROUPS == {
        "oil_heavy": ("EOG", "FANG", "PR", "MTDR", "MGY", "NOG"),
        "gas_heavy": ("EQT", "AR", "RRC", "CNX"),
        "mixed": ("COP", "DVN", "OVV", "SM"),
    }
    assert len(all_tickers()) == len(set(all_tickers())) == 14
    assert group_for_ticker("AR") == "gas_heavy"
    assert tuple(COMPANY_ADAPTERS) == all_tickers()
    assert COMPANY_ADAPTERS["OVV"].local_operational_source_available is False


def test_guidance_unit_sanity_converts_raw_daily_units() -> None:
    assert _guidance_scale_sanity(320_000.0, "total") == 320.0
    assert _guidance_scale_sanity(150_000.0, "oil") == 150.0
    assert _guidance_scale_sanity(3_500.0, "gas") == 3_500.0


def test_loco_prediction_is_invariant_to_held_company_revenue_labels() -> None:
    strategy = _strategy()
    first = strategy.predict("EOG", "2024Q2", excluded_ticker="EOG")
    assert first is not None
    strategy.revenue.loc[
        strategy.revenue["ticker"].eq("EOG"), ["revenue", "prior_year_revenue"]
    ] *= 1000.0
    second = strategy.predict("EOG", "2024Q2", excluded_ticker="EOG")
    assert second is not None
    assert second["prediction_log_yoy"] == first["prediction_log_yoy"]
    assert second["basis_adjustment_log_points"] == 0.0
    assert second["heldout_company_revenue_excluded"] is True


def test_no_revenue_implied_production_fallback() -> None:
    assert _strategy(drop_eog_prior=True).predict("EOG", "2024Q2") is None


def test_clean_component_disables_company_basis_completely() -> None:
    prediction = _strategy(use_company_basis=False).predict("EOG", "2024Q2")
    assert prediction is not None
    assert prediction["basis_adjustment_log_points"] == 0.0
    assert prediction["prediction_log_yoy"] == prediction["component_growth_log_points"]
    assert prediction["company_basis_overlay_applied"] is False
    assert prediction["basis_overlay_mode"] == "DISABLED_CLEAN_COMPONENT"


def test_post_cutoff_guidance_cannot_change_prediction() -> None:
    low = _strategy(late_guidance_total=120.0).predict("EOG", "2024Q2")
    high = _strategy(late_guidance_total=1200.0).predict("EOG", "2024Q2")
    assert low is not None and high is not None
    assert low["volume_source"] == high["volume_source"] == "HIERARCHICAL_VOLUME_GROWTH"
    assert low["prediction_log_yoy"] == high["prediction_log_yoy"]


def test_macro_overlay_and_promotion_fail_closed() -> None:
    score = pd.DataFrame({
        "ticker": list(all_tickers()),
        "observations": [8] * 14,
        "mase": [0.7] * 14,
        "improvement_log_points": [1.0] * 13 + [-3.0],
    })
    summary = pd.Series({
        "median_ticker_mase": 0.7,
        "mean_ticker_mase": 0.7,
        "mean_pi_80_coverage": 0.80,
    })
    gate = v35_promotion_gate(score, summary, ready_company_count=14, live_matches=0)
    assert not gate["research_component_gate"].any()
    assert not gate["macro_overlay_enabled"].any()
    assert not gate["champion_promotion"].any()


def test_rejected_proxy_experiment_is_preserved() -> None:
    status = pd.read_json(ROOT / "output" / "universe" / "experiment_status.json", typ="series")
    assert status["status"] == "REJECTED_EXPERIMENT"
