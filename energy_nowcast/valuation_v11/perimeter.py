from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..valuation.financials import ENERGY_TICKERS, _coalesce_instant


NONCONTROLLING_INTEREST_OPTIONS = (
    "NoncontrollingInterestInConsolidatedEntity",
    "MinorityInterest",
    "RedeemableNoncontrollingInterestEquityCarryingAmount",
)
PREFERRED_STOCK_OPTIONS = (
    "PreferredStocksIncludingAdditionalPaidInCapital",
    "PreferredStockValue",
    "PreferredStockCarryingValue",
)
OPERATING_LEASE_CURRENT_OPTIONS = ("OperatingLeaseLiabilityCurrent",)
OPERATING_LEASE_NONCURRENT_OPTIONS = ("OperatingLeaseLiabilityNoncurrent",)
FINANCE_LEASE_CURRENT_OPTIONS = (
    "FinanceLeaseLiabilityCurrent",
    "CapitalLeaseObligationsCurrent",
)
FINANCE_LEASE_NONCURRENT_OPTIONS = (
    "FinanceLeaseLiabilityNoncurrent",
    "CapitalLeaseObligationsNoncurrent",
)
CONDITIONAL_DEBT_REFERENCE_OPTIONS = (
    "LongTermDebt",
    "LongTermDebtNoncurrent",
    "UnsecuredLongTermDebt",
    "ConvertibleDebtNoncurrent",
)


def _latest_metric(
    companyfacts_root: Path,
    ticker: str,
    options: tuple[str, ...],
    value_name: str,
    maximum_ordinal: int,
) -> dict[str, object]:
    frame = _coalesce_instant(companyfacts_root, ticker, options, value_name)
    if frame.empty:
        return {
            value_name: 0.0,
            f"{value_name}_source_tag": "UNAVAILABLE_ASSUMED_ZERO_FOR_RECONCILIATION",
            f"{value_name}_available_at": pd.NaT,
        }
    eligible = frame.loc[frame["quarter_ordinal"].le(maximum_ordinal)].sort_values(
        "quarter_ordinal"
    )
    if eligible.empty:
        return {
            value_name: 0.0,
            f"{value_name}_source_tag": "UNAVAILABLE_ASSUMED_ZERO_FOR_RECONCILIATION",
            f"{value_name}_available_at": pd.NaT,
        }
    row = eligible.iloc[-1]
    return {
        value_name: float(row[value_name]),
        f"{value_name}_source_tag": row[f"{value_name}_source_tag"],
        f"{value_name}_available_at": row[f"{value_name}_available_at"],
    }


def _adjusted_debt(row: pd.Series) -> tuple[float, str]:
    current = float(row.get("current_debt_usd", 0.0) or 0.0)
    long_term = float(row.get("noncurrent_debt_usd", 0.0) or 0.0)
    tag = str(row.get("noncurrent_debt_usd_source_tag", ""))
    total_concepts = (
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
    )
    if any(tag.endswith(concept) for concept in total_concepts):
        return max(long_term, current), "TOTAL_DEBT_CONCEPT_NO_CURRENT_DOUBLE_COUNT"
    return current + long_term, "CURRENT_PLUS_EXPLICIT_NONCURRENT_DEBT"


