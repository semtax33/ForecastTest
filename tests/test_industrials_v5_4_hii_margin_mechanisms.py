from __future__ import annotations

import pandas as pd
import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_hii_v52_valuation,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v53 import (
    verify_hii_v53_margin_research,
)


OUTPUT = PROJECT_ROOT / "output/industrials_v5_4_hii_margin_mechanism_research"


def test_v54_uses_complete_html_ir_and_industry_lineage() -> None:
    coverage = pd.read_csv(OUTPUT / "hii_v54_source_coverage.csv").set_index("layer")
    assert int(coverage.loc["SEC_10K_HTML", "source_count"]) == 7
    assert int(coverage.loc["SEC_10Q_HTML", "source_count"]) == 20
    assert int(coverage.loc["ARCANA_IR_HTML", "source_count"]) == 18
    assert int(coverage.loc["ARCANA_IR_HTML_ACTUALS", "source_count"]) == 27
    assert int(coverage.loc["BLS_CES_CURRENT_REVISED", "source_count"]) == 4
    assert coverage["all_lineage_hashes_verified"].all()
    assert not coverage["pdf_parsing_used"].any()

    lineage = pd.read_csv(OUTPUT / "hii_source_lineage_hash_audit.csv")
    assert len(lineage) == 55
    assert lineage["source_exists"].all()
    assert lineage["hash_match"].all()


def test_guidance_vintages_realization_and_2024_execution_shock() -> None:
    vintages = pd.read_csv(OUTPUT / "hii_guidance_vintage_history.csv")
    realization = pd.read_csv(OUTPUT / "hii_guidance_realization_audit.csv").set_index(
        "forecast_year"
    )
    shocks = pd.read_csv(OUTPUT / "hii_material_guidance_shocks.csv")

    assert len(vintages) == 18
    assert int(realization["realized"].sum()) == 4
    assert realization.loc[2024, "realized_shipbuilding_margin_pct"] == pytest.approx(
        5.231227, abs=1e-5
    )
    assert realization.loc[
        2024, "first_shipbuilding_margin_midpoint_pct"
    ] == pytest.approx(7.7)
    assert realization.loc[
        2024, "last_shipbuilding_margin_midpoint_pct"
    ] == pytest.approx(5.5)
    assert len(shocks) == 1
    assert shocks.iloc[0]["forecast_origin_period"] == "2024Q3"
    assert shocks.iloc[0]["revision_shipbuilding_margin_midpoint_pct"] == pytest.approx(
        -2.2
    )
    assert shocks.iloc[0]["revision_free_cash_flow_midpoint_usd"] == pytest.approx(
        -600_000_000.0
    )
    assert not shocks["structural_margin_upgrade_evidence"].any()


def test_contract_behavior_recovers_catchup_effect_but_not_vintage_margin() -> None:
    behavior = pd.read_csv(OUTPUT / "hii_contract_catchup_behavior.csv")
    coverage = pd.read_csv(OUTPUT / "hii_contract_vintage_identifiability.csv").set_index(
        "field"
    )
    recovery = pd.read_csv(OUTPUT / "hii_cost_recovery_mechanism_evidence.csv")

    assert len(behavior) == 9
    newport_2024 = behavior.loc[
        behavior["period"].eq(2024)
        & behavior["segment"].eq("newport_news_shipbuilding")
    ].iloc[0]
    assert newport_2024["net_cumulative_catchup_adjustment_usd"] == pytest.approx(
        -154_000_000.0
    )
    assert newport_2024["reported_margin_pct"] == pytest.approx(4.121293, abs=1e-5)
    assert newport_2024["catchup_neutral_margin_pct"] == pytest.approx(
        6.701290, abs=1e-5
    )
    assert not bool(coverage.loc["CONTRACT_VINTAGE_MARGIN", "identified"])
    assert not bool(coverage.loc["DIRECT_LABOR_HOURS_AND_VARIANCE", "identified"])
    assert not bool(coverage.loc["PRICE_RESET_AMOUNT", "identified"])
    assert set(recovery["mechanism"]) == {
        "FIRM_FIXED_PRICE",
        "FIXED_PRICE_INCENTIVE",
        "COST_TYPE",
        "TIME_AND_MATERIALS",
        "ESCALATION_PROVISION",
    }
    assert not recovery["terminal_margin_point_input_allowed"].any()


def test_workforce_and_bls_are_context_not_direct_pit_productivity() -> None:
    workforce = pd.read_csv(OUTPUT / "hii_workforce_productivity_proxy.csv")
    history = pd.read_csv(OUTPUT / "hii_bls_labor_history.csv")
    summary = pd.read_csv(OUTPUT / "hii_bls_labor_summary.csv").set_index("series_id")

    assert len(workforce) == 7
    assert not workforce["labor_hour_productivity_claim_allowed"].any()
    assert len(history) == 360
    assert history["reference_period"].max() == "2026M06"
    assert not history["pit_model_input_allowed"].any()
    assert summary.loc["CES3133600003", "year_over_year_pct"] == pytest.approx(
        4.53897, abs=1e-4
    )
    assert summary.iloc[0]["composite_labor_input_cost_proxy_yoy_pct"] == pytest.approx(
        5.61646, abs=1e-4
    )


