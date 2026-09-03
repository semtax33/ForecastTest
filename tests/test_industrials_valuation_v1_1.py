from pathlib import Path

import pandas as pd
import pytest

from equity_platform.sectors.industrials import (
    build_annual_financial_bridge,
    build_backlog_semantic_audit,
    build_cat_backlog_history,
    build_cat_segment_history,
    build_cat_sotp_research,
    build_next_year_backlog_bridge,
    build_segment_claim_reconciliation,
    load_cat_10k_sources,
)
from equity_platform.sectors.industrials.market import build_market_inputs
from equity_platform.sectors.industrials.sotp import residual_income_value


ROOT = Path(__file__).resolve().parents[1]
ARCANA = ROOT.parent / "Arcana/data-lake/bronze"
CUTOFF = pd.Timestamp("2026-09-03")


@pytest.fixture(scope="module")
def cat_v1_1() -> dict[str, object]:
    sources = load_cat_10k_sources(
        ROOT,
        ROOT / "configs/industrials_v1_1_cat_10k_sources.csv",
        CUTOFF,
    )
    segments = build_cat_segment_history(sources)
    backlog = build_cat_backlog_history(sources)
    backlog_results = build_next_year_backlog_bridge(
        backlog,
        segments.rename(columns={"mpe_total_revenue_usd": "mpe_revenue_usd"}),
        minimum_history_observations=2,
        minimum_validation_observations=3,
    )
    consolidated = build_annual_financial_bridge(
        ARCANA / "sec/companyfacts/CIK0000018230.json", CUTOFF
    )
    market = build_market_inputs(
        companyfacts_path=ARCANA / "sec/companyfacts/CIK0000018230.json",
        price_path=ARCANA / "yfinance/price/CAT.csv",
        benchmark_path=ARCANA / "yfinance/benchmark/us_sp500.csv",
        risk_free_path=ARCANA / "fred/rates/us_dgs10.csv",
        annual_financials=consolidated,
        cutoff=CUTOFF,
        equity_risk_premium_pct=4.5,
        fallback_credit_spread_pct=2.0,
        beta_weeks=104,
    )
    valuation = build_cat_sotp_research(
        segment_history=segments,
        market=market,
        backlog_results=backlog_results,
        bridge_history_years=5,
        terminal_growth_pct=2.0,
        horizon_years=5,
        finance_cost_of_equity_sensitivity_pct=1.0,
        reverse_growth_lower_pct=-10.0,
        reverse_growth_upper_pct=15.0,
        v1_forecast=pd.read_csv(
            ROOT / "output/industrials_valuation_v1_research/forecast_financial_bridge.csv"
        ),
    )
    return {
        "sources": sources,
        "segments": segments,
        "backlog": backlog,
        "backlog_results": backlog_results,
        "consolidated": consolidated,
        "market": market,
        "valuation": valuation,
    }


def test_direct_10k_backlog_parser_preserves_disclosed_semantics(
    cat_v1_1: dict[str, object],
) -> None:
    backlog = cat_v1_1["backlog"]
    latest = backlog.iloc[-1]
    assert len(backlog) == 5
    assert latest["fiscal_year"] == 2025
    assert latest["firm_backlog_usd"] == pytest.approx(51.2e9)
    assert latest["not_expected_next_year_usd"] == pytest.approx(19.3e9)
    assert latest["expected_within_next_year_usd"] == pytest.approx(31.9e9)
    assert latest["expected_fill_year"] == 2026
    assert backlog["next_year_identity_pass"].all()
    assert backlog["parser_confidence"].eq("HIGH_DIRECT_TEXT_MATCH").all()


def test_rpo_is_retired_and_never_equated_to_firm_order_backlog(
    cat_v1_1: dict[str, object],
) -> None:
    audit = build_backlog_semantic_audit(
        cat_v1_1["backlog"], cat_v1_1["consolidated"]
    )
    assert not audit["same_economic_semantics"].any()
    assert audit["v1_rpo_anchor_status"].eq("RETIRED_WRONG_KPI_SEMANTICS").all()
    assert audit["direct_backlog_anchor_status"].eq(
        "RESEARCH_ONLY_PENDING_OOS_GATE"
    ).all()


