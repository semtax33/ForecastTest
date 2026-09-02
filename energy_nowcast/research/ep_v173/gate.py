from __future__ import annotations

import pandas as pd


def build_v173_gate(
    *,
    triangulation: pd.DataFrame,
    annual_attribution: pd.DataFrame,
    cohorts: pd.DataFrame,
    validation: pd.DataFrame,
    v172_gate: pd.DataFrame,
) -> pd.DataFrame:
    parent = v172_gate.iloc[0]
    mature = cohorts.loc[cohorts["cohort_offset"].eq(2)]
    bridge_count = int(triangulation["evidence_backed_nopat_bridge"].sum())
    triangulated_count = int(triangulation["two_route_nopat_triangulated"].sum())
    positive_triangulated_count = int(
        triangulation["triangulation_economic_run_rate_positive"].sum()
    )
    attribution_tickers = int(
        annual_attribution.loc[
            annual_attribution["normalization_attribution_annual_complete"]
        ]["ticker"].nunique()
    )
    independent_cohorts = int(
        mature["independent_cost_normalized_cohort_complete"].sum()
    )
    complete_reported = int(mature["reported_cohort_complete"].sum())
    complete_cycle = int(
        mature["full_cycle_normalized_cohort_complete"].sum()
    )
    validated = int(validation["organic_company_roic_validated"].sum())
    parent_preserved = bool(parent["v1_7_2_research_gate"])
    research_gate = bool(
        parent_preserved
        and bridge_count >= 3
        and triangulated_count >= 2
        and attribution_tickers >= 2
        and independent_cohorts >= 2
    )
    freeze_eligible = bool(
        research_gate
        and complete_reported >= 2
        and complete_cycle >= 2
        and validated >= 2
    )
    return pd.DataFrame(
        [
            {
                "v1_7_2_parent_research_gate_preserved": parent_preserved,
                "evidence_backed_nopat_bridge_min_3": bridge_count >= 3,
                "nopat_two_route_triangulation_min_2": triangulated_count >= 2,
                "normalization_attribution_min_2_tickers": attribution_tickers >= 2,
                "independent_cost_normalized_cohort_min_2": independent_cohorts >= 2,
                "complete_3y_reported_cohort_min_2": complete_reported >= 2,
                "complete_3y_cycle_normalized_cohort_min_2": complete_cycle >= 2,
                "validated_organic_roic_min_2": validated >= 2,
                "terminal_replacement_remains_locked": True,
                "evidence_backed_nopat_bridge_deals": bridge_count,
                "two_route_nopat_triangulated_deals": triangulated_count,
                "positive_two_route_nopat_deals": positive_triangulated_count,
                "normalization_attribution_tickers": attribution_tickers,
                "independent_cost_normalized_cohort_tickers": independent_cohorts,
                "complete_3y_reported_cohort_tickers": complete_reported,
                "complete_3y_cycle_normalized_cohort_tickers": complete_cycle,
                "validated_organic_roic_tickers": validated,
                "v1_7_3_research_gate": research_gate,
                "v1_7_3_research_freeze_eligible": freeze_eligible,
                "development_status": (
                    "RESEARCH_GATE_PASSED_FREEZE_ELIGIBLE"
                    if freeze_eligible
                    else "RESEARCH_GATE_PASSED_FREEZE_DEFERRED"
                    if research_gate
                    else "RESEARCH_GATE_FAILED"
                ),
                "terminal_anchor_replacement_allowed": False,
                "wacc_recalibrated": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
