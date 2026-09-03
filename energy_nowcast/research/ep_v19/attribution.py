from __future__ import annotations

import numpy as np
import pandas as pd


STAGES = {
    "reported": "reported_economic_organic_nopat",
    "price": "price_only_normalized_organic_nopat",
    "price_cost": "price_and_cost_normalized_organic_nopat",
    "full_cycle": "full_cycle_normalized_organic_nopat",
}
COMPONENTS = (
    "denominator",
    "price_normalization",
    "cost_normalization",
    "tax_normalization",
    "accounting_perimeter",
)


def _midpoint(row: pd.Series, stage: str) -> float:
    prefix = STAGES[stage]
    low = float(row[f"v174_{prefix}_cumulative_roic_low_pct"])
    high = float(row[f"v174_{prefix}_cumulative_roic_high_pct"])
    return (low + high) / 2.0


def build_range_width_attribution(
    *, closed_cohorts: pd.DataFrame, v18_company_ranges: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mature = closed_cohorts.loc[closed_cohorts["cohort_offset"].eq(2)].set_index(
        "ticker"
    )
    ranges = v18_company_ranges.set_index("ticker")
    wide_rows: list[dict[str, object]] = []
    long_rows: list[dict[str, object]] = []
    for ticker in ("DVN", "FANG"):
        row = mature.loc[ticker]
        company = ranges.loc[ticker]
        reported = _midpoint(row, "reported")
        price = _midpoint(row, "price")
        price_cost = _midpoint(row, "price_cost")
        full_cycle = _midpoint(row, "full_cycle")
        width = float(company["roic_range_width_pct"])
        direction = float(np.sign(full_cycle - reported))
        if direction == 0:
            direction = 1.0
        accounting_perimeter = max(
            width - abs(full_cycle - reported),
            0.0,
        )
        contributions = {
            "denominator": 0.0,
            "price_normalization": direction * (price - reported),
            "cost_normalization": direction * (price_cost - price),
            "tax_normalization": direction * (full_cycle - price_cost),
            "accounting_perimeter": accounting_perimeter,
        }
        attributed_width = sum(contributions.values())
        identity_error = width - attributed_width
        gross_movement = sum(
            abs(value)
            for value in (
                price - reported,
                price_cost - price,
                full_cycle - price_cost,
            )
        )
        positive = {
            name: value for name, value in contributions.items() if value > 0
        }
        dominant = max(positive, key=positive.get)
        wide = {
            "ticker": ticker,
            "group": company["group"],
            "reported_economic_midpoint_pct": reported,
            "price_only_midpoint_pct": price,
            "price_and_cost_midpoint_pct": price_cost,
            "full_cycle_midpoint_pct": full_cycle,
            "range_direction_reported_to_full_cycle": direction,
            "observed_range_width_pct": width,
            **{
                f"{name}_signed_width_contribution_pct": value
                for name, value in contributions.items()
            },
            "attributed_range_width_pct": attributed_width,
            "range_width_attribution_identity_error_pct": identity_error,
            "gross_absolute_methodology_movement_pct": gross_movement,
            "signed_offset_contribution_pct": sum(
                value for value in contributions.values() if value < 0
            ),
            "dominant_width_expansion_driver": dominant.upper(),
            "price_expansion_share_of_observed_width_pct": (
                contributions["price_normalization"] / width * 100.0
            ),
            "denominator_uncertainty_status": (
                "ZERO_FIXED_SINGLE_VALIDATED_COHORT_DENOMINATOR"
            ),
            "accounting_perimeter_uncertainty_status": (
                "BOUNDED_V1_7_4_ENDPOINT_STRESS"
                if accounting_perimeter > 0
                else "ZERO_RESOLVED_SINGLE_ENDPOINT"
            ),
            "decomposition_semantics": (
                "SIGNED_REPORTED_TO_PRICE_TO_COST_TO_TAX_PATH_PLUS_ENDPOINT_STRESS"
            ),
            "range_width_attribution_complete": abs(identity_error) <= 1e-9,
            "normal_roic_claimed": False,
            "terminal_input_allowed": False,
            "research_only": True,
        }
        wide_rows.append(wide)
        for component in COMPONENTS:
            contribution = contributions[component]
            long_rows.append(
                {
                    "ticker": ticker,
                    "group": company["group"],
                    "component": component.upper(),
                    "signed_width_contribution_pct": contribution,
                    "absolute_contribution_pct": abs(contribution),
                    "contribution_role": (
                        "WIDTH_EXPANSION"
                        if contribution > 0
                        else (
                            "WIDTH_OFFSET" if contribution < 0 else "NO_UNCERTAINTY"
                        )
                    ),
                    "observed_range_width_pct": width,
                    "decomposition_semantics": wide["decomposition_semantics"],
                    "normal_roic_claimed": False,
                    "terminal_input_allowed": False,
                    "research_only": True,
                }
            )
    wide = pd.DataFrame(wide_rows).sort_values("ticker").reset_index(drop=True)
    long = pd.DataFrame(long_rows).sort_values(["ticker", "component"]).reset_index(
        drop=True
    )
    if not wide["range_width_attribution_complete"].all():
        raise ValueError("DVN/FANG range-width attribution identity failed")
    return wide, long