def test_direct_backlog_bridge_fails_closed_on_short_oos_history(
    cat_v1_1: dict[str, object],
) -> None:
    results = cat_v1_1["backlog_results"]
    gate = results["backlog_anchor_gate"].iloc[0]
    candidate = results["backlog_conversion_candidate"].iloc[0]
    assert gate["walk_forward_validation_observations"] == 2
    assert gate["minimum_validation_observations"] == 3
    assert gate["anchor_revenue_mase_vs_prior_year_naive"] == pytest.approx(
        0.5924059869891197
    )
    assert not gate["anchor_promoted"]
    assert gate["selected_forecast_route"] == "PRIOR_YEAR_MPE_REVENUE_BASELINE"
    assert not candidate["selected_for_valuation"]
    assert candidate["candidate_revenue_mid_usd"] == pytest.approx(91.47075e9, rel=1e-5)


def test_supplemental_segment_parser_reconciles_and_separates_debt(
    cat_v1_1: dict[str, object],
) -> None:
    segments = cat_v1_1["segments"]
    latest = segments.iloc[-1]
    assert len(segments) == 5
    assert segments["segment_reconciliation_pass"].all()
    assert latest["mpe_total_revenue_usd"] == pytest.approx(63.980e9)
    assert latest["financial_products_total_revenue_usd"] == pytest.approx(4.382e9)
    assert latest["mpe_total_debt_usd"] == pytest.approx(10.990e9)
    assert latest["fp_funding_debt_usd"] == pytest.approx(33.617e9)
    assert latest["financial_products_equity_usd"] == pytest.approx(4.841e9)
    assert latest["fp_credit_loss_provision_usd"] == pytest.approx(109e6)
    assert latest["fp_credit_loss_allowance_usd"] == pytest.approx(277e6)
    assert latest["fp_finance_receivables_total_usd"] == pytest.approx(25.150e9)
    claims = build_segment_claim_reconciliation(segments)
    assert claims["reconciliation_pass"].all()
    assert claims["reconciliation_error_usd"].abs().max() <= 1.0


def test_residual_income_equals_justified_price_to_book_identity() -> None:
    projection, residual_value, pb_value = residual_income_value(
        book_equity_usd=4.841e9,
        roe_pct=16.2,
        cost_of_equity_pct=9.67,
        growth_pct=2.0,
        horizon_years=5,
    )
    assert len(projection) == 5
    assert residual_value == pytest.approx(pb_value, abs=2.0)
    assert residual_value > 4.841e9


def test_sotp_uses_only_mpe_debt_and_prevents_finance_debt_double_counting(
    cat_v1_1: dict[str, object],
) -> None:
    valuation = cat_v1_1["valuation"]
    bridge = valuation["mpe_forecast_financial_bridge"].iloc[0]
    sotp = valuation["sotp_valuation"].iloc[0]
    gate = valuation["industrials_v1_1_gate"].iloc[0]
    expected_equity = (
        bridge["mpe_enterprise_value_usd"]
        - bridge["mpe_debt_used_usd"]
        + bridge["mpe_cash_used_usd"]
        + sotp["financial_products_equity_value_usd"]
    )
    assert bridge["mpe_debt_used_usd"] == pytest.approx(10.990e9)
    assert bridge["fp_funding_debt_excluded_usd"] == pytest.approx(33.617e9)
    assert sotp["sotp_equity_value_usd"] == pytest.approx(expected_equity, abs=1.0)
    assert not sotp["financial_products_funding_debt_double_counted"]
    assert abs(sotp["component_identity_error_usd"]) <= 1.0
    assert gate["sotp_component_identity_pass"]


def test_cat_v1_1_is_research_only_and_reverse_dcf_fails_closed(
    cat_v1_1: dict[str, object],
) -> None:
    valuation = cat_v1_1["valuation"]
    sotp = valuation["sotp_valuation"].iloc[0]
    reverse = valuation["sotp_reverse_dcf"].iloc[0]
    comparison = valuation["v1_vs_v1_1_comparison"].iloc[0]
    gate = valuation["industrials_v1_1_gate"].iloc[0]
    assert sotp["sotp_value_per_share"] == pytest.approx(248.62051964, rel=1e-8)
    assert sotp["research_gap_pct"] == pytest.approx(-69.96974124, rel=1e-8)
    assert reverse["reverse_dcf_status"] == "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"
    assert pd.isna(reverse["market_implied_near_term_growth_pct"])
    assert not reverse["boundary_reported_as_solution"]
    assert comparison["v1_gap_interpretation"] == (
        "RETIRED_NOT_INTERPRETABLE_AS_MISPRICING"
    )
    assert not comparison["investment_conclusion_allowed"]
    assert gate["research_audit_complete"]
    assert not gate["terminal_input_allowed"]
    assert not gate["production_promoted"]
    assert gate["live_matched_observations"] == "0/20"