def build_adjusted_market(
    market: pd.DataFrame,
    companyfacts_root: Path,
    tickers: tuple[str, ...] = ENERGY_TICKERS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconcile the operating-asset EV perimeter to common equity.

    Noncontrolling interest and preferred claims are included when standardized
    Companyfacts tags exist. Operating leases are disclosed but not capitalized
    because the common EBIT/FCFF bridge has not reversed lease expense.
    """
    supplemental_rows: list[dict[str, object]] = []
    market_lookup = market.set_index("ticker")
    metrics = (
        (NONCONTROLLING_INTEREST_OPTIONS, "noncontrolling_interest_usd"),
        (PREFERRED_STOCK_OPTIONS, "preferred_stock_usd"),
        (OPERATING_LEASE_CURRENT_OPTIONS, "operating_lease_current_usd"),
        (OPERATING_LEASE_NONCURRENT_OPTIONS, "operating_lease_noncurrent_usd"),
        (FINANCE_LEASE_CURRENT_OPTIONS, "finance_lease_current_usd"),
        (FINANCE_LEASE_NONCURRENT_OPTIONS, "finance_lease_noncurrent_usd"),
        (CONDITIONAL_DEBT_REFERENCE_OPTIONS, "conditional_debt_reference_usd"),
    )
    for ticker in tickers:
        current = market_lookup.loc[ticker]
        row: dict[str, object] = {"ticker": ticker}
        for options, value_name in metrics:
            row.update(
                _latest_metric(
                    companyfacts_root,
                    ticker,
                    options,
                    value_name,
                    int(current["quarter_ordinal"]),
                )
            )
        supplemental_rows.append(row)
    supplemental = pd.DataFrame(supplemental_rows)
    adjusted = market.merge(supplemental, on="ticker", how="left", validate="one_to_one")
    debt = adjusted.apply(_adjusted_debt, axis=1, result_type="expand")
    adjusted["adjusted_total_debt_usd"] = pd.to_numeric(debt[0], errors="coerce")
    adjusted["debt_semantics_method"] = debt[1]
    debt_taxonomy_gap = (
        adjusted["adjusted_total_debt_usd"].le(0)
        & adjusted["conditional_debt_reference_usd"].gt(0)
    )
    adjusted.loc[debt_taxonomy_gap, "adjusted_total_debt_usd"] = adjusted.loc[
        debt_taxonomy_gap, "conditional_debt_reference_usd"
    ]
    adjusted.loc[debt_taxonomy_gap, "debt_semantics_method"] = (
        "PIT_LAST_DISCLOSED_DEBT_CARRY_FORWARD_TAXONOMY_GAP"
    )
    adjusted["debt_double_count_adjustment_usd"] = (
        adjusted["total_debt_usd"] - adjusted["adjusted_total_debt_usd"]
    )
    adjusted["operating_lease_liability_usd"] = (
        adjusted["operating_lease_current_usd"]
        + adjusted["operating_lease_noncurrent_usd"]
    )
    adjusted["finance_lease_liability_usd"] = (
        adjusted["finance_lease_current_usd"]
        + adjusted["finance_lease_noncurrent_usd"]
    )
    adjusted["lease_valuation_treatment"] = (
        "DISCLOSED_NOT_ADDED_TO_EV_TO_AVOID_LEASE_EXPENSE_DOUBLE_COUNT"
    )
    adjusted["nonoperating_assets_usd"] = 0.0
    adjusted["nonoperating_assets_method"] = (
        "CASH_ONLY_NO_STANDARDIZED_CROSS_COMPANY_NONOPERATING_ASSET_TAG"
    )
    adjusted["market_cap_recalculated_usd"] = (
        adjusted["market_price"] * adjusted["shares_outstanding"]
    )
    adjusted["market_cap_reconciliation_error_usd"] = (
        adjusted["market_cap_usd"] - adjusted["market_cap_recalculated_usd"]
    )
    adjusted["adjusted_net_debt_usd"] = (
        adjusted["adjusted_total_debt_usd"] - adjusted["cash_usd"]
    )
    adjusted["market_enterprise_value_adjusted_usd"] = (
        adjusted["market_cap_usd"]
        + adjusted["adjusted_total_debt_usd"]
        + adjusted["noncontrolling_interest_usd"]
        + adjusted["preferred_stock_usd"]
        - adjusted["cash_usd"]
        - adjusted["nonoperating_assets_usd"]
    )
    adjusted["market_common_equity_reconstructed_usd"] = (
        adjusted["market_enterprise_value_adjusted_usd"]
        - adjusted["adjusted_total_debt_usd"]
        - adjusted["noncontrolling_interest_usd"]
        - adjusted["preferred_stock_usd"]
        + adjusted["cash_usd"]
        + adjusted["nonoperating_assets_usd"]
    )
    adjusted["ev_equity_reconciliation_error_usd"] = (
        adjusted["market_common_equity_reconstructed_usd"]
        - adjusted["market_cap_usd"]
    )
    capital = adjusted["market_cap_usd"] + adjusted["adjusted_total_debt_usd"]
    adjusted["adjusted_equity_weight"] = adjusted["market_cap_usd"] / capital
    adjusted["adjusted_debt_weight"] = adjusted["adjusted_total_debt_usd"] / capital
    adjusted["wacc_adjusted_pct"] = (
        adjusted["adjusted_equity_weight"] * adjusted["cost_of_equity_pct"]
        + adjusted["adjusted_debt_weight"] * adjusted["pre_tax_cost_of_debt_pct"]
        * (1.0 - adjusted["effective_tax_rate"])
    )
    audit_columns = [
        "ticker", "subindustry", "market_price", "shares_outstanding",
        "market_cap_usd", "market_cap_recalculated_usd",
        "market_cap_reconciliation_error_usd", "total_debt_usd",
        "adjusted_total_debt_usd", "debt_double_count_adjustment_usd",
        "debt_semantics_method", "cash_usd", "adjusted_net_debt_usd",
        "conditional_debt_reference_usd",
        "conditional_debt_reference_usd_source_tag",
        "noncontrolling_interest_usd", "preferred_stock_usd",
        "operating_lease_liability_usd", "finance_lease_liability_usd",
        "lease_valuation_treatment", "nonoperating_assets_usd",
        "nonoperating_assets_method", "market_enterprise_value_adjusted_usd",
        "market_common_equity_reconstructed_usd",
        "ev_equity_reconciliation_error_usd", "wacc_pct", "wacc_adjusted_pct",
    ]
    return adjusted, adjusted[audit_columns].copy()
