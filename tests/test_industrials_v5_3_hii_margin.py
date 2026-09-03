from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_hii_v52_valuation,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v521 import (
    verify_hii_v521_consensus,
)


OUTPUT = PROJECT_ROOT / "output/industrials_v5_3_hii_through_cycle_margin_research"


def test_v53_uses_full_html_and_ir_history_with_verified_sources() -> None:
    coverage = pd.read_csv(OUTPUT / "hii_v53_source_coverage.csv").set_index("layer")
    assert int(coverage.loc["SEC_10K_HTML", "source_count"]) == 7
    assert int(coverage.loc["SEC_10Q_HTML", "source_count"]) == 20
    assert int(coverage.loc["IR_HTML_DERIVED_HISTORY", "source_count"]) == 27
    assert int(coverage.loc["BLS_AS_RELEASED_VINTAGE", "source_count"]) == 3
    assert coverage["source_hash_verified"].all()
    assert not coverage["pdf_parsing_used"].any()


def test_contract_mix_catchup_fas_cas_and_backlog_identities() -> None:
    contract = pd.read_csv(OUTPUT / "hii_contract_type_mix_history.csv")
    assert len(contract) == 128
    totals = contract.groupby(["period", "segment"])["contract_mix_pct"].sum()
    assert np.allclose(totals, 100.0, atol=1e-9)
    latest = contract.loc[contract["period"].eq("2026Q2")]
    ingalls_fixed = latest.loc[
        latest["segment"].eq("ingalls_shipbuilding")
        & latest["fixed_price_risk_channel"],
        "contract_mix_pct",
    ].sum()
    mission_cost = latest.loc[
        latest["segment"].eq("mission_technologies")
        & latest["contract_type"].eq("cost_type"),
        "contract_mix_pct",
    ].iloc[0]
    assert ingalls_fixed == pytest.approx(85.6465, abs=1e-3)
    assert mission_cost == pytest.approx(80.5785, abs=1e-3)

    annual_catchup = pd.read_csv(OUTPUT / "hii_annual_cumulative_catchup_history.csv")
    quarterly_catchup = pd.read_csv(OUTPUT / "hii_quarterly_cumulative_catchup_history.csv")
    fas_cas = pd.read_csv(OUTPUT / "hii_fas_cas_reconciliation_history.csv")
    backlog = pd.read_csv(OUTPUT / "hii_latest_segment_backlog_coverage.csv")
    assert len(annual_catchup) == 7 and len(quarterly_catchup) == 26
    assert annual_catchup["gross_to_net_identity_error_usd"].le(1.0).all()
    assert fas_cas["reconciliation_identity_error_usd"].le(1.0).all()
    assert backlog["backlog_identity_error_usd"].le(1.0).all()
    assert backlog["total_backlog_usd"].sum() == pytest.approx(57_322_000_000.0)


def test_catchup_neutral_segment_and_company_margin_distributions_are_explicit() -> None:
    distribution = pd.read_csv(OUTPUT / "hii_margin_distribution.csv")
    normalized = distribution.loc[distribution["basis"].eq("CATCHUP_NEUTRAL_TTM")]
    assert set(normalized["entity"]) == {
        "consolidated",
        "ingalls_shipbuilding",
        "newport_news_shipbuilding",
        "mission_technologies",
    }
    consolidated = normalized.loc[normalized["entity"].eq("consolidated")].iloc[0]
    assert int(consolidated["observations"]) == 23
    assert float(consolidated["median_pct"]) == pytest.approx(5.685131, abs=1e-5)
    assert float(consolidated["q90_pct"]) == pytest.approx(6.791324, abs=1e-5)
    segment_normalized = pd.read_csv(
        OUTPUT / "hii_segment_catchup_neutral_ttm_history.csv"
    )
    assert segment_normalized.groupby("segment").size().eq(11).all()


def test_terminal_margin_feasibility_and_dcf_crosscheck_fail_closed() -> None:
    feasibility = pd.read_csv(OUTPUT / "hii_terminal_margin_feasibility.csv").set_index(
        "terminal_margin_hypothesis_pct"
    )
    assert feasibility.loc[8.0, "economic_support_status"] == (
        "ACCOUNTING_OBSERVED_BUT_NOT_NORMALIZED_BASE_RATE"
    )
    assert feasibility.loc[10.0, "economic_support_status"] == (
        "NONCONTEMPORANEOUS_COMPONENT_EXTREMES_ONLY"
    )
    assert feasibility.loc[12.0, "economic_support_status"] == (
        "OUTSIDE_OBSERVED_COMPONENT_DOMAIN"
    )
    assert not feasibility["terminal_input_allowed"].any()

    crosscheck = pd.read_csv(OUTPUT / "hii_margin_dcf_reverse_crosscheck.csv").set_index(
        "terminal_margin_pct"
    )
    assert crosscheck.loc[12.0, "market_implied_wacc_pct"] == pytest.approx(
        8.46191, abs=1e-4
    )
    assert crosscheck.loc[8.0, "market_implied_wacc_pct"] == pytest.approx(
        6.56604, abs=1e-4
    )
    assert crosscheck["conditional_only"].all()
    assert not crosscheck["fair_value_claim_allowed"].any()
    assert not crosscheck["terminal_input_allowed"].any()


def test_industry_signal_and_consensus_semantics_remain_diagnostic() -> None:
    industry = pd.read_csv(OUTPUT / "hii_industry_cost_recovery_diagnostic.csv")
    assert industry["price_less_cost_proxy_yoy_pp"].lt(0).all()
    assert not industry["dedicated_shipbuilding_output_series_available"].any()
    assert not industry["terminal_margin_point_input_allowed"].any()

    correction = pd.read_csv(OUTPUT / "hii_immutable_correction_record.csv")
    semantics = pd.read_csv(OUTPUT / "hii_consensus_semantics_corrected_summary.csv").iloc[0]
    target = correction.loc[
        correction["correction_id"].eq("HII_V521_TARGET_SEMANTICS_001")
    ].iloc[0]
    assert target["superseded_field"] == "analyst_average_target_median"
    assert target["replacement_field"] == "provider_average_target_median"
    assert float(semantics["provider_average_target_median"]) == pytest.approx(
        361.7954545455
    )
    assert bool(semantics["analyst_counts_may_overlap"])
    assert not bool(semantics["analyst_counts_can_be_summed"])
    assert pd.isna(semantics["independent_analyst_count"])
    verify_hii_v52_valuation(PROJECT_ROOT)
    verify_hii_v521_consensus(PROJECT_ROOT)


def test_v53_gate_denies_fair_value_terminal_and_production_authority() -> None:
    gate = pd.read_csv(OUTPUT / "hii_v53_gate.csv").iloc[0]
    assert gate["research_freeze_eligible"]
    assert gate["frozen_parents_unchanged"]
    assert gate["ir_source_hashes_verified"]
    assert not gate["fair_value_claim_allowed"]
    assert not gate["terminal_input_allowed"]
    assert not gate["production_promoted"]
    assert gate["live_forward_matched_observations"] == "0/20"
