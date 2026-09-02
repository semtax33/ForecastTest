from __future__ import annotations

import pandas as pd


def build_terminal_candidate_gate(
    *,
    coverage_summary: pd.DataFrame,
    accounting_summary: pd.DataFrame,
    roic_summary: pd.DataFrame,
    parent_roic_path,
) -> pd.DataFrame:
    parent_roic = pd.read_csv(parent_roic_path)[
        ["ticker", "observed_all_in_reserve_cost_years"]
    ]
    result = (
        coverage_summary.merge(accounting_summary, on="ticker", how="left")
        .merge(roic_summary, on="ticker", how="left")
        .merge(parent_roic, on="ticker", how="left")
    )
    result["reserve_chain_5plus_usable_years"] = result[
        "v16_usable_replacement_years"
    ].ge(5)
    result["all_in_reserve_cost_3plus_years"] = result[
        "observed_all_in_reserve_cost_years"
    ].ge(3)
    result["basis_explainable"] = result["actual_three_component_mix_ready"]
    result["three_roic_levels_present"] = (
        result["level_1_development_roic_pct"].notna()
        & result["level_2_reserve_replacement_roic_pct"].notna()
        & result["level_3_company_incremental_roic_q50_pct"].notna()
    )
    requirements = [
        "complete_standardized_cost_scope",
        "accounting_perimeter_pass",
        "reserve_chain_5plus_usable_years",
        "actual_three_component_mix_ready",
        "basis_explainable",
        "three_roic_levels_present",
        "all_in_reserve_cost_3plus_years",
        "hedge_presentation_proven",
    ]
    result["terminal_candidate_ready"] = result[requirements].all(axis=1) & ~result[
        "unexplained_roic_over_100pct"
    ]
    result["terminal_anchor_replacement_allowed"] = False
    result["terminal_candidate_status"] = result.apply(
        lambda row: "RESEARCH_CANDIDATE_NOT_PROMOTED"
        if row["terminal_candidate_ready"]
        else "LOCKED_" + ";".join(
            column.upper()
            for column in requirements
            if not bool(row[column])
        )
        + (";UNEXPLAINED_ROIC_OVER_100PCT" if row["unexplained_roic_over_100pct"] else ""),
        axis=1,
    )
    return result