def test_nonsegment_and_mission_normalization_remain_fail_closed() -> None:
    nonsegment = pd.read_csv(
        OUTPUT / "hii_nonsegment_normalization_summary.csv"
    ).set_index("reference")
    mission = pd.read_csv(OUTPUT / "hii_mission_margin_ceiling.csv").iloc[0]

    assert nonsegment.loc["TTM_CURRENT", "nonsegment_contribution_pct"] == pytest.approx(
        -0.546, abs=1e-3
    )
    assert nonsegment.loc[
        "TTM_HISTORICAL_MEDIAN", "nonsegment_contribution_pct"
    ] == pytest.approx(-0.535, abs=1e-3)
    assert nonsegment.loc["FY26_GUIDANCE", "nonsegment_contribution_pct"] == pytest.approx(
        -0.483, abs=1e-3
    )
    assert mission["fy26_guided_operating_margin_pct"] == 5.0
    assert mission["historical_max_operating_margin_pct"] == pytest.approx(
        4.59352, abs=1e-4
    )
    assert not bool(mission["sustainable_operating_margin_ceiling_identified"])
    assert not nonsegment["terminal_input_allowed"].any()


def test_contemporaneous_reconstruction_rejects_eight_to_ten_percent_base() -> None:
    panel = pd.read_csv(OUTPUT / "hii_contemporaneous_margin_panel.csv")
    requirements = pd.read_csv(
        OUTPUT / "hii_operational_margin_requirements.csv"
    ).set_index("target_consolidated_margin_pct")

    assert len(panel) == 11
    assert panel["all_components_are_same_ttm_window"].all()
    assert panel["fy26_mix_reweighted_consolidated_margin_pct"].max() == pytest.approx(
        6.163492, abs=1e-5
    )
    assert not panel["fy26_mix_reweighted_consolidated_margin_pct"].ge(8.0).any()
    assert requirements.loc[8.0, "required_shipbuilding_margin_pct"] == pytest.approx(
        9.40777, abs=1e-4
    )
    assert requirements.loc[
        8.0, "required_shipbuilding_gap_vs_normalized_max_pp"
    ] == pytest.approx(2.07421, abs=1e-4)
    assert requirements.loc[10.0, "required_shipbuilding_margin_pct"] == pytest.approx(
        11.9806, abs=1e-4
    )
    assert requirements["observed_contemporaneous_periods_at_or_above_target"].eq(0).all()
    assert not requirements["operational_mechanism_proven"].any()


def test_dcf_reverse_dcf_is_conditional_and_does_not_upgrade_authority() -> None:
    crosscheck = pd.read_csv(
        OUTPUT / "hii_operational_margin_valuation_crosscheck.csv"
    ).set_index("terminal_margin_pct")

    assert crosscheck.loc[12.0, "market_implied_wacc_pct"] == pytest.approx(
        8.46191, abs=1e-4
    )
    assert bool(crosscheck.loc[12.0, "implied_wacc_inside_independent_range"])
    assert crosscheck.loc[8.0, "conditional_value_at_independent_midpoint_wacc_per_share"] == pytest.approx(
        205.36, abs=0.02
    )
    assert crosscheck.loc[10.0, "conditional_value_at_independent_midpoint_wacc_per_share"] == pytest.approx(
        269.23, abs=0.02
    )
    assert crosscheck.loc[12.0, "conditional_value_at_independent_midpoint_wacc_per_share"] == pytest.approx(
        333.11, abs=0.02
    )
    assert crosscheck["high_terminal_dependence"].all()
    assert not crosscheck["valuation_upgrade_allowed"].any()
    assert not crosscheck["fair_value_claim_allowed"].any()
    assert not crosscheck["terminal_input_allowed"].any()


def test_v54_gate_freezes_research_and_preserves_parent_authorities() -> None:
    scorecard = pd.read_csv(OUTPUT / "hii_margin_mechanism_scorecard.csv")
    gate = pd.read_csv(OUTPUT / "hii_v54_gate.csv").iloc[0]

    assert len(scorecard) == 8
    assert int(scorecard["supports_8_to_10_pct"].sum()) == 0
    for column in (
        "all_10k_available",
        "all_10q_available",
        "all_ir_hashes_verified",
        "guidance_vintage_coverage_complete",
        "bls_series_complete",
        "bls_cutoff_enforced",
        "all_lineage_hashes_verified",
        "dcf_reverse_crosscheck_run",
        "frozen_parents_unchanged",
        "research_freeze_eligible",
    ):
        assert bool(gate[column])
    for column in (
        "contract_vintage_margin_identified",
        "direct_labor_hours_identified",
        "price_reset_lag_identified",
        "contemporaneous_eight_pct_observed",
        "operational_mechanism_for_structural_eight_to_ten_proven",
        "valuation_upgrade_allowed",
        "fair_value_claim_allowed",
        "terminal_input_allowed",
        "production_promoted",
    ):
        assert not bool(gate[column])
    verify_hii_v52_valuation(PROJECT_ROOT)
    verify_hii_v53_margin_research(PROJECT_ROOT)
