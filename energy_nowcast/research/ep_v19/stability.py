from __future__ import annotations

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v18.distribution import (
    _classify_width,
    _distribution_row,
    build_leave_one_cohort_out,
)


def build_expanded_company_ranges(
    *,
    v18_company_ranges: pd.DataFrame,
    rrc_cohort: pd.DataFrame,
    width_policy: pd.DataFrame,
) -> pd.DataFrame:
    result = v18_company_ranges.copy()
    mature = rrc_cohort.loc[rrc_cohort["cohort_offset"].eq(2)]
    if len(mature) != 1:
        raise ValueError("Expected one mature RRC cohort")
    row = mature.iloc[0]
    reported = float(row["reported_economic_nopat_cumulative_roic_pct"])
    full_cycle = float(
        row["full_cycle_normalized_nopat_cumulative_roic_pct"]
    )
    low = min(reported, full_cycle)
    high = max(reported, full_cycle)
    width = high - low
    policy = _classify_width(width, width_policy)
    addition = {column: np.nan for column in result.columns}
    addition.update(
        {
            "ticker": "RRC",
            "group": "gas_heavy",
            "event_name": row["event_name"],
            "cohort_type": row["cohort_type"],
            "cohort_start_year": int(row["cohort_start_year"]),
            "cohort_end_year": int(row["cohort_end_year"]),
            "reported_gaap_roic_low_pct": np.nan,
            "reported_gaap_roic_high_pct": np.nan,
            "reported_economic_roic_low_pct": reported,
            "reported_economic_roic_high_pct": reported,
            "full_cycle_roic_low_pct": full_cycle,
            "full_cycle_roic_high_pct": full_cycle,
            "organic_roic_research_low_pct": low,
            "organic_roic_research_high_pct": high,
            "accounting_confidence_grade": "A",
            "accounting_perimeter_validated": bool(
                row["organic_company_roic_validated"]
            ),
            "validation_route": (
                "DIRECT_SINGLE_SEGMENT_IDENTITY_RESERVE_ROLLFORWARD_AND_CLEAN_WINDOW"
            ),
            "organic_roic_research_midpoint_pct": (low + high) / 2.0,
            "roic_range_width_pct": width,
            "range_width_category": policy["range_category"],
            "range_width_research_weight": float(policy["research_weight"]),
            "range_width_gate_pass": bool(policy["width_gate_pass"]),
            "accounting_confidence_weight": 1.0,
            "company_confidence_weight": float(policy["research_weight"]),
            "normal_roic_claimed": False,
            "terminal_input_allowed": False,
            "research_only": True,
        }
    )
    result = pd.concat([result, pd.DataFrame([addition])], ignore_index=True)
    return result.sort_values("ticker").reset_index(drop=True)


def build_expanded_distribution(
    *, company_ranges: pd.DataFrame
) -> pd.DataFrame:
    row = _distribution_row(company_ranges)
    counts = company_ranges["range_width_category"].value_counts()
    strong = int(counts.get("STRONG", 0))
    usable = int(counts.get("USABLE_RESEARCH", 0))
    red = int(counts.get("TOO_UNCERTAIN_FOR_TERMINAL", 0))
    row.update(
        {
            "strong_cohorts": strong,
            "usable_research_cohorts": usable,
            "strong_or_usable_cohorts": strong + usable,
            "too_uncertain_cohorts": red,
            "distribution_semantics": (
                "CONFIDENCE_WEIGHTED_EMPIRICAL_COHORT_RANGE_DESCRIPTION_NOT_POSTERIOR_OR_NORMAL_ROIC"
            ),
            "distribution_confidence": (
                "RESEARCH_FREEZE_GATE_CANDIDATE_FOUR_COHORTS_EFFECTIVE_N_THREE"
            ),
            "normal_roic_claimed": False,
            "terminal_input_allowed": False,
            "research_only": True,
        }
    )
    return pd.DataFrame([row])


def build_expanded_loco(
    *, company_ranges: pd.DataFrame, distribution: pd.DataFrame
) -> pd.DataFrame:
    return build_leave_one_cohort_out(
        company_ranges=company_ranges,
        full_distribution=distribution,
    )


def build_stability_comparison(
    *,
    v18_distribution: pd.DataFrame,
    v18_loco: pd.DataFrame,
    v19_distribution: pd.DataFrame,
    v19_loco: pd.DataFrame,
) -> pd.DataFrame:
    before = v18_distribution.iloc[0]
    after = v19_distribution.iloc[0]
    before_max = float(v18_loco["abs_p50_shift_pct_points"].max())
    after_max = float(v19_loco["abs_p50_shift_pct_points"].max())
    return pd.DataFrame(
        [
            {
                "v1_8_cohort_count": int(before["cohort_count"]),
                "v1_9_cohort_count": int(after["cohort_count"]),
                "v1_8_effective_weighted_cohort_count": float(
                    before["effective_weighted_cohort_count"]
                ),
                "v1_9_effective_weighted_cohort_count": float(
                    after["effective_weighted_cohort_count"]
                ),
                "v1_8_midpoint_p50_pct": float(before["midpoint_p50_pct"]),
                "v1_9_midpoint_p50_pct": float(after["midpoint_p50_pct"]),
                "p50_change_pct_points": float(
                    after["midpoint_p50_pct"] - before["midpoint_p50_pct"]
                ),
                "v1_8_max_abs_loco_p50_shift_pct_points": before_max,
                "v1_9_max_abs_loco_p50_shift_pct_points": after_max,
                "max_abs_loco_improvement_pct_points": before_max - after_max,
                "v1_8_strong_or_usable_cohorts": int(before["strong_cohorts"])
                + int(before["usable_research_cohorts"]),
                "v1_9_strong_or_usable_cohorts": int(
                    after["strong_or_usable_cohorts"]
                ),
                "predeclared_min_strong_or_usable": 2,
                "predeclared_max_abs_loco_p50_shift_pct_points": 10.0,
                "sample_stability_gate_resolved": bool(
                    int(after["strong_or_usable_cohorts"]) >= 2
                    and after_max <= 10.0
                ),
                "normal_roic_claimed": False,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        ]
    )
