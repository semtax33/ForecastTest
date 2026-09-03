from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.sectors.industrials.segments import _find_row, _group_value, _normalize_label


def load_cfsc_sources(root: Path, catalog_path: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    sources = pd.read_csv(catalog_path)
    sources["fiscal_year"] = pd.to_numeric(sources["fiscal_year"], errors="raise").astype(int)
    sources["filing_date"] = pd.to_datetime(sources["filing_date"], errors="raise")
    sources = sources.loc[sources["filing_date"].le(cutoff)].copy()
    sources["resolved_path"] = sources["local_path"].map(lambda value: str((root / value).resolve()))
    missing = [path for path in sources["resolved_path"] if not Path(path).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing CFSC 10-K sources: {missing}")
    sources["source_sha256"] = sources["resolved_path"].map(lambda value: sha256_file(Path(value)))
    sources["source_authority"] = "SEC_EDGAR_CFSC_10_K"
    sources["point_in_time_eligible"] = True
    return sources.sort_values("fiscal_year").reset_index(drop=True)


def _value(table: pd.DataFrame, label: str, group: int = 0) -> float:
    return _group_value(_find_row(table, label), group)


def _table_with_labels(tables: list[pd.DataFrame], required: set[str]) -> pd.DataFrame | None:
    matches: list[pd.DataFrame] = []
    for table in tables:
        labels = {_normalize_label(value) for value in table.iloc[:, 0].dropna()}
        if required.issubset(labels):
            matches.append(table)
    return max(matches, key=lambda table: table.shape[1]) if matches else None


def _first_value(table: pd.DataFrame, labels: list[str], group: int = 0) -> float:
    available = {_normalize_label(value) for value in table.iloc[:, 0].dropna()}
    for label in labels:
        if label in available:
            return _value(table, label, group)
    raise ValueError(f"None of the CFSC labels were present: {labels}")


def _parse_cfsc(source: pd.Series) -> dict[str, object]:
    tables = pd.read_html(Path(source["resolved_path"]))
    income = _table_with_labels(tables, {"Retail finance", "Interest", "Total revenues"})
    balance = _table_with_labels(tables, {"Cash and cash equivalents", "Short-term borrowings", "Total assets"})
    cashflow = _table_with_labels(tables, {"Dividend paid to Caterpillar", "Net cash provided by operating activities"})
    if income is None or balance is None or cashflow is None:
        raise ValueError(f"CFSC standalone statements missing: {source['resolved_path']}")
    finance_receivable_label = next(
        str(value)
        for value in balance.iloc[:, 0].dropna()
        if str(value).lower().startswith("finance receivables, net of allowance")
    )
    allowance_match = re.search(r"\$([\d,]+)", finance_receivable_label)
    if allowance_match is None:
        raise ValueError("CFSC allowance amount was not present in balance-sheet label")
    labels = {
        "retail_finance_revenue_usd": "Retail finance",
        "operating_lease_revenue_usd": "Operating lease",
        "wholesale_finance_revenue_usd": "Wholesale finance",
        "other_revenue_usd": "Other, net",
        "total_revenue_usd": "Total revenues",
        "interest_expense_usd": "Interest",
        "leased_equipment_depreciation_usd": "Depreciation on equipment leased to others",
        "general_operating_admin_usd": "General, operating and administrative",
        "credit_loss_provision_usd": "Provision for credit losses",
        "total_expense_usd": "Total expenses",
        "pretax_profit_usd": "Profit before income taxes",
    }
    parsed: dict[str, object] = {
        "fiscal_year": int(source["fiscal_year"]),
        "filing_date": source["filing_date"].date().isoformat(),
        "source_url": source["source_url"],
        "source_sha256": source["source_sha256"],
        **{key: _value(income, label) for key, label in labels.items()},
        "income_tax_usd": _first_value(income, ["Provision (benefit) for income taxes", "Provision for income taxes"]),
        "standalone_profit_usd": _first_value(income, ["Profit attributable to Caterpillar Financial Services Corporation", "Profit(1)", "Profit"]),
        "cash_usd": _value(balance, "Cash and cash equivalents"),
        "finance_receivables_net_usd": _value(balance, finance_receivable_label),
        "allowance_credit_losses_usd": float(allowance_match.group(1).replace(",", "")) * 1e6,
        "operating_lease_assets_net_usd": _value(balance, "Equipment on operating leases, net"),
        "short_term_borrowings_usd": _value(balance, "Short-term borrowings"),
        "current_debt_usd": _value(balance, "Current maturities of long-term debt"),
        "long_term_debt_usd": _value(balance, "Long-term debt"),
        "standalone_equity_usd": _value(balance, "Total shareholder’s equity"),
        "dividend_to_parent_usd": abs(_value(cashflow, "Dividend paid to Caterpillar")),
    }
    return parsed


def build_cfsc_economics(
    sources: pd.DataFrame, cat_segment_history: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    history = pd.DataFrame([_parse_cfsc(row) for _, row in sources.iterrows()]).sort_values("fiscal_year")
    history["finance_receivables_gross_usd"] = history["finance_receivables_net_usd"] + history["allowance_credit_losses_usd"]
    history["standalone_funding_debt_usd"] = (
        history["short_term_borrowings_usd"] + history["current_debt_usd"] + history["long_term_debt_usd"]
    )
    history["average_finance_receivables_usd"] = history["finance_receivables_net_usd"].rolling(2).mean()
    history["average_funding_debt_usd"] = history["standalone_funding_debt_usd"].rolling(2).mean()
    history["average_equity_usd"] = history["standalone_equity_usd"].rolling(2).mean()
    history["financing_revenue_usd"] = history["retail_finance_revenue_usd"] + history["wholesale_finance_revenue_usd"]
    history["financing_yield_pct"] = history["financing_revenue_usd"] / history["average_finance_receivables_usd"] * 100.0
    history["funding_cost_pct"] = history["interest_expense_usd"] / history["average_funding_debt_usd"] * 100.0
    history["net_finance_spread_pct"] = history["financing_yield_pct"] - history["funding_cost_pct"]
    history["credit_loss_rate_pct"] = history["credit_loss_provision_usd"] / history["average_finance_receivables_usd"] * 100.0
    history["allowance_coverage_pct"] = history["allowance_credit_losses_usd"] / history["finance_receivables_gross_usd"] * 100.0
    history["standalone_roe_pct"] = history["standalone_profit_usd"] / history["average_equity_usd"] * 100.0
    history["payout_ratio_pct"] = history["dividend_to_parent_usd"] / history["standalone_profit_usd"] * 100.0
    history["retention_ratio_pct"] = 100.0 - history["payout_ratio_pct"]
    history["sustainable_equity_growth_pct"] = history["standalone_roe_pct"] * history["retention_ratio_pct"] / 100.0
    segment = cat_segment_history[["fiscal_year", "financial_products_profit_usd", "financial_products_equity_usd"]]
    history = history.merge(segment, on="fiscal_year", how="left", validate="one_to_one")
    history["segment_minus_cfsc_profit_usd"] = history["financial_products_profit_usd"] - history["standalone_profit_usd"]
    history["segment_minus_cfsc_equity_usd"] = history["financial_products_equity_usd"] - history["standalone_equity_usd"]
    history["perimeter_status"] = "CFSC_EXACT_STANDALONE_WITH_CAT_FP_RECONCILING_RESIDUAL"
    latest = history.iloc[-1]
    audit = pd.DataFrame(
        [
            {
                "fiscal_year": int(latest["fiscal_year"]),
                "cfsc_standalone_profit_usd": latest["standalone_profit_usd"],
                "cat_financial_products_profit_usd": latest["financial_products_profit_usd"],
                "broader_fp_reconciling_profit_usd": latest["segment_minus_cfsc_profit_usd"],
                "reconciling_profit_attribution_identified": False,
                "cfsc_standalone_equity_usd": latest["standalone_equity_usd"],
                "cat_financial_products_equity_usd": latest["financial_products_equity_usd"],
                "perimeter_equity_difference_usd": latest["segment_minus_cfsc_equity_usd"],
                "financing_yield_pct": latest["financing_yield_pct"],
                "funding_cost_pct": latest["funding_cost_pct"],
                "net_finance_spread_pct": latest["net_finance_spread_pct"],
                "credit_loss_rate_pct": latest["credit_loss_rate_pct"],
                "standalone_roe_pct": latest["standalone_roe_pct"],
                "payout_ratio_pct": latest["payout_ratio_pct"],
                "exact_cfsc_economics_available": True,
                "whole_fp_exact_economics_available": False,
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return {"cfsc_standalone_economics_history": history.reset_index(drop=True), "financial_products_perimeter_audit": audit}
