from __future__ import annotations

import numpy as np
import pandas as pd


MATERIALITY_RATIO = 0.01
ELIGIBLE_DENOMINATOR_RATIO = 0.02


def build_v171_company_year_bridge(
    *, acquisition_proof: pd.DataFrame, annual_organic: pd.DataFrame
) -> pd.DataFrame:
    annual = annual_organic.copy()
    proof_columns = [
        "ticker",
        "fiscal_year",
        "event_name",
        "event_type",
        "event_close_date",
        "company_year_contamination_status",
        "acquiree_net_income_since_close_usd",
        "full_year_normalized_acquiree_net_income_usd",
        "acquired_invested_capital_usd",
        "acquired_capital_scope_complete",
        "acquisition_related_cost_usd",
        "integration_restructuring_cost_usd",
        "ownership_fraction",
        "ownership_normalization_status",
        "normalized_acquiree_return_proxy_pct",
        "normalized_acquiree_return_semantics",
        "purchase_accounting_step_up_usd",
        "purchase_accounting_step_up_proven",
    ]
    events = acquisition_proof[proof_columns].rename(columns={"fiscal_year": "year"})
    overlapping_parent_columns = [
        column
        for column in events.columns
        if column in annual.columns and column not in {"ticker", "year"}
    ]
    annual = annual.drop(columns=overlapping_parent_columns)
    merged = events.merge(annual, on=["ticker", "year"], how="left", validate="one_to_one")
    if merged["raw_delta_invested_capital_usd"].isna().any():
        missing = merged.loc[
            merged["raw_delta_invested_capital_usd"].isna(), ["ticker", "year"]
        ].to_dict("records")
        raise ValueError(f"Missing V1.7 annual capital rows: {missing}")

    opening = merged["opening_invested_capital_usd"].abs()
    acquired = merged["acquired_invested_capital_usd"].fillna(0.0)
    gross_capital_perimeter = opening + acquired
    merged["gross_event_capital_perimeter_usd"] = gross_capital_perimeter
    merged["economic_acquisition_materiality_ratio"] = acquired / opening
    merged["divestiture_materiality_ratio_gross_perimeter"] = (
        merged["divestiture_cash_proxy_usd"].fillna(0.0) / gross_capital_perimeter
    )
    merged["material_divestiture_gross_perimeter"] = merged[
        "divestiture_materiality_ratio_gross_perimeter"
    ].gt(MATERIALITY_RATIO)
    merged["divestiture_treatment"] = np.where(
        merged["material_divestiture_gross_perimeter"],
        "LOCKED_MATERIAL_DIVESTITURE_BOOK_CAPITAL_AND_NOPAT_NOT_FULLY_PROVEN",
        "IMMATERIAL_UNADJUSTED_UNDER_GROSS_EVENT_CAPITAL_PERIMETER",
    )

    business = merged["event_type"].eq("business_combination")
    tax_rate = merged["effective_tax_rate"].clip(lower=0.0, upper=0.35)
    disclosed_deal_cost = (
        merged["acquisition_related_cost_usd"].fillna(0.0)
        + merged["integration_restructuring_cost_usd"].fillna(0.0)
    )
    merged["deal_cost_after_tax_addback_usd"] = disclosed_deal_cost * (1.0 - tax_rate)
    merged["acquired_current_period_after_tax_contribution_proxy_usd"] = np.where(
        business, merged["acquiree_net_income_since_close_usd"], np.nan
    )
    merged["acquired_full_year_normalized_after_tax_contribution_proxy_usd"] = np.where(
        business, merged["full_year_normalized_acquiree_net_income_usd"], np.nan
    )
    merged["organic_delta_nopat_same_period_proxy_usd"] = (
        merged["raw_delta_nopat_usd"]
        - merged["acquired_current_period_after_tax_contribution_proxy_usd"]
        + merged["deal_cost_after_tax_addback_usd"]
    )
    merged["organic_delta_invested_capital_v171_proxy_usd"] = (
        merged["raw_delta_invested_capital_usd"]
        - merged["acquired_invested_capital_usd"]
    )
    merged["same_period_vs_full_year_numerator_separated"] = (
        merged["acquired_current_period_after_tax_contribution_proxy_usd"].notna()
        & merged[
            "acquired_full_year_normalized_after_tax_contribution_proxy_usd"
        ].notna()
    )
    merged["company_year_mna_scope_fully_bridged"] = (
        business
        & merged["acquired_capital_scope_complete"]
        & merged["acquiree_net_income_since_close_usd"].notna()
        & merged["acquisition_related_cost_usd"].notna()
        & merged["effective_tax_rate"].notna()
        & merged["company_year_contamination_status"].eq("NONE")
        & ~merged["material_divestiture_gross_perimeter"]
    )
    denominator_ratio = (
        merged["organic_delta_invested_capital_v171_proxy_usd"] / opening
    )
    merged["organic_incremental_roic_v171_proxy_ready"] = (
        merged["company_year_mna_scope_fully_bridged"]
        & merged["raw_delta_nopat_usd"].notna()
        & merged["organic_delta_invested_capital_v171_proxy_usd"].gt(1_000_000.0)
        & denominator_ratio.gt(ELIGIBLE_DENOMINATOR_RATIO)
    )
    merged["organic_incremental_roic_v171_after_tax_proxy_pct"] = np.where(
        merged["organic_incremental_roic_v171_proxy_ready"],
        merged["organic_delta_nopat_same_period_proxy_usd"]
        / merged["organic_delta_invested_capital_v171_proxy_usd"]
        * 100.0,
        np.nan,
    )
    merged["company_year_bridge_status"] = np.select(
        [
            ~business,
            ~merged["company_year_contamination_status"].eq("NONE"),
            merged["material_divestiture_gross_perimeter"],
            ~merged["acquired_capital_scope_complete"],
            merged["acquiree_net_income_since_close_usd"].isna(),
            merged["company_year_mna_scope_fully_bridged"]
            & ~merged["organic_incremental_roic_v171_proxy_ready"],
            merged["organic_incremental_roic_v171_proxy_ready"],
        ],
        [
            "LOCKED_ASSET_ACQUISITION_NO_SEPARATE_OPERATING_CONTRIBUTION",
            merged["company_year_contamination_status"],
            "LOCKED_MATERIAL_DIVESTITURE_PERIMETER_INCOMPLETE",
            "LOCKED_ACQUIRED_CAPITAL_SCOPE_INCOMPLETE",
            "LOCKED_ACQUIRED_NUMERATOR_SCOPE_INCOMPLETE",
            "FULL_MNA_SCOPE_BRIDGE_NONPOSITIVE_OR_SMALL_ORGANIC_DENOMINATOR",
            "DIAGNOSTIC_FULL_MNA_SCOPE_AFTER_TAX_PROXY_NOT_NOPAT",
        ],
        default="LOCKED_INCOMPLETE_MNA_SCOPE",
    )
    merged["organic_company_roic_validated"] = False
    merged["terminal_input_allowed"] = False
    merged["research_only"] = True
    return merged.sort_values(["year", "ticker"]).reset_index(drop=True)


