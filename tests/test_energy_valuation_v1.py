from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.valuation.benchmark import verify_v1


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "energy_valuation_v1"


def test_v1_completion_states_are_separate_and_fail_closed_for_production() -> None:
    status = pd.read_csv(OUTPUT / "v1_completion_status.csv").set_index(
        "status_dimension"
    )
    assert status.loc["V1_CODE", "status"] == "COMPLETE"
    assert bool(status.loc["V1_CODE", "passed"])
    assert status.loc["V1_RESEARCH", "status"] == "COMPLETE"
    assert bool(status.loc["V1_RESEARCH", "passed"])
    assert status.loc["V1_PRODUCTION", "status"] == "NOT_PROMOTED_LIVE_0_OF_20"
    assert not bool(status.loc["V1_PRODUCTION", "passed"])

    audit = pd.read_csv(OUTPUT / "v1_requirement_audit.csv")
    assert audit["passed"].all()


def test_every_subindustry_has_a_complete_anchor_to_fcff_roic_bridge() -> None:
    quarterly = pd.read_parquet(OUTPUT / "quarterly_financial_bridge.parquet")
    latest = pd.read_csv(OUTPUT / "latest_financial_bridge.csv")
    coverage = pd.read_csv(OUTPUT / "source_coverage.csv")

    assert latest["ticker"].nunique() == 26
    assert set(latest["subindustry"]) == {
        "ep", "integrated", "refining", "midstream", "services"
    }
    assert coverage["complete_quarterly_rows"].ge(8).all()
    assert ~coverage["source_status"].str.startswith("INSUFFICIENT").any()
    assert coverage.loc[
        coverage["ticker"].isin(["SM", "VLO"]), "conditional_capex_rows"
    ].gt(0).all()

    complete = quarterly.loc[quarterly["valuation_source_complete"]]
    assert np.allclose(
        complete["nopat_usd"] - complete["reinvestment_usd"],
        complete["fcff_usd"],
        rtol=1e-12,
        atol=1e-3,
    )
    assert complete["primary_anchor"].notna().all()
    assert complete["anchor_route"].notna().all()
    assert complete["invested_capital_usd"].gt(0).all()


def test_bear_base_bull_engine_uses_distributions_not_fixed_ratios() -> None:
    assumptions = pd.read_csv(OUTPUT / "scenario_assumptions.csv")
    assert len(assumptions) == 26 * 3
    assert set(assumptions["scenario"]) == {"BEAR", "BASE", "BULL"}
    assert set(assumptions["probability_class"]).issubset(
        {"POSSIBLE", "PLAUSIBLE", "PROBABLE"}
    )
    assert assumptions["assumption_validation"].eq("PASS").all()
    assert assumptions["minimum_history_pass"].all()
    assert assumptions["historical_observations"].ge(8).all()
    assert (~assumptions["fixed_ratio_used"]).all()
    assert np.allclose(
        assumptions.groupby("ticker")["probability"].sum().to_numpy(), 1.0
    )
    for column in (
        "growth_pct", "operating_margin_pct", "reinvestment_rate_pct",
        "roic_pct", "wacc_pct", "terminal_growth_pct",
    ):
        assert assumptions[column].notna().all()


def test_forward_and_reverse_dcf_are_complete_and_reconcile() -> None:
    projections = pd.read_csv(OUTPUT / "dcf_projections.csv")
    scenarios = pd.read_csv(OUTPUT / "forward_dcf_scenario_values.csv")
    weighted = pd.read_csv(OUTPUT / "forward_dcf_probability_weighted.csv")
    reverse = pd.read_csv(OUTPUT / "reverse_dcf_expectations.csv")
    gap = pd.read_csv(OUTPUT / "expectations_gap.csv")

    assert len(projections) == 26 * 3 * 5
    assert np.allclose(
        projections["nopat_usd"] - projections["reinvestment_usd"],
        projections["fcff_usd"],
        rtol=1e-12,
        atol=1e-3,
    )
    assert len(scenarios) == 26 * 3
    assert len(weighted) == len(reverse) == len(gap) == 26
    assert np.isfinite(weighted["probability_weighted_fair_value"]).all()
    implied = [
        "market_implied_growth_pct", "market_implied_operating_margin_pct",
        "market_implied_roic_pct",
        "market_implied_competitive_advantage_period_years",
    ]
    assert reverse[implied].notna().all().all()
    assert reverse["reverse_dcf_method"].eq(
        "ONE_VARIABLE_AT_A_TIME_GRID_HOLDING_BASE_ASSUMPTIONS"
    ).all()
    assert (~reverse["production_eligible"]).all()


def test_market_inputs_are_current_and_explicit_about_two_price_fallbacks() -> None:
    coverage = pd.read_csv(OUTPUT / "market_input_coverage.csv")
    assert len(coverage) == 26
    assert coverage["market_input_complete"].all()
    assert coverage["price_freshness_status"].eq("CURRENT_WITHIN_LIMIT").all()
    overrides = set(coverage.loc[coverage["price_override_used"], "ticker"])
    assert overrides == {"OVV", "ET"}
    assert coverage.loc[
        coverage["price_override_used"], "beta_method"
    ].eq("CONSERVATIVE_BETA_1P0_INSUFFICIENT_LOCAL_HISTORY").all()


def test_metadata_and_revenue_freeze_boundary() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["v1_code_complete"] is True
    assert metadata["v1_research_complete"] is True
    assert metadata["v1_production_promoted"] is False
    assert metadata["live_matched_observations"] == "0/20"
    assert metadata["fixed_ratio_reverse_calculation_used"] is False
    assert metadata["ticker_count"] == 26
    assert metadata["subindustry_count"] == 5
    assert metadata["scenario_count"] == 3


def test_energy_v1_frozen_manifest_verifies() -> None:
    manifest = verify_v1(ROOT)
    assert manifest["immutable"] is True
    assert manifest["code_complete"] is True
    assert manifest["research_complete"] is True
    assert manifest["production_promoted"] is False
    assert manifest["live_matched_observations"] == "0/20"
