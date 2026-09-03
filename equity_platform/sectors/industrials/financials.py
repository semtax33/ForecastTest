from __future__ import annotations

from functools import reduce
from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.sec import CompanyFactsReader


FLOW_CONCEPTS = {
    "revenue_usd": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
    ),
    "operating_income_usd": ("OperatingIncomeLoss",),
    "pretax_income_usd": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    "income_tax_usd": ("IncomeTaxExpenseBenefit",),
    "interest_expense_usd": (
        "InterestExpenseNonOperating",
        "InterestExpense",
    ),
    "cfo_usd": (
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        "NetCashProvidedByUsedInOperatingActivities",
    ),
    "capex_usd": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
}
INSTANT_CONCEPTS = {
    "backlog_usd": ("RevenueRemainingPerformanceObligation",),
    "cash_usd": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashCashEquivalentsAndShortTermInvestments",
    ),
    "debt_noncurrent_usd": (
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "LongTermDebtNoncurrent",
    ),
    "debt_current_usd": (
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "LongTermDebtCurrent",
    ),
    "equity_usd": (
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ),
}


def build_annual_financial_bridge(
    companyfacts_path: Path,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    reader = CompanyFactsReader(companyfacts_path)
    frames = [
        reader.annual_flow(concepts, name, cutoff)
        for name, concepts in FLOW_CONCEPTS.items()
    ]
    frames.extend(
        reader.annual_instant(concepts, name, cutoff)
        for name, concepts in INSTANT_CONCEPTS.items()
    )
    frame = reduce(
        lambda left, right: left.merge(right, on="fiscal_year", how="outer"),
        frames,
    ).sort_values("fiscal_year")
    value_columns = tuple(FLOW_CONCEPTS) + tuple(INSTANT_CONCEPTS)
    for column in value_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("debt_current_usd", "debt_noncurrent_usd"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    frame["total_debt_usd"] = frame["debt_current_usd"] + frame["debt_noncurrent_usd"]
    reported_tax_rate = frame["income_tax_usd"] / frame["pretax_income_usd"]
    valid_tax = reported_tax_rate.between(0.0, 0.50) & frame["pretax_income_usd"].gt(0)
    frame["effective_tax_rate"] = reported_tax_rate.where(valid_tax, 0.21)
    frame["tax_rate_method"] = np.where(
        valid_tax,
        "DIRECT_ANNUAL_TAX_OVER_PRETAX_INCOME",
        "US_STATUTORY_21PCT_FALLBACK_INVALID_OR_NONPOSITIVE_PRETAX",
    )
    frame["nopat_usd"] = frame["operating_income_usd"] * (
        1.0 - frame["effective_tax_rate"]
    )
    frame["fcff_usd"] = (
        frame["cfo_usd"]
        + frame["interest_expense_usd"].fillna(0.0)
        * (1.0 - frame["effective_tax_rate"])
        - frame["capex_usd"]
    )
    frame["invested_capital_usd"] = (
        frame["equity_usd"] + frame["total_debt_usd"] - frame["cash_usd"]
    )
    frame["average_invested_capital_usd"] = (
        frame["invested_capital_usd"]
        + frame["invested_capital_usd"].shift(1)
    ) / 2.0
    frame["revenue_growth_pct"] = frame["revenue_usd"].pct_change() * 100.0
    frame["backlog_growth_pct"] = frame["backlog_usd"].pct_change() * 100.0
    frame["operating_margin_pct"] = (
        frame["operating_income_usd"] / frame["revenue_usd"] * 100.0
    )
    frame["fcff_margin_pct"] = frame["fcff_usd"] / frame["revenue_usd"] * 100.0
    frame["roic_pct"] = (
        frame["nopat_usd"] / frame["average_invested_capital_usd"] * 100.0
    )
    availability = [column for column in frame if column.endswith("_available_at")]
    availability_frame = frame[availability].apply(
        lambda values: pd.to_datetime(values, errors="coerce")
    )
    frame["financial_available_at"] = availability_frame.max(axis=1)
    frame["ticker"] = "CAT"
    frame["sector"] = "Industrials"
    frame["subindustry"] = "Machinery"
    frame["primary_anchor"] = "ORDERS_BACKLOG_SHIPMENTS"
    frame["anchor_source"] = "SEC_REVENUE_REMAINING_PERFORMANCE_OBLIGATION"
    frame["financial_complete"] = frame[
        [
            "revenue_usd",
            "operating_income_usd",
            "cfo_usd",
            "capex_usd",
            "invested_capital_usd",
        ]
    ].notna().all(axis=1)
    return frame.reset_index(drop=True)
