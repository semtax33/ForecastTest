from __future__ import annotations

import pandas as pd


def build_v172_gate(
    *,
    acquiree_nopat: pd.DataFrame,
    cycle_company_year: pd.DataFrame,
    cohorts: pd.DataFrame,
    v171_gate: pd.DataFrame,
    v161_gate: pd.DataFrame,
) -> pd.DataFrame:
    parent = v171_gate.iloc[0]
    frozen_parent = v161_gate.iloc[0]
    direct_nopat_events = int(acquiree_nopat["acquiree_nopat_directly_disclosed"].sum())
    bridged_nopat_events = int(acquiree_nopat["acquiree_nopat_bridge_ready"].sum())
    direct_or_bridged = int(
        (
            acquiree_nopat["acquiree_nopat_directly_disclosed"]
            | acquiree_nopat["acquiree_nopat_bridge_ready"]
        ).sum()
    )
    cycle_available_tickers = int(
        cycle_company_year.loc[
            cycle_company_year["cycle_normalized_annual_scope_complete"], "ticker"
        ].nunique()
    )
    complete_reported_nopat_cohorts = int(
        cohorts.loc[cohorts["reported_nopat_cohort_complete"], "ticker"].nunique()
    )
    complete_cycle_cohorts = int(
        cohorts.loc[cohorts["cycle_normalized_cohort_complete"], "ticker"].nunique()
    )
    validated_tickers = int(
        cohorts.loc[cohorts["organic_company_roic_validated"], "ticker"].nunique()
    )
    research_conditions = {
        "v1_6_1_frozen_parent_gate_preserved": bool(
            frozen_parent["v1_6_1_research_freeze_eligible"]
        ),
        "v1_7_1_parent_research_gate_preserved": bool(
            parent["v1_7_1_research_gate"]
        ),
        "direct_or_bridged_acquiree_nopat_min_2": direct_or_bridged >= 2,
        "ppa_step_up_min_2_preserved": int(
            parent["purchase_accounting_step_up_proven_events"]
        )
        >= 2,
        "full_mna_bridge_min_2_preserved": int(
            parent["material_mna_fully_bridged_company_years"]
        )
        >= 2,
        "reported_vs_cycle_roic_separated": bool(
            cohorts["reported_vs_cycle_separated"].all()
        ),
        "cycle_normalized_annual_tickers_min_2": cycle_available_tickers >= 2,
        "terminal_replacement_remains_locked": bool(
            frozen_parent["terminal_candidate_ready_tickers"] == 0
        ),
    }
    freeze_conditions = {
        "complete_3y_reported_nopat_cohort_tickers_min_2": (
            complete_reported_nopat_cohorts >= 2
        ),
        "complete_3y_cycle_normalized_cohort_tickers_min_2": complete_cycle_cohorts
        >= 2,
        "validated_organic_roic_tickers_min_2": validated_tickers >= 2,
    }
    research_gate = all(research_conditions.values())
    freeze_eligible = research_gate and all(freeze_conditions.values())
    return pd.DataFrame(
        [
            {
                **research_conditions,
                **freeze_conditions,
                "direct_acquiree_nopat_events": direct_nopat_events,
                "bridged_acquiree_nopat_events": bridged_nopat_events,
                "direct_or_bridged_acquiree_nopat_events": direct_or_bridged,
                "purchase_accounting_step_up_proven_events": int(
                    parent["purchase_accounting_step_up_proven_events"]
                ),
                "material_mna_fully_bridged_company_years": int(
                    parent["material_mna_fully_bridged_company_years"]
                ),
                "complete_3y_cohort_tickers": int(
                    parent["complete_multi_year_roic_cohort_tickers"]
                ),
                "complete_3y_reported_nopat_cohort_tickers": complete_reported_nopat_cohorts,
                "cycle_normalized_annual_tickers": cycle_available_tickers,
                "complete_3y_cycle_normalized_cohort_tickers": complete_cycle_cohorts,
                "validated_organic_roic_tickers": validated_tickers,
                "v1_7_2_research_gate": research_gate,
                "v1_7_2_research_freeze_eligible": freeze_eligible,
                "development_status": (
                    "RESEARCH_GATE_PASSED_FREEZE_DEFERRED"
                    if research_gate and not freeze_eligible
                    else (
                        "RESEARCH_FREEZE_ELIGIBLE"
                        if freeze_eligible
                        else "RESEARCH_GATE_FAILED"
                    )
                ),
                "terminal_anchor_replacement_allowed": False,
                "wacc_recalibrated": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
