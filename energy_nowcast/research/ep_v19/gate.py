from __future__ import annotations

import pandas as pd


def build_v19_gate(
    *,
    parent_v18_verified: bool,
    candidate_audit: pd.DataFrame,
    rrc_cohort: pd.DataFrame,
    company_ranges: pd.DataFrame,
    distribution: pd.DataFrame,
    loco: pd.DataFrame,
    width_attribution: pd.DataFrame,
) -> pd.DataFrame:
    selected = candidate_audit.loc[candidate_audit["selected_for_v19"]]
    mature = rrc_cohort.loc[rrc_cohort["cohort_offset"].eq(2)]
    outcome_blind = bool(
        not candidate_audit["outcome_values_used_for_selection"].any()
    )
    fourth_validated = bool(
        len(selected) == 1
        and len(mature) == 1
        and mature.iloc[0]["organic_company_roic_validated"]
    )
    width_passes = int(company_ranges["range_width_gate_pass"].sum())
    loco_complete = len(loco) == len(company_ranges)
    max_loco = float(loco["abs_p50_shift_pct_points"].max())
    loco_stable = bool(loco_complete and max_loco <= 10.0)
    attribution_complete = bool(
        set(width_attribution["ticker"]) == {"DVN", "FANG"}
        and width_attribution["range_width_attribution_complete"].all()
        and width_attribution[
            "range_width_attribution_identity_error_pct"
        ].abs().le(1e-9).all()
    )
    research_gate = bool(
        parent_v18_verified
        and outcome_blind
        and fourth_validated
        and len(company_ranges) == 4
        and company_ranges["group"].nunique() == 3
        and attribution_complete
        and loco_complete
    )
    freeze_eligible = bool(
        research_gate and width_passes >= 2 and loco_stable
    )
    return pd.DataFrame(
        [
            {
                "v1_8_parent_snapshot_verified": parent_v18_verified,
                "outcome_blind_fourth_cohort_selection": outcome_blind,
                "independent_fourth_cohort_validated": fourth_validated,
                "cohort_count_exactly_4": len(company_ranges) == 4,
                "oil_mixed_gas_group_coverage": company_ranges["group"].nunique()
                == 3,
                "dvn_fang_range_width_attribution_complete": attribution_complete,
                "minimum_two_strong_or_usable_ranges": width_passes >= 2,
                "leave_one_cohort_out_complete": loco_complete,
                "loco_p50_max_shift_10pp": loco_stable,
                "terminal_replacement_remains_locked": True,
                "cohort_count": len(company_ranges),
                "group_count": int(company_ranges["group"].nunique()),
                "strong_or_usable_range_count": width_passes,
                "too_uncertain_range_count": int(
                    (~company_ranges["range_width_gate_pass"]).sum()
                ),
                "effective_weighted_cohort_count": float(
                    distribution.iloc[0]["effective_weighted_cohort_count"]
                ),
                "max_abs_loco_p50_shift_pct_points": max_loco,
                "v1_9_research_gate": research_gate,
                "sample_stability_issue_resolved": freeze_eligible,
                "uncertainty_decomposition_issue_resolved": attribution_complete,
                "v1_9_research_freeze_eligible": freeze_eligible,
                "v1_9_research_frozen": False,
                "development_status": (
                    "RESEARCH_GATE_PASSED_FREEZE_ELIGIBLE_AWAITING_APPROVAL"
                    if freeze_eligible
                    else (
                        "RESEARCH_GATE_PASSED_FREEZE_DEFERRED"
                        if research_gate
                        else "RESEARCH_GATE_FAILED"
                    )
                ),
                "normal_roic_claimed": False,
                "sector_distribution_terminal_ready": False,
                "terminal_anchor_replacement_allowed": False,
                "wacc_recalibrated": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
