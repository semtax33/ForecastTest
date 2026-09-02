from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.phase6.financial_targets import EP_TICKERS


GREEN_GAP_PCT_POINTS = 5.0
YELLOW_GAP_PCT_POINTS = 10.0


def build_annual_consolidated_financials(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    frame = frame.loc[frame["subindustry"].eq("ep")].copy()
    frame["year"] = frame["quarter"].astype(str).str[:4].astype(int)
    frame = frame.loc[frame["year"].between(2021, 2025)]
    annual = (
        frame.groupby(["ticker", "year"], as_index=False)
        .agg(
            financial_quarters=("quarter", "nunique"),
            revenue_observations=("revenue", "count"),
            ebit_observations=("ebit_usd", "count"),
            consolidated_revenue_usd=("revenue", "sum"),
            consolidated_ebit_usd=("ebit_usd", "sum"),
            revenue_source_tags=(
                "revenue_source_tag",
                lambda values: ";".join(sorted(set(values.dropna().astype(str)))),
            ),
            ebit_methods=(
                "ebit_method",
                lambda values: ";".join(sorted(set(values.dropna().astype(str)))),
            ),
        )
        .sort_values(["ticker", "year"])
        .reset_index(drop=True)
    )
    complete = (
        annual["financial_quarters"].eq(4)
        & annual["revenue_observations"].eq(4)
        & annual["ebit_observations"].eq(4)
        & annual["consolidated_revenue_usd"].gt(0)
    )
    annual["consolidated_financial_status"] = np.where(
        complete,
        "FOUR_QUARTER_CONSOLIDATED_REVENUE_AND_EBIT",
        "LOCKED_INCOMPLETE_CONSOLIDATED_FINANCIAL_YEAR",
    )
    annual["consolidated_operating_margin_pct"] = np.where(
        complete,
        annual["consolidated_ebit_usd"]
        / annual["consolidated_revenue_usd"]
        * 100.0,
        np.nan,
    )
    return annual


def _annual_gap_grade(value: float) -> str:
    if not np.isfinite(value):
        return "LOCKED_NOT_COMPARABLE"
    absolute = abs(value)
    if absolute <= GREEN_GAP_PCT_POINTS:
        return "GREEN_ABSOLUTE_GAP_LE_5PPT"
    if absolute <= YELLOW_GAP_PCT_POINTS:
        return "YELLOW_ABSOLUTE_GAP_GT_5_LE_10PPT"
    return "RED_ABSOLUTE_GAP_GT_10PPT"


def build_annual_perimeter_reconciliation(
    *,
    v13_annual_path: Path,
    v14_cost_panel_path: Path,
    v14_cross_path: Path,
    consolidated_financial_path: Path,
) -> pd.DataFrame:
    unit = pd.read_csv(v13_annual_path)[
        [
            "ticker",
            "year",
            "lifting_cost_per_boe",
            "upstream_dda_per_boe",
        ]
    ]
    cost = pd.read_csv(v14_cost_panel_path)
    cost = cost.loc[cost["year"].between(2021, 2025)].copy()
    annual = unit.merge(cost, on=["ticker", "year"], how="inner")
    annual = annual.merge(
        build_annual_consolidated_financials(consolidated_financial_path),
        on=["ticker", "year"],
        how="left",
    )
    v14_status = pd.read_csv(v14_cross_path).set_index("ticker")
    cost_columns = [
        "lifting_cost_per_boe",
        "upstream_dda_per_boe",
        "transport_cost_per_boe",
        "production_tax_per_boe",
        "g_and_a_per_boe",
    ]
    rows: list[dict[str, object]] = []
    for item in annual.itertuples(index=False):
        row = item._asdict()
        ticker = str(item.ticker)
        missing_costs = [
            column for column in cost_columns if not np.isfinite(row.get(column, np.nan))
        ]
        exact_upstream_revenue = (
            row.get("upstream_revenue_usd_scope") == "UPSTREAM_EXACT"
            and np.isfinite(row.get("upstream_revenue_per_boe", np.nan))
            and float(row.get("upstream_revenue_per_boe", np.nan)) > 0
        )
        complete_financial = row.get("consolidated_financial_status") == (
            "FOUR_QUARTER_CONSOLIDATED_REVENUE_AND_EBIT"
        )
        comparable = exact_upstream_revenue and complete_financial
        known_cost = float(
            sum(float(row[column]) for column in cost_columns if column not in missing_costs)
        )
        upstream_revenue_per_boe = float(
            row.get("upstream_revenue_per_boe", np.nan)
        )
        if comparable:
            unit_margin = (
                upstream_revenue_per_boe - known_cost
            ) / upstream_revenue_per_boe * 100.0
            consolidated_margin = float(row["consolidated_operating_margin_pct"])
            gap = unit_margin - consolidated_margin
            production_boe = float(row["kpi_production_mboe"]) * 1_000.0
            reconstructed_ebit = (
                upstream_revenue_per_boe - known_cost
            ) * production_boe
            revenue_ratio = float(row["upstream_revenue_usd"]) / float(
                row["consolidated_revenue_usd"]
            )
            hedge = float(row.get("hedge_gain_loss_per_boe", np.nan))
            hedge_margin_effect = (
                hedge / upstream_revenue_per_boe * 100.0
                if np.isfinite(hedge)
                else np.nan
            )
            alternative_gap = (
                gap + hedge_margin_effect
                if np.isfinite(hedge_margin_effect)
                else np.nan
            )
            if np.isfinite(alternative_gap) and abs(alternative_gap) < abs(gap):
                minimum_gap = alternative_gap
                presentation = "HEDGE_OUTSIDE_UPSTREAM_REVENUE_FITS_BETTER_NOT_PROVEN"
            else:
                minimum_gap = gap
                presentation = "HEDGE_IN_UPSTREAM_REVENUE_FITS_BETTER_NOT_PROVEN"
        else:
            unit_margin = consolidated_margin = gap = np.nan
            reconstructed_ebit = revenue_ratio = np.nan
            hedge_margin_effect = alternative_gap = minimum_gap = np.nan
            presentation = "LOCKED_NOT_COMPARABLE"
        row.update(
            {
                "known_cost_per_boe": known_cost if exact_upstream_revenue else np.nan,
                "missing_cost_components": ";".join(missing_costs),
                "annual_cost_scope_status": (
                    "COMPLETE_STANDARDIZED_COST_SCOPE"
                    if not missing_costs
                    else "KNOWN_COST_UPPER_BOUND_MISSING_"
                    + "_AND_".join(
                        column.removesuffix("_per_boe").upper()
                        for column in missing_costs
                    )
                ),
                "v14_company_cost_scope_status": (
                    v14_status.loc[ticker, "v14_cost_scope_status"]
                    if ticker in v14_status.index
                    else "LOCKED_NO_V14_CROSS_CHECK"
                ),
                "v14_hedge_inclusion_diagnostic": (
                    v14_status.loc[ticker, "hedge_inclusion_diagnostic"]
                    if ticker in v14_status.index
                    else "LOCKED_NO_V14_HEDGE_DIAGNOSTIC"
                ),
                "perimeter_comparable": comparable,
                "unit_reconstructed_operating_margin_pct": unit_margin,
                "unit_reconstructed_ebit_usd": reconstructed_ebit,
                "raw_margin_gap_pct_points": gap,
                "absolute_raw_margin_gap_pct_points": abs(gap),
                "annual_perimeter_grade": _annual_gap_grade(gap),
                "upstream_to_consolidated_revenue_ratio": revenue_ratio,
                "reported_hedge_margin_effect_pct_points": hedge_margin_effect,
                "gap_if_reported_hedge_added_to_unit_pct_points": alternative_gap,
                "minimum_abs_gap_hedge_presentation_diagnostic_pct_points": abs(
                    minimum_gap
                ),
                "best_fit_hedge_presentation_diagnostic": presentation,
                "hedge_accounting_adjustment_applied": False,
                "research_only": True,
                "terminal_anchor_ready": False,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["ticker", "year"]).reset_index(drop=True)


def build_perimeter_summary(annual: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        history = annual.loc[
            annual["ticker"].eq(ticker) & annual["perimeter_comparable"]
        ]
        v14_rows = annual.loc[annual["ticker"].eq(ticker)]
        v14_status = (
            str(v14_rows.iloc[0]["v14_company_cost_scope_status"])
            if len(v14_rows)
            else "LOCKED_NO_V14_CROSS_CHECK"
        )
        hedge_diagnostic = (
            str(v14_rows.iloc[0]["v14_hedge_inclusion_diagnostic"])
            if len(v14_rows)
            else "LOCKED_NO_V14_HEDGE_DIAGNOSTIC"
        )
        complete_cost = v14_status == "COMPLETE_STANDARDIZED_COST_SCOPE_CROSS_CHECK"
        count = len(history)
        green = int(
            history["annual_perimeter_grade"].eq(
                "GREEN_ABSOLUTE_GAP_LE_5PPT"
            ).sum()
        )
        yellow = int(
            history["annual_perimeter_grade"].eq(
                "YELLOW_ABSOLUTE_GAP_GT_5_LE_10PPT"
            ).sum()
        )
        red = int(
            history["annual_perimeter_grade"].eq(
                "RED_ABSOLUTE_GAP_GT_10PPT"
            ).sum()
        )
        median_abs = (
            float(history["absolute_raw_margin_gap_pct_points"].median())
            if count
            else np.nan
        )
        median_ratio = (
            float(history["upstream_to_consolidated_revenue_ratio"].median())
            if count
            else np.nan
        )
        red_share = red / count if count else np.nan
        numeric_pass = bool(
            complete_cost
            and count >= 3
            and median_abs <= GREEN_GAP_PCT_POINTS
            and red_share <= 0.25
            and 0.9 <= median_ratio <= 1.1
        )
        if not complete_cost:
            gate = "LOCKED_INCOMPLETE_STANDARDIZED_COST_SCOPE"
        elif count < 3:
            gate = "LOCKED_FEWER_THAN_3_COMPARABLE_YEARS"
        elif numeric_pass and hedge_diagnostic == (
            "STRONG_EXACT_HEDGE_ASSOCIATION_REVENUE_INCLUSION_NOT_PROVEN"
        ):
            gate = "LOCKED_NUMERIC_PASS_HEDGE_PRESENTATION_NOT_PROVEN"
        elif numeric_pass:
            gate = "PASS_RESEARCH_PERIMETER_RECONCILIATION"
        elif median_abs <= YELLOW_GAP_PCT_POINTS:
            gate = "REVIEW_VOLATILE_ANNUAL_GAPS"
        else:
            gate = "FAIL_MEDIAN_ABSOLUTE_GAP_GT_10PPT"
        rows.append(
            {
                "ticker": ticker,
                "v14_cost_scope_status": v14_status,
                "v14_hedge_inclusion_diagnostic": hedge_diagnostic,
                "comparable_years_2021_2025": count,
                "green_years": green,
                "yellow_years": yellow,
                "red_years": red,
                "red_year_share": red_share,
                "median_absolute_raw_margin_gap_pct_points": median_abs,
                "median_upstream_to_consolidated_revenue_ratio": median_ratio,
                "numeric_reconciliation_pass": numeric_pass,
                "accounting_perimeter_reconciliation_gate": gate,
                "gate_thresholds": (
                    "PROVISIONAL_GREEN_LE_5PPT_YELLOW_LE_10PPT_RED_GT_10PPT"
                ),
                "terminal_anchor_ready": False,
                "research_only": True,
            }
        )
    return pd.DataFrame(rows)


def build_accounting_perimeter_research(
    *,
    v13_annual_path: Path,
    v14_cost_panel_path: Path,
    v14_cross_path: Path,
    consolidated_financial_path: Path,
) -> dict[str, pd.DataFrame]:
    annual = build_annual_perimeter_reconciliation(
        v13_annual_path=v13_annual_path,
        v14_cost_panel_path=v14_cost_panel_path,
        v14_cross_path=v14_cross_path,
        consolidated_financial_path=consolidated_financial_path,
    )
    return {
        "annual_accounting_perimeter_reconciliation": annual,
        "accounting_perimeter_reconciliation_summary": build_perimeter_summary(
            annual
        ),
    }