def build_v171_deal_cohorts(
    *,
    acquisition_proof: pd.DataFrame,
    company_year_bridge: pd.DataFrame,
    annual_organic: pd.DataFrame,
) -> pd.DataFrame:
    candidates = acquisition_proof.loc[
        acquisition_proof["event_type"].eq("business_combination")
        & acquisition_proof["acquiree_net_income_since_close_usd"].notna()
    ].copy()
    rows: list[dict[str, object]] = []
    for event in candidates.to_dict("records"):
        ticker = str(event["ticker"])
        event_year = int(event["fiscal_year"])
        event_bridge = company_year_bridge.loc[
            company_year_bridge["ticker"].eq(ticker)
            & company_year_bridge["year"].eq(event_year)
        ]
        if len(event_bridge) != 1:
            raise ValueError(f"Expected one V1.7.1 event bridge for {ticker} {event_year}")
        event_opening = float(event_bridge.iloc[0]["opening_invested_capital_usd"])
        cumulative_numerator = 0.0
        cumulative_denominator = 0.0
        all_scope_complete = True
        observed = 0
        for offset in range(3):
            year = event_year + offset
            annual_row = annual_organic.loc[
                annual_organic["ticker"].eq(ticker) & annual_organic["year"].eq(year)
            ]
            if len(annual_row) != 1:
                continue
            observed += 1
            if offset == 0:
                source = event_bridge.iloc[0]
                numerator = float(source["organic_delta_nopat_same_period_proxy_usd"])
                denominator = float(source["organic_delta_invested_capital_v171_proxy_usd"])
                scope_complete = bool(source["company_year_mna_scope_fully_bridged"])
                source_semantics = "V171_EVENT_YEAR_SAME_PERIOD_MNA_BRIDGE"
            else:
                source = annual_row.iloc[0]
                numerator = float(source["organic_delta_nopat_after_tax_proxy_usd"])
                denominator = float(source["organic_delta_invested_capital_proxy_usd"])
                scope_complete = bool(
                    source["numerator_scope_complete"]
                    and source["denominator_scope_complete"]
                )
                source_semantics = "V17_SUBSEQUENT_YEAR_ORGANIC_DIAGNOSTIC"
            all_scope_complete = all_scope_complete and scope_complete
            if all_scope_complete:
                cumulative_numerator += numerator
                cumulative_denominator += denominator
                cumulative_numerator_output = cumulative_numerator
                cumulative_denominator_output = cumulative_denominator
            else:
                cumulative_numerator_output = np.nan
                cumulative_denominator_output = np.nan
            denominator_threshold = abs(event_opening) * ELIGIBLE_DENOMINATOR_RATIO
            year_roic = (
                numerator / denominator * 100.0
                if scope_complete and denominator > denominator_threshold
                else np.nan
            )
            cumulative_roic = (
                cumulative_numerator / cumulative_denominator * 100.0
                if all_scope_complete
                and cumulative_denominator > denominator_threshold
                else np.nan
            )
            window_complete = offset == 2 and observed == 3 and all_scope_complete
            rows.append(
                {
                    "ticker": ticker,
                    "event_name": event["event_name"],
                    "deal_year": event_year,
                    "cohort_offset": offset,
                    "observation_year": year,
                    "year_label": f"t+{offset}" if offset else "t",
                    "annual_organic_delta_nopat_after_tax_proxy_usd": numerator,
                    "annual_organic_delta_invested_capital_proxy_usd": denominator,
                    "annual_organic_incremental_roic_proxy_pct": year_roic,
                    "annual_scope_complete": scope_complete,
                    "annual_source_semantics": source_semantics,
                    "cumulative_organic_delta_nopat_after_tax_proxy_usd": cumulative_numerator_output,
                    "cumulative_organic_invested_capital_proxy_usd": cumulative_denominator_output,
                    "cumulative_organic_incremental_roic_proxy_pct": cumulative_roic,
                    "cohort_window_complete": window_complete,
                    "cohort_validated": False,
                    "cohort_status": (
                        "COMPLETE_3Y_DIAGNOSTIC_AFTER_TAX_PROXY_NOT_NOPAT_OR_CYCLE_NORMALIZED"
                        if window_complete
                        else (
                            "PARTIAL_OBSERVATION_WINDOW"
                            if all_scope_complete
                            else "LOCKED_INCOMPLETE_COMPANY_YEAR_MNA_SCOPE"
                        )
                    ),
                    "terminal_input_allowed": False,
                    "research_only": True,
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["deal_year", "ticker", "cohort_offset"]
    ).reset_index(drop=True)
