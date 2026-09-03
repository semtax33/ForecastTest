from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v110 import (
    build_cost_component_evidence,
    build_project_to_company_waterfall,
    build_v110_gate,
)


ROOT = Path(__file__).resolve().parents[1]


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    reserve = pd.read_csv(
        ROOT / "output/energy_valuation_v1_5_research/reserve_roic_scope_cross_check.csv"
    )
    company = pd.read_csv(
        ROOT / "output/energy_valuation_v1_9_research/expanded_company_organic_roic_ranges.csv"
    )
    costs = pd.read_csv(
        ROOT / "output/energy_valuation_v1_5_research/annual_all_in_reserve_cost.csv"
    )
    return reserve, company, costs


def test_ar_waterfall_reconciles_without_arbitrary_driver_allocation() -> None:
    reserve, company, costs = _inputs()
    steps, summary = build_project_to_company_waterfall(reserve, company)
    evidence = build_cost_component_evidence(costs, set(summary["ticker"]))
    ar = summary.loc[summary["ticker"].eq("AR")].iloc[0]
    assert ar["waterfall_identity_pass"]
    assert abs(ar["waterfall_identity_error_pct_points"]) <= 1e-10
    assert ar["company_scope_driver_closure"] is False or not ar["company_scope_driver_closure"]
    assert not evidence["roic_effect_allocated"].any()
    assert len(steps.loc[steps["ticker"].eq("AR")]) == 3


def test_v110_completes_explanation_but_keeps_terminal_locked() -> None:
    reserve, company, costs = _inputs()
    _, summary = build_project_to_company_waterfall(reserve, company)
    evidence = build_cost_component_evidence(costs, set(summary["ticker"]))
    gate = build_v110_gate(
        parent_v19_verified=True,
        waterfall_summary=summary,
        driver_evidence=evidence,
    ).iloc[0]
    assert gate["v1_10_research_complete"]
    assert not gate["v1_10_freeze_eligible"]
    assert not gate["terminal_anchor_replacement_allowed"]
    assert not gate["production_promoted"]
