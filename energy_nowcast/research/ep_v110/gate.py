from __future__ import annotations

import pandas as pd


def build_v110_gate(
    *,
    parent_v19_verified: bool,
    waterfall_summary: pd.DataFrame,
    driver_evidence: pd.DataFrame,
) -> pd.DataFrame:
    ar = waterfall_summary.loc[waterfall_summary["ticker"].eq("AR")]
    ar_complete = bool(
        len(ar) == 1
        and ar.iloc[0]["waterfall_identity_pass"]
        and ar.iloc[0]["strong_company_comparison"]
        and ar.iloc[0]["cross_level_period_alignment"] == "OVERLAPPING_CLEAN_WINDOW"
    )
    identities = waterfall_summary.loc[
        waterfall_summary["company_organic_roic_midpoint_pct"].notna()
    ]["waterfall_identity_pass"].all()
    arbitrary_allocations = bool(driver_evidence["roic_effect_allocated"].any())
    complete = bool(parent_v19_verified and ar_complete and identities and not arbitrary_allocations)
    return pd.DataFrame(
        [
            {
                "v1_9_parent_frozen_verified": parent_v19_verified,
                "ar_overlapping_strong_waterfall_complete": ar_complete,
                "all_available_waterfall_identities_pass": bool(identities),
                "arbitrary_component_roic_allocations": arbitrary_allocations,
                "unexplained_company_scope_residual_retained": True,
                "v1_10_research_complete": complete,
                "v1_10_freeze_eligible": False,
                "freeze_deferred_reason": "ONLY_ONE_STRONG_PERIOD_ALIGNED_COMPANY_WATERFALL",
                "e_and_p_research_status": (
                    "PAUSED_AFTER_V1_10_EXPLANATORY_BRIDGE"
                    if complete
                    else "V1_10_RESEARCH_INCOMPLETE"
                ),
                "normal_roic_claimed": False,
                "terminal_anchor_replacement_allowed": False,
                "wacc_recalibrated": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
