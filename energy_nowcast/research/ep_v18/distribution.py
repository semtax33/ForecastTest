from __future__ import annotations

import numpy as np
import pandas as pd


ACCOUNTING_CONFIDENCE_WEIGHTS = {"A": 1.0, "B": 0.5, "C": 0.0}
LOCO_P50_MAX_SHIFT_THRESHOLD_PCT = 10.0


def _classify_width(width: float, policy: pd.DataFrame) -> pd.Series:
    for _, row in policy.sort_values("min_width_pct_inclusive").iterrows():
        lower = float(row["min_width_pct_inclusive"])
        upper = row["max_width_pct_exclusive"]
        if width >= lower and (pd.isna(upper) or width < float(upper)):
            return row
    raise ValueError(f"No range-width policy for {width}")


def build_company_roic_ranges(
    *,
    v174_validation: pd.DataFrame,
    ar_cohort: pd.DataFrame,
    width_policy: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    groups = {"FANG": "oil_heavy", "DVN": "mixed"}
    for parent in v174_validation.to_dict("records"):
        ticker = str(parent["ticker"])
        low = float(parent["economically_comparable_roic_low_pct"])
        high = float(parent["economically_comparable_roic_high_pct"])
        rows.append(
            {
                "ticker": ticker,
                "group": groups[ticker],
                "event_name": parent["event_name"],
                "cohort_type": "MNA_CLOSED_THREE_YEAR_COHORT",
                "cohort_start_year": int(parent["deal_year"]),
                "cohort_end_year": int(parent["deal_year"]) + 2,
                "reported_gaap_roic_low_pct": parent[
                    "reported_gaap_3y_roic_low_pct"
                ],
                "reported_gaap_roic_high_pct": parent[
                    "reported_gaap_3y_roic_high_pct"
                ],
                "reported_economic_roic_low_pct": parent[
                    "reported_economic_3y_roic_low_pct"
                ],
                "reported_economic_roic_high_pct": parent[
                    "reported_economic_3y_roic_high_pct"
                ],
                "full_cycle_roic_low_pct": parent["full_cycle_3y_roic_low_pct"],
                "full_cycle_roic_high_pct": parent[
                    "full_cycle_3y_roic_high_pct"
                ],
                "organic_roic_research_low_pct": low,
                "organic_roic_research_high_pct": high,
                "accounting_confidence_grade": "A",
                "accounting_perimeter_validated": bool(
                    parent["organic_company_roic_validated"]
                ),
                "validation_route": (
                    "V1_7_4_MNA_CLOSURE_AND_TARGET_NOPAT_TRIANGULATION"
                ),
            }
        )
    ar = ar_cohort.loc[ar_cohort["cohort_offset"].eq(2)]
    if len(ar) != 1:
        raise ValueError("Expected one mature AR clean cohort")
    ar_row = ar.iloc[0]
    ar_economic = float(
        ar_row["reported_economic_nopat_cumulative_roic_pct"]
    )
    ar_full_cycle = float(
        ar_row["full_cycle_normalized_nopat_cumulative_roic_pct"]
    )
    rows.append(
        {
            "ticker": "AR",
            "group": "gas_heavy",
            "event_name": ar_row["event_name"],
            "cohort_type": ar_row["cohort_type"],
            "cohort_start_year": int(ar_row["cohort_start_year"]),
            "cohort_end_year": int(ar_row["cohort_end_year"]),
            "reported_gaap_roic_low_pct": ar_row[
                "reported_gaap_nopat_cumulative_roic_pct"
            ],
            "reported_gaap_roic_high_pct": ar_row[
                "reported_gaap_nopat_cumulative_roic_pct"
            ],
            "reported_economic_roic_low_pct": ar_economic,
            "reported_economic_roic_high_pct": ar_economic,
            "full_cycle_roic_low_pct": ar_full_cycle,
            "full_cycle_roic_high_pct": ar_full_cycle,
            "organic_roic_research_low_pct": min(ar_economic, ar_full_cycle),
            "organic_roic_research_high_pct": max(ar_economic, ar_full_cycle),
            "accounting_confidence_grade": "A",
            "accounting_perimeter_validated": bool(
                ar_row["organic_company_roic_validated"]
            ),
            "validation_route": (
                "DIRECT_E_AND_P_SEGMENT_IDENTITY_AND_CLEAN_ORGANIC_WINDOW"
            ),
        }
    )
    result = pd.DataFrame(rows)
    result["organic_roic_research_midpoint_pct"] = (
        result["organic_roic_research_low_pct"]
        + result["organic_roic_research_high_pct"]
    ) / 2.0
    result["roic_range_width_pct"] = (
        result["organic_roic_research_high_pct"]
        - result["organic_roic_research_low_pct"]
    )
    classifications = [
        _classify_width(float(width), width_policy)
        for width in result["roic_range_width_pct"]
    ]
    result["range_width_category"] = [row["range_category"] for row in classifications]
    result["range_width_research_weight"] = [
        float(row["research_weight"]) for row in classifications
    ]
    result["range_width_gate_pass"] = [
        bool(row["width_gate_pass"]) for row in classifications
    ]
    result["accounting_confidence_weight"] = result[
        "accounting_confidence_grade"
    ].map(ACCOUNTING_CONFIDENCE_WEIGHTS)
    result["company_confidence_weight"] = (
        result["accounting_confidence_weight"]
        * result["range_width_research_weight"]
    )
    result["normal_roic_claimed"] = False
    result["terminal_input_allowed"] = False
    result["research_only"] = True
    return result.sort_values("ticker").reset_index(drop=True)


def build_three_level_comparison(
    *,
    company_ranges: pd.DataFrame,
    three_level_parent: pd.DataFrame,
    acquisition_routes: pd.DataFrame,
) -> pd.DataFrame:
    levels = three_level_parent.set_index("ticker")
    rows: list[dict[str, object]] = []
    deal_years = {"FANG": 2018, "DVN": 2021}
    for company in company_ranges.to_dict("records"):
        ticker = str(company["ticker"])
        level = levels.loc[ticker]
        route = acquisition_routes.loc[
            acquisition_routes["ticker"].eq(ticker)
            & acquisition_routes["fiscal_year"].eq(deal_years.get(ticker, -1))
        ]
        acquisition = (
            float(route.iloc[0]["evidence_backed_acquisition_return_proxy_pct"])
            if len(route) == 1
            else np.nan
        )
        project = float(level["level_1_development_roic_pct"])
        reserve = float(level["level_2_reserve_replacement_roic_pct"])
        low = float(company["organic_roic_research_low_pct"])
        high = float(company["organic_roic_research_high_pct"])
        anchors = {
            "project": project,
            "reserve": reserve,
            "acquisition": acquisition,
        }
        available = {name: value for name, value in anchors.items() if pd.notna(value)}
        inside = {name: low <= value <= high for name, value in available.items()}
        concordant = sum(inside.values())
        rows.append(
            {
                "ticker": ticker,
                "group": company["group"],
                "project_development_roic_pct": project,
                "reserve_replacement_roic_pct": reserve,
                "acquisition_return_proxy_pct": acquisition,
                "company_organic_roic_low_pct": low,
                "company_organic_roic_high_pct": high,
                "available_independent_anchor_count": len(available),
                "anchors_inside_company_range": concordant,
                "anchor_range_concordance_ratio": (
                    concordant / len(available) if available else np.nan
                ),
                "project_inside_company_range": inside.get("project", np.nan),
                "reserve_inside_company_range": inside.get("reserve", np.nan),
                "acquisition_inside_company_range": inside.get(
                    "acquisition", np.nan
                ),
                "acquisition_semantics": (
                    "PREDEAL_TARGET_RUN_RATE_PROXY_NOT_NORMAL_ACQUISITION_ROIC"
                    if pd.notna(acquisition)
                    else "NOT_APPLICABLE_NO_MATERIAL_ACQUISITION_IN_COHORT_WINDOW"
                ),
                "comparison_status": (
                    "ALL_AVAILABLE_ANCHORS_INSIDE_COMPANY_RANGE"
                    if available and concordant == len(available)
                    else "CROSS_LEVEL_ECONOMICS_DIVERGE"
                ),
                "normal_roic_claimed": False,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        )
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def _weighted_quantile(
    values: np.ndarray, weights: np.ndarray, quantile: float
) -> float:
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    if len(values) == 0 or weights.sum() <= 0:
        return np.nan
    positions = (np.cumsum(weights) - 0.5 * weights) / weights.sum()
    return float(
        np.interp(quantile, positions, values, left=values[0], right=values[-1])
    )


def _distribution_row(frame: pd.DataFrame) -> dict[str, object]:
    weights = frame["company_confidence_weight"].to_numpy(dtype=float)
    midpoint = frame["organic_roic_research_midpoint_pct"].to_numpy(dtype=float)
    lower = frame["organic_roic_research_low_pct"].to_numpy(dtype=float)
    upper = frame["organic_roic_research_high_pct"].to_numpy(dtype=float)
    effective_n = (
        weights.sum() ** 2 / np.square(weights).sum()
        if np.square(weights).sum() > 0
        else 0.0
    )
    return {
        "cohort_count": len(frame),
        "group_count": int(frame["group"].nunique()),
        "effective_weighted_cohort_count": effective_n,
        "weighted_midpoint_mean_pct": float(np.average(midpoint, weights=weights)),
        "midpoint_p25_pct": _weighted_quantile(midpoint, weights, 0.25),
        "midpoint_p50_pct": _weighted_quantile(midpoint, weights, 0.50),
        "midpoint_p75_pct": _weighted_quantile(midpoint, weights, 0.75),
        "lower_endpoint_p25_pct": _weighted_quantile(lower, weights, 0.25),
        "lower_endpoint_p50_pct": _weighted_quantile(lower, weights, 0.50),
        "lower_endpoint_p75_pct": _weighted_quantile(lower, weights, 0.75),
        "upper_endpoint_p25_pct": _weighted_quantile(upper, weights, 0.25),
        "upper_endpoint_p50_pct": _weighted_quantile(upper, weights, 0.50),
        "upper_endpoint_p75_pct": _weighted_quantile(upper, weights, 0.75),
    }


def build_through_cycle_distribution(
    *, company_ranges: pd.DataFrame
) -> pd.DataFrame:
    row = _distribution_row(company_ranges)
    category_counts = company_ranges["range_width_category"].value_counts()
    row.update(
        {
            "strong_cohorts": int(category_counts.get("STRONG", 0)),
            "usable_research_cohorts": int(
                category_counts.get("USABLE_RESEARCH", 0)
            ),
            "too_uncertain_cohorts": int(
                category_counts.get("TOO_UNCERTAIN_FOR_TERMINAL", 0)
            ),
            "distribution_semantics": (
                "CONFIDENCE_WEIGHTED_EMPIRICAL_COHORT_RANGE_DESCRIPTION_NOT_POSTERIOR_OR_NORMAL_ROIC"
            ),
            "distribution_confidence": (
                "LOW_THREE_COHORTS_TWO_RANGE_WIDTH_RED_ONE_STRONG"
            ),
            "normal_roic_claimed": False,
            "terminal_input_allowed": False,
            "research_only": True,
        }
    )
    return pd.DataFrame([row])


def build_leave_one_cohort_out(
    *, company_ranges: pd.DataFrame, full_distribution: pd.DataFrame
) -> pd.DataFrame:
    full_p50 = float(full_distribution.iloc[0]["midpoint_p50_pct"])
    rows: list[dict[str, object]] = []
    for ticker in company_ranges["ticker"]:
        remaining = company_ranges.loc[~company_ranges["ticker"].eq(ticker)]
        distribution = _distribution_row(remaining)
        shift = float(distribution["midpoint_p50_pct"] - full_p50)
        rows.append(
            {
                "held_out_ticker": ticker,
                "held_out_group": company_ranges.loc[
                    company_ranges["ticker"].eq(ticker), "group"
                ].iloc[0],
                "remaining_cohorts": len(remaining),
                "remaining_groups": int(remaining["group"].nunique()),
                "full_midpoint_p50_pct": full_p50,
                "loco_midpoint_p25_pct": distribution["midpoint_p25_pct"],
                "loco_midpoint_p50_pct": distribution["midpoint_p50_pct"],
                "loco_midpoint_p75_pct": distribution["midpoint_p75_pct"],
                "p50_shift_pct_points": shift,
                "abs_p50_shift_pct_points": abs(shift),
                "predeclared_max_abs_p50_shift_pct_points": LOCO_P50_MAX_SHIFT_THRESHOLD_PCT,
                "loco_p50_stable": abs(shift) <= LOCO_P50_MAX_SHIFT_THRESHOLD_PCT,
                "terminal_input_allowed": False,
                "research_only": True,
            }
        )
    result = pd.DataFrame(rows)
    result["all_loco_p50_stable"] = result["loco_p50_stable"].all()
    result["max_abs_p50_shift_pct_points"] = result[
        "abs_p50_shift_pct_points"
    ].max()
    return result.sort_values("held_out_ticker").reset_index(drop=True)
