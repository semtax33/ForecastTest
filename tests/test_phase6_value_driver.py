from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.phase6.benchmark import (
    verify_revenue_research_benchmark,
)
from energy_nowcast.research.phase6.bridge import load_target_hierarchy


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "phase6_value_driver_research"
CONFIG = ROOT / "configs" / "phase6_value_driver_research.toml"


def test_phase5_revenue_research_is_frozen_and_verifies() -> None:
    manifest = verify_revenue_research_benchmark(ROOT)
    assert manifest["version"] == "PHASE5_REVENUE_RESEARCH_FREEZE_V1"
    assert manifest["immutable"] is True
    assert manifest["verified_files"] == 10
    assert manifest["production_champion"] == "V3.4_FROZEN"
    assert manifest["live_model_change_matches"] == "0/20"


def test_anchor_hierarchy_forbids_fixed_ratio_reverse_calculation() -> None:
    hierarchy = load_target_hierarchy(CONFIG)
    assert set(hierarchy["subindustry"]) == {
        "E&P", "Refining", "Midstream", "Services", "Integrated"
    }
    assert hierarchy["architecture"].eq("ANCHOR_TO_CONDITIONAL_BRIDGE").all()
    assert (~hierarchy["fixed_ratio_reverse_calculation_allowed"]).all()
    assert hierarchy["scenario_bridge_required"].all()
    assert hierarchy["production_eligible"].eq(False).all()  # noqa: E712


def test_integrated_parser_gold_and_segment_routes() -> None:
    gold = pd.read_csv(OUTPUT / "integrated_segment_gold_audit_summary.csv").iloc[0]
    assert gold["gold_rows"] == 20
    assert gold["all_dimension_accuracy"] == 1.0
    assert bool(gold["parser_quality_gate"])

    decisions = pd.read_csv(OUTPUT / "target_research_decisions.csv")
    integrated = decisions.loc[decisions["subindustry"].eq("Integrated")]
    passed = integrated.loc[integrated["research_gate"], "scope"].tolist()
    assert passed == ["DOWNSTREAM"]
    failed_routes = integrated.loc[~integrated["research_gate"], "selected_research_route"]
    assert failed_routes.eq("PRIOR_YEAR_ZERO_CHANGE_BASELINE").all()


def test_integrated_segment_performance_is_reproducible() -> None:
    downstream = pd.read_csv(OUTPUT / "integrated_downstream_summary.csv")
    downstream = downstream.loc[
        downstream["validation"].eq("TIME_HOLDOUT_8Q_PRIMARY")
    ].iloc[0]
    upstream = pd.read_csv(OUTPUT / "integrated_upstream_summary.csv")
    upstream = upstream.loc[
        upstream["validation"].eq("TIME_HOLDOUT_8Q_PRIMARY")
    ].iloc[0]
    assert abs(downstream["median_entity_mase"] - 0.7798376952825736) < 1e-10
    assert abs(downstream["mean_target_level_mae"] - 1.3783780607472051) < 1e-10
    assert upstream["median_entity_mase"] > 3.6


def test_conditional_bridges_are_pit_scenarios_with_error_attribution() -> None:
    midstream = pd.read_csv(OUTPUT / "midstream_ebitda_to_revenue_bridge.csv")
    assert (~midstream["fixed_margin_used"]).all()
    available = midstream.loc[midstream["bridge_status"].eq("AVAILABLE")]
    assert len(available) == 32
    assert (
        available["revenue_scenario_low_usd"]
        <= available["revenue_scenario_base_usd"]
    ).all()
    assert (
        available["revenue_scenario_base_usd"]
        <= available["revenue_scenario_high_usd"]
    ).all()
    evaluable = available.loc[available["attribution_status"].eq("EVALUABLE")]
    assert len(evaluable) == 28
    for column in (
        "anchor_only_revenue_error_usd", "bridge_only_revenue_error_usd",
        "total_revenue_error_usd", "interaction_error_usd",
    ):
        assert evaluable[column].notna().all()
    assert (
        available["history_last_quarter"].map(lambda value: pd.Period(value, freq="Q"))
        < available["quarter"].map(lambda value: pd.Period(value, freq="Q"))
    ).all()

    integrated = pd.read_csv(OUTPUT / "integrated_consolidated_earnings_bridge.csv")
    assert (~integrated["fixed_ratio_used"]).all()
    assert integrated["anchor_error_pct"].notna().all()
    assert integrated["bridge_error_pct"].notna().all()
    assert integrated["total_error_pct"].notna().all()


def test_new_financial_targets_fail_closed_without_full_evidence() -> None:
    decisions = pd.read_csv(OUTPUT / "target_research_decisions.csv")
    non_integrated = decisions.loc[~decisions["subindustry"].eq("Integrated")]
    assert (~non_integrated["research_gate"]).all()
    assert non_integrated["selected_research_route"].eq(
        "PRIOR_YEAR_ZERO_CHANGE_BASELINE"
    ).all()
    assert (~decisions["production_eligible"]).all()


def test_common_target_schema_and_consensus_tracking() -> None:
    common = pd.read_csv(OUTPUT / "phase6_common_target_forecasts.csv")
    assert {
        "GAAP_REVENUE", "ADJUSTED_EBITDA_NON_GAAP",
        "SEGMENT_EARNINGS_CONTRIBUTION_MARGIN_PCT",
        "CONSOLIDATED_OPERATING_MARGIN_PCT", "CASH_CAPEX",
    }.issubset(set(common["forecast_target"]))
    assert "target_component" in common
    assert not common.duplicated(
        ["ticker", "quarter", "forecast_target", "target_component", "validation"]
    ).any()

    consensus = pd.read_csv(OUTPUT / "model_vs_consensus_summary.csv").iloc[0]
    assert consensus["status"] == "NO_MATCHED_OBSERVATIONS"
    assert consensus["observations"] == 0
    finnworlds = pd.read_csv(
        OUTPUT / "analyst_consensus_finnworlds_coverage.csv"
    )
    assert finnworlds["revenue_consensus_available"].eq(False).all()  # noqa: E712


def test_phase6_does_not_change_production_or_revenue_freeze() -> None:
    metadata = json.loads((OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["production_champion_changed"] is False
    assert metadata["live_matched_observations"] == "0/20"
    assert metadata["integrated_consolidated_revenue_improvement_allowed"] is False
    assert metadata["fixed_ratio_reverse_calculation_used"] is False
    assert metadata["integrated_passed_segments"] == ["downstream"]
    verify_revenue_research_benchmark(ROOT)
