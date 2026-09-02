from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.phase6.financial_targets import EP_TICKERS


MATERIALITY_RATIO = 0.01
ELIGIBLE_DENOMINATOR_RATIO = 0.02


def _event_capital_proxies(events: pd.DataFrame) -> pd.DataFrame:
    result = events.copy()
    business = result["event_type"].eq("business_combination")
    net_assets = result["recognized_net_assets_usd"]
    assumed_debt = result["assumed_long_term_debt_usd"].fillna(0.0)
    acquired_cash = result["cash_acquired_usd"].fillna(0.0)
    result["acquired_invested_capital_proxy_usd"] = np.where(
        business & net_assets.notna(),
        net_assets + assumed_debt - acquired_cash,
        result["asset_acquisition_ppe_usd"],
    )
    result["acquired_capital_proxy_semantics"] = np.select(
        [
            business
            & net_assets.notna()
            & result["assumed_long_term_debt_usd"].notna()
            & result["cash_acquired_usd"].notna(),
            business & net_assets.notna(),
            result["event_type"].eq("asset_acquisition")
            & result["asset_acquisition_ppe_usd"].notna(),
        ],
        [
            "PPA_NET_ASSETS_PLUS_ASSUMED_DEBT_MINUS_ACQUIRED_CASH",
            "PPA_NET_ASSETS_PROXY_MISSING_EXPLICIT_DEBT_OR_CASH_COMPONENT",
            "ASSET_ACQUISITION_PPE_ONLY_LOWER_BOUND",
        ],
        default="NO_ACQUIRED_CAPITAL_EVIDENCE",
    )
    result["cash_consideration_proxy_usd"] = np.where(
        result["total_consideration_usd"].notna()
        & result["equity_consideration_usd"].notna(),
        result["total_consideration_usd"] - result["equity_consideration_usd"],
        np.where(
            result["total_consideration_usd"].notna(),
            result["total_consideration_usd"],
            result["net_cash_paid_usd"] + result["cash_acquired_usd"].fillna(0.0),
        ),
    )
    result["noncash_equity_consideration_usd"] = result[
        "equity_consideration_usd"
    ].fillna(0.0)
    result["noncash_assumed_debt_usd"] = result[
        "assumed_long_term_debt_usd"
    ].fillna(0.0)
    result["purchase_accounting_step_up_usd"] = np.nan
    result["purchase_accounting_step_up_status"] = (
        "LOCKED_ACQUIREE_PREDEAL_BOOK_BASIS_NOT_IDENTIFIED"
    )
    result["acquired_nopat_directly_disclosed"] = False
    result["after_tax_earnings_contribution_proxy_available"] = result[
        "acquiree_net_income_since_close_usd"
    ].notna()
    result["acquired_numerator_semantics"] = np.where(
        result["after_tax_earnings_contribution_proxy_available"],
        "ACQUIREE_NET_INCOME_SINCE_CLOSE_AFTER_TAX_PROXY_NOT_NOPAT",
        "LOCKED_NO_SEPARATE_ACQUIREE_AFTER_TAX_CONTRIBUTION",
    )
    result["organic_company_roic_validated"] = False
    result["terminal_input_allowed"] = False
    return result


