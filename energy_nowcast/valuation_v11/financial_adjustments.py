from __future__ import annotations

import numpy as np
import pandas as pd

from ..valuation.financials import _fill_hierarchical_capex, build_ttm_financials


SEMANTICALLY_UNSAFE_CAPEX_TAGS = {
    "us-gaap:PaymentsForProceedsFromOtherInvestingActivities",
}


def rebuild_semantically_safe_financials(
    frozen_quarterly: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Replace net payments/proceeds concepts with a disclosed PIT estimate.

    A net investing-activities concept can contain asset-sale proceeds and is
    not a valid gross cash-CapEx observation. The immutable V1.0 source remains
    untouched; V1.1 invalidates those rows before applying the existing
    prior-only same-subindustry distribution bridge.
    """
    quarterly = frozen_quarterly.copy()
    source_tag = quarterly["cash_capex_usd_source_tag"].fillna("").astype(str)
    unsafe = source_tag.map(
        lambda value: any(tag in value for tag in SEMANTICALLY_UNSAFE_CAPEX_TAGS)
    )
    audit = quarterly.loc[unsafe, [
        "ticker", "subindustry", "quarter", "cash_capex_usd",
        "cash_capex_usd_source_tag", "cash_capex_usd_method",
        "cash_capex_usd_available_at",
    ]].copy()
    audit = audit.rename(columns={"cash_capex_usd": "v1_0_cash_capex_usd"})
    audit["v1_0_semantic_status"] = (
        "REJECTED_NET_PAYMENTS_PROCEEDS_CONCEPT_AS_GROSS_CAPEX"
    )
    columns = [
        "cash_capex_usd", "cash_capex_usd_available_at",
        "cash_capex_usd_source_tag", "cash_capex_usd_source_path",
        "cash_capex_usd_method",
    ]
    quarterly.loc[unsafe, columns] = np.nan
    quarterly.loc[unsafe, "cash_capex_imputed"] = False
    quarterly = _fill_hierarchical_capex(quarterly)
    quarterly["fcff_usd"] = (
        quarterly["cfo_usd"]
        + quarterly["interest_expense_usd"]
        * (1.0 - quarterly["effective_tax_rate"])
        - quarterly["cash_capex_usd"]
    )
    quarterly["reinvestment_usd"] = quarterly["nopat_usd"] - quarterly["fcff_usd"]
    quarterly["core_financial_complete"] = quarterly[[
        "revenue", "ebit_usd", "nopat_usd", "cfo_usd",
        "cash_capex_usd", "fcff_usd",
    ]].notna().all(axis=1)
    quarterly["valuation_source_complete"] = (
        quarterly["core_financial_complete"]
        & quarterly["invested_capital_usd"].gt(0)
    )
    availability_columns = [
        column for column in quarterly if column.endswith("_available_at")
    ]
    quarterly["financial_available_at"] = quarterly[
        availability_columns
    ].max(axis=1)
    replacement = quarterly.loc[unsafe, [
        "ticker", "quarter", "cash_capex_usd", "cash_capex_usd_source_tag",
        "cash_capex_usd_method", "cash_capex_imputed",
    ]].rename(columns={
        "cash_capex_usd": "v1_1_cash_capex_usd",
        "cash_capex_usd_source_tag": "v1_1_cash_capex_source_tag",
        "cash_capex_usd_method": "v1_1_cash_capex_method",
        "cash_capex_imputed": "v1_1_cash_capex_imputed",
    })
    audit = audit.merge(replacement, on=["ticker", "quarter"], how="left")
    audit["v1_1_semantic_status"] = np.where(
        audit["v1_1_cash_capex_usd"].notna(),
        "REPLACED_WITH_PRIOR_ONLY_SUBINDUSTRY_DISTRIBUTION",
        "UNRESOLVED_EXCLUDED_FROM_COMPLETE_HISTORY",
    )
    ttm = build_ttm_financials(quarterly)
    return quarterly, ttm, audit


def overlay_latest_financials(
    market: pd.DataFrame,
    ttm: pd.DataFrame,
) -> pd.DataFrame:
    latest = (
        ttm.loc[ttm["ttm_complete"]]
        .sort_values(["ticker", "quarter_ordinal"])
        .groupby("ticker", as_index=False, group_keys=False)
        .tail(1)
        .set_index("ticker")
    )
    result = market.copy().set_index("ticker")
    for column in latest.columns:
        result[column] = latest[column]
    return result.reset_index()
