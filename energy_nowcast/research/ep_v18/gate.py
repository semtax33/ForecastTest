from __future__ import annotations

import pandas as pd


def build_v18_gate(
    *,
    parent_v174_verified: bool,
    company_ranges: pd.DataFrame,
    gas_cohort: pd.DataFrame,
    distribution: pd.DataFrame,
    loco: pd.DataFrame,
    three_level_comparison: pd.DataFrame,
) -> pd.DataFrame:
    mature_gas = gas_cohort.loc[gas_cohort["cohort_offset"].eq(2)]
    validated_ranges = int(company_ranges["accounting_perimeter_validated"].sum())
    groups = int(company_ranges["group"].nunique())
    width_classified = int(company_ranges["range_width_category"].notna().sum())
    usable_widths = int(company_ranges["range_width_gate_pass"].sum())
    loco_complete = len(loco) == len(company_ranges)
    loco_stable = bool(loco_complete and loco["all_loco_p50_stable"].all())
    comparison_complete = len(three_level_comparison) == len(company_ranges)
    gas_validated = bool(
        len(mature_gas) == 1
        and mature_gas.iloc[0]["organic_company_roic_validated"]
    )
    research_gate = bool(
        parent_v174_verified
        and len(company_ranges) >= 3
        and groups == 3
        and validated_ranges >= 3
        and gas_validated
        and width_classified == len(company_ranges)
        and loco_complete
        and comparison_complete
    )
    terminal_evidence_thresholds_met = bool(
        research_gate and usable_widths >= 3 and loco_stable
    )
    # V1.8 is a descriptive research layer. Even if the diagnostic evidence
    # thresholds are met in a later rerun, this version has no authority to
    # promote a pooled distribution into V1.1 terminal inputs.
    terminal_distribution_ready = False
    freeze_eligible = bool(
        research_gate and usable_widths >= 2 and loco_stable
    )
    return pd.DataFrame(
        [
            {
                "v1_7_4_frozen_parent_verified": parent_v174_verified,
                "cohort_count_min_3": len(company_ranges) >= 3,
                "oil_mixed_gas_group_coverage": groups == 3,
                "validated_company_research_ranges_min_3": validated_ranges >= 3,
                "gas_heavy_clean_cohort_validated": gas_validated,
                "range_width_policy_applied_all": width_classified
                == len(company_ranges),
                "three_level_comparison_complete": comparison_complete,
                "leave_one_cohort_out_complete": loco_complete,
                "minimum_two_strong_or_usable_ranges_for_freeze": usable_widths
                >= 2,
                "loco_p50_max_shift_10pp": loco_stable,
                "terminal_replacement_remains_locked": True,
                "cohort_count": len(company_ranges),
                "group_count": groups,
                "validated_company_research_ranges": validated_ranges,
                "strong_or_usable_range_count": usable_widths,
                "too_uncertain_range_count": int(
                    (~company_ranges["range_width_gate_pass"]).sum()
                ),
                "max_abs_loco_p50_shift_pct_points": float(
                    loco["abs_p50_shift_pct_points"].max()
                ),
                "v1_8_research_gate": research_gate,
                "sector_pooling_descriptive_ready": research_gate,
                "terminal_evidence_thresholds_met": (
                    terminal_evidence_thresholds_met
                ),
                "sector_distribution_terminal_ready": terminal_distribution_ready,
                "v1_8_research_freeze_eligible": freeze_eligible,
                "development_status": (
                    "RESEARCH_GATE_PASSED_FREEZE_ELIGIBLE"
                    if freeze_eligible
                    else (
                        "RESEARCH_GATE_PASSED_FREEZE_DEFERRED_DISTRIBUTION_UNSTABLE"
                        if research_gate
                        else "RESEARCH_GATE_FAILED"
                    )
                ),
                "normal_roic_claimed": False,
                "terminal_anchor_replacement_allowed": False,
                "wacc_recalibrated": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