def build_organic_company_economics(
    *,
    event_evidence: pd.DataFrame,
    parent_capital_panel_path: Path,
    ttm_financial_path: Path,
) -> dict[str, pd.DataFrame]:
    events = _event_capital_proxies(event_evidence)
    panel = pd.read_csv(parent_capital_panel_path)
    ttm = pd.read_parquet(ttm_financial_path)
    annual_tax = ttm.loc[
        ttm["subindustry"].eq("ep")
        & ttm["quarter"].astype(str).str.endswith("Q4"),
        ["ticker", "quarter", "effective_tax_rate", "tax_rate_method"],
    ].copy()
    annual_tax["year"] = annual_tax["quarter"].astype(str).str[:4].astype(int)
    annual_tax = annual_tax.drop(columns="quarter").drop_duplicates(["ticker", "year"])
    if "effective_tax_rate" not in panel or "tax_rate_method" not in panel:
        panel = panel.merge(annual_tax, on=["ticker", "year"], how="left")
    event_columns = [
        "ticker",
        "fiscal_year",
        "event_name",
        "event_type",
        "event_close_date",
        "filing_date",
        "classification_phrase_proven",
        "acquired_invested_capital_proxy_usd",
        "acquired_capital_proxy_semantics",
        "acquiree_net_income_since_close_usd",
        "acquiree_revenue_since_close_usd",
        "acquisition_related_cost_usd",
        "acquired_numerator_semantics",
        "acquired_nopat_directly_disclosed",
        "noncash_equity_consideration_usd",
        "noncash_assumed_debt_usd",
        "purchase_accounting_step_up_usd",
        "purchase_accounting_step_up_status",
    ]
    panel = panel.merge(
        events[event_columns].rename(columns={"fiscal_year": "year"}),
        on=["ticker", "year"],
        how="left",
    )
    opening = panel["opening_invested_capital_usd"].abs()
    observed_acquisition = panel["acquisition_cash_proxy_usd"].fillna(0.0)
    ppa_acquisition = panel["acquired_invested_capital_proxy_usd"].fillna(0.0)
    panel["acquisition_materiality_ratio"] = (
        pd.concat([observed_acquisition, ppa_acquisition], axis=1).max(axis=1)
        / opening
    )
    panel["divestiture_materiality_ratio"] = (
        panel["divestiture_cash_proxy_usd"].fillna(0.0) / opening
    )
    panel["material_acquisition"] = panel["acquisition_materiality_ratio"].gt(
        MATERIALITY_RATIO
    )
    panel["material_divestiture"] = panel["divestiture_materiality_ratio"].gt(
        MATERIALITY_RATIO
    )
    panel["acquired_capital_adjustment_usd"] = np.where(
        panel["material_acquisition"],
        panel["acquired_invested_capital_proxy_usd"],
        0.0,
    )
    panel["acquisition_capital_scope_complete"] = (
        ~panel["material_acquisition"]
        | panel["acquired_invested_capital_proxy_usd"].notna()
    )
    panel["divested_capital_adjustment_usd"] = np.where(
        panel["material_divestiture"],
        np.nan,
        panel["divestiture_cash_proxy_usd"].fillna(0.0),
    )
    panel["divestiture_capital_scope_complete"] = ~panel["material_divestiture"]
    panel["organic_delta_invested_capital_proxy_usd"] = (
        panel["raw_delta_invested_capital_usd"]
        - panel["acquired_capital_adjustment_usd"]
        + panel["divested_capital_adjustment_usd"]
    )
    panel["pre_divestiture_scope_delta_invested_capital_proxy_usd"] = (
        panel["raw_delta_invested_capital_usd"]
        - panel["acquired_capital_adjustment_usd"]
        + panel["divestiture_cash_proxy_usd"].fillna(0.0)
    )
    panel["denominator_scope_complete"] = (
        panel["acquisition_capital_scope_complete"]
        & panel["divestiture_capital_scope_complete"]
    )

    material_business = panel["material_acquisition"] & panel["event_type"].eq(
        "business_combination"
    )
    material_asset = panel["material_acquisition"] & panel["event_type"].eq(
        "asset_acquisition"
    )
    panel["acquired_after_tax_contribution_adjustment_usd"] = np.where(
        material_business,
        panel["acquiree_net_income_since_close_usd"],
        np.where(panel["material_acquisition"], np.nan, 0.0),
    )
    panel["transaction_cost_after_tax_addback_usd"] = np.where(
        material_business,
        panel["acquisition_related_cost_usd"]
        * (1.0 - panel["effective_tax_rate"].clip(lower=0.0, upper=0.35)),
        0.0,
    )
    panel["acquisition_numerator_scope_complete"] = (
        ~panel["material_acquisition"]
        | (
            material_business
            & panel["acquiree_net_income_since_close_usd"].notna()
            & panel["acquisition_related_cost_usd"].notna()
            & panel["effective_tax_rate"].notna()
        )
    ) & ~material_asset
    panel["divested_after_tax_contribution_adjustment_usd"] = np.where(
        panel["material_divestiture"], np.nan, 0.0
    )
    panel["divestiture_numerator_scope_complete"] = ~panel["material_divestiture"]
    panel["numerator_scope_complete"] = (
        panel["acquisition_numerator_scope_complete"]
        & panel["divestiture_numerator_scope_complete"]
    )
    panel["organic_delta_nopat_after_tax_proxy_usd"] = (
        panel["raw_delta_nopat_usd"]
        - panel["acquired_after_tax_contribution_adjustment_usd"]
        + panel["transaction_cost_after_tax_addback_usd"]
        + panel["divested_after_tax_contribution_adjustment_usd"]
    )
    panel["pre_divestiture_scope_delta_nopat_after_tax_proxy_usd"] = (
        panel["raw_delta_nopat_usd"]
        - panel["acquired_after_tax_contribution_adjustment_usd"]
        + panel["transaction_cost_after_tax_addback_usd"]
    )
    denominator_ratio = (
        panel["organic_delta_invested_capital_proxy_usd"] / opening
    )
    panel["organic_incremental_roic_proxy_ready"] = (
        panel["raw_delta_nopat_usd"].notna()
        & panel["numerator_scope_complete"]
        & panel["denominator_scope_complete"]
        & panel["organic_delta_invested_capital_proxy_usd"].gt(1_000_000.0)
        & denominator_ratio.gt(ELIGIBLE_DENOMINATOR_RATIO)
    )
    panel["organic_incremental_roic_after_tax_proxy_pct"] = np.where(
        panel["organic_incremental_roic_proxy_ready"],
        panel["organic_delta_nopat_after_tax_proxy_usd"]
        / panel["organic_delta_invested_capital_proxy_usd"]
        * 100.0,
        np.nan,
    )
    panel["material_mna_year_proxy_ready"] = (
        panel["organic_incremental_roic_proxy_ready"]
        & (panel["material_acquisition"] | panel["material_divestiture"])
    )
    panel["organic_company_roic_validated"] = False
    panel["terminal_input_allowed"] = False
    panel["organic_bridge_status"] = np.select(
        [
            material_asset & panel["material_divestiture"],
            panel["material_divestiture"],
            material_asset,
            panel["material_acquisition"]
            & ~panel["acquisition_capital_scope_complete"],
            panel["material_acquisition"]
            & ~panel["acquisition_numerator_scope_complete"],
            panel["organic_incremental_roic_proxy_ready"]
            & panel["material_acquisition"],
            panel["organic_incremental_roic_proxy_ready"],
        ],
        [
            "LOCKED_ASSET_ACQUISITION_CONTRIBUTION_AND_MATERIAL_DIVESTITURE_SCOPE_MISSING",
            "LOCKED_MATERIAL_DIVESTITURE_BOOK_CAPITAL_AND_NOPAT_MISSING",
            "LOCKED_ASSET_ACQUISITION_OPERATING_CONTRIBUTION_NOT_SEPARABLE",
            "LOCKED_MATERIAL_ACQUISITION_CAPITAL_SCOPE_MISSING",
            "LOCKED_MATERIAL_ACQUISITION_NUMERATOR_SCOPE_MISSING",
            "DIAGNOSTIC_MATERIAL_MNA_BRIDGED_AFTER_TAX_PROXY_NOT_NOPAT",
            "DIAGNOSTIC_ORGANIC_NO_MATERIAL_MNA_OR_IMMATERIAL_MNA",
        ],
        default="LOCKED_NONPOSITIVE_SMALL_OR_INCOMPLETE_ORGANIC_DENOMINATOR",
    )
    panel["research_only"] = True

    summary_rows: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        history = panel.loc[panel["ticker"].eq(ticker)]
        eligible = history.loc[history["organic_incremental_roic_proxy_ready"]]
        material = history.loc[
            history["material_acquisition"] | history["material_divestiture"]
        ]
        summary_rows.append(
            {
                "ticker": ticker,
                "annual_rows": len(history),
                "material_mna_years": len(material),
                "material_mna_proxy_ready_years": int(
                    material["material_mna_year_proxy_ready"].sum()
                ),
                "organic_diagnostic_years": len(eligible),
                "organic_incremental_roic_after_tax_proxy_q50_pct": (
                    float(
                        eligible[
                            "organic_incremental_roic_after_tax_proxy_pct"
                        ].median()
                    )
                    if len(eligible) >= 3
                    else np.nan
                ),
                "organic_company_roic_validated": False,
                "terminal_input_allowed": False,
                "status": (
                    "DIAGNOSTIC_PROXY_AVAILABLE_NOT_VALIDATED"
                    if len(eligible) >= 1
                    else "LOCKED_NO_ELIGIBLE_ORGANIC_ROIC_PROXY"
                ),
            }
        )
    summary = pd.DataFrame(summary_rows)
    return {
        "mna_event_capital_and_numerator_evidence": events,
        "annual_organic_company_economics": panel.sort_values(
            ["ticker", "year"]
        ).reset_index(drop=True),
        "organic_company_economics_summary": summary,
    }
