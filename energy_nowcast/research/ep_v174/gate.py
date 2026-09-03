from __future__ import annotations

import pandas as pd


def build_v174_gate(
    *,
    parent_gate: pd.DataFrame,
    closed_cohorts: pd.DataFrame,
    validation: pd.DataFrame,
    adjusted_triangulation: pd.DataFrame,
) -> pd.DataFrame:
    parent = parent_gate.iloc[0]
    mature = closed_cohorts.loc[closed_cohorts["cohort_offset"].eq(2)]
    complete_reported = int(mature["v174_reported_3y_cohort_complete"].sum())
    complete_full_cycle = int(
        mature["v174_independent_full_cycle_3y_cohort_complete"].sum()
    )
    validated_tickers = int(validation["organic_company_roic_validated"].sum())
    candidate_routes = adjusted_triangulation.loc[
        adjusted_triangulation["validated_cohort_candidate"]
    ]
    triangulated_candidates = int(
        candidate_routes.loc[
            candidate_routes["v1_7_4_scope_adjusted_two_route_triangulated"],
            "ticker",
        ].nunique()
    )
    unresolved_material = int(
        (~mature["material_transaction_perimeter_resolved"]).sum()
    )
    parent_preserved = bool(parent["v1_7_3_research_gate"])
    freeze_eligible = bool(
        parent_preserved
        and complete_reported >= 2
        and complete_full_cycle >= 2
        and triangulated_candidates >= 2
        and validated_tickers >= 2
        and unresolved_material == 0
    )
    return pd.DataFrame(
        [
            {
                "v1_7_3_parent_research_gate_preserved": parent_preserved,
                "complete_reported_3y_cohorts_min_2": complete_reported >= 2,
                "complete_independent_full_cycle_cohorts_min_2": complete_full_cycle
                >= 2,
                "triangulated_nopat_validated_cohort_tickers_min_2": triangulated_candidates
                >= 2,
                "validated_organic_roic_tickers_min_2": validated_tickers >= 2,
                "no_unresolved_material_transaction_perimeter": unresolved_material
                == 0,
                "terminal_replacement_remains_locked": True,
                "complete_reported_3y_cohort_tickers": complete_reported,
                "complete_independent_full_cycle_cohort_tickers": complete_full_cycle,
                "triangulated_nopat_validated_cohort_tickers": triangulated_candidates,
                "validated_organic_roic_tickers": validated_tickers,
                "unresolved_material_transaction_perimeters": unresolved_material,
                "v1_7_4_research_freeze_eligible": freeze_eligible,
                "development_status": (
                    "RESEARCH_GATE_PASSED_FREEZE_ELIGIBLE"
                    if freeze_eligible
                    else "RESEARCH_GATE_FAILED_FREEZE_DEFERRED"
                ),
                "terminal_anchor_replacement_allowed": False,
                "wacc_recalibrated": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
