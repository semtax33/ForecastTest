from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import pandas as pd


RESULT_ROWS = {
    "total_revenue_usd": "Total sales and revenues",
    "operating_profit_usd": "Operating profit",
    "interest_expense_usd": "Interest expense excluding Financial Products",
    "fp_interest_expense_usd": "Interest expense of Financial Products",
    "pretax_profit_usd": "Consolidated profit before taxes",
    "income_tax_usd": "Provision (benefit) for income taxes",
    "profit_usd": "Profit of consolidated and affiliated companies",
}
POSITION_ROWS = {
    "cash_usd": "Cash and cash equivalents",
    "finance_receivables_current_usd": "Receivables - finance",
    "short_term_borrowings_usd": "Short-term borrowings",
    "debt_current_usd": "Long-term debt due within one year",
    "debt_noncurrent_usd": "Long-term debt due after one year",
    "equity_usd": "Total shareholders’ equity",
}
CASH_FLOW_ROWS = {
    "cfo_usd": "Net cash provided by (used for) operating activities",
    "capex_excluding_leased_equipment_usd": (
        "Capital expenditures - excluding equipment leased to others"
    ),
}
ENTITY_INDEX = {"consolidated": 0, "mpe": 1, "financial_products": 2, "adjustments": 3}
_FOOTNOTE_SUFFIX = re.compile(r"\d+$")


def _normalize_label(value: object) -> str:
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def _money(value: object) -> float | None:
    if pd.isna(value):
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if text in {"", "—", "-", "nan"}:
        return 0.0 if text in {"—", "-"} else None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        result = float(text)
    except ValueError:
        return None
    return -result if negative else result


def _find_table(tables: list[pd.DataFrame], phrase: str) -> pd.DataFrame | None:
    for table in tables:
        labels = table.iloc[:, 0].dropna().map(_normalize_label)
        if any(phrase in label for label in labels):
            return table
    return None


def _find_row(table: pd.DataFrame, label: str) -> pd.Series:
    labels = table.iloc[:, 0].map(_normalize_label)
    matches = labels.eq(label)
    if not matches.any():
        matches = labels.map(lambda value: _FOOTNOTE_SUFFIX.sub("", value)).eq(label)
    if not matches.any():
        raise ValueError(f"CAT supplemental row not found: {label}")
    return table.loc[matches].iloc[0]


def _group_value(row: pd.Series, group_index: int) -> float:
    # CAT's rendered SEC tables reserve three label columns followed by six
    # columns per period/entity cell.  The amount may appear once or twice.
    start = 3 + group_index * 6
    values = [_money(value) for value in row.iloc[start : start + 6]]
    parsed = [value for value in values if value is not None]
    if not parsed:
        raise ValueError(f"CAT supplemental amount missing in group {group_index}")
    return float(parsed[0]) * 1e6


def _entity_values(
    table: pd.DataFrame,
    rows: dict[str, str],
    *,
    periods_per_entity: int,
    period_slot: int = 0,
) -> dict[str, float]:
    output: dict[str, float] = {}
    for metric, label in rows.items():
        row = _find_row(table, label)
        for entity, entity_index in ENTITY_INDEX.items():
            group = entity_index * periods_per_entity + period_slot
            output[f"{entity}_{metric}"] = _group_value(row, group)
    return output


def _credit_quality(tables: list[pd.DataFrame]) -> dict[str, float]:
    table = _find_table(tables, "Allowance for Credit Losses:")
    if table is None:
        return {}
    provision = _find_row(table, "Provision for credit losses")
    allowance = _find_row(table, "Ending balance")
    receivables = _find_row(table, "Finance Receivables")
    # Groups are current/prior Customer, Dealer and Total. Group 2 is the
    # current-year total across customer and dealer receivables.
    return {
        "fp_credit_loss_provision_usd": _group_value(provision, 2),
        "fp_credit_loss_allowance_usd": _group_value(allowance, 2),
        "fp_finance_receivables_total_usd": _group_value(receivables, 2),
    }


def parse_cat_supplemental_segments(source: pd.Series) -> dict[str, object]:
    path = Path(str(source["resolved_path"]))
    tables = pd.read_html(path)
    results = _find_table(tables, "Supplemental Data for Results of Operations")
    position = _find_table(tables, "Supplemental Data for Financial Position")
    if results is None or position is None:
        raise ValueError(f"CAT supplemental segment tables not found: {path}")
    parsed: dict[str, object] = {
        "fiscal_year": int(source["fiscal_year"]),
        "filing_date": pd.Timestamp(source["filing_date"]).date().isoformat(),
        "source_url": source["source_url"],
        "source_path": str(path),
        "source_sha256": source["source_sha256"],
        "segment_semantics": "MPE_OR_LEGACY_MET_NON_FINANCIAL_VS_FINANCIAL_PRODUCTS",
    }
    parsed.update(_entity_values(results, RESULT_ROWS, periods_per_entity=3))
    parsed.update(_entity_values(position, POSITION_ROWS, periods_per_entity=2))
    cash_flow = _find_table(tables, "Supplemental Data for Cash Flow")
    if cash_flow is not None:
        parsed.update(_entity_values(cash_flow, CASH_FLOW_ROWS, periods_per_entity=2))
    parsed.update(_credit_quality(tables))
    return parsed


def build_cat_segment_history(sources: pd.DataFrame) -> pd.DataFrame:
    history = pd.DataFrame(
        [parse_cat_supplemental_segments(row) for _, row in sources.iterrows()]
    ).sort_values("fiscal_year")
    history["mpe_total_debt_usd"] = (
        history["mpe_short_term_borrowings_usd"]
        + history["mpe_debt_current_usd"]
        + history["mpe_debt_noncurrent_usd"]
    )
    history["fp_funding_debt_usd"] = (
        history["financial_products_short_term_borrowings_usd"]
        + history["financial_products_debt_current_usd"]
        + history["financial_products_debt_noncurrent_usd"]
    )
    history["mpe_operating_margin_pct"] = (
        history["mpe_operating_profit_usd"] / history["mpe_total_revenue_usd"] * 100.0
    )
    reported_tax = history["mpe_income_tax_usd"] / history["mpe_pretax_profit_usd"]
    history["mpe_effective_tax_rate_pct"] = reported_tax.where(
        reported_tax.between(0.0, 0.50), 0.21
    ) * 100.0
    history["mpe_nopat_usd"] = history["mpe_operating_profit_usd"] * (
        1.0 - history["mpe_effective_tax_rate_pct"] / 100.0
    )
    history["mpe_invested_capital_usd"] = (
        history["mpe_equity_usd"]
        + history["mpe_total_debt_usd"]
        - history["mpe_cash_usd"]
    )
    history["mpe_average_invested_capital_usd"] = (
        history["mpe_invested_capital_usd"]
        + history["mpe_invested_capital_usd"].shift(1)
    ) / 2.0
    history["mpe_roic_pct"] = (
        history["mpe_nopat_usd"]
        / history["mpe_average_invested_capital_usd"]
        * 100.0
    )
    history["fp_average_equity_usd"] = (
        history["financial_products_equity_usd"]
        + history["financial_products_equity_usd"].shift(1)
    ) / 2.0
    history["fp_roe_pct"] = (
        history["financial_products_profit_usd"]
        / history["fp_average_equity_usd"]
        * 100.0
    )
    history["fp_average_funding_debt_usd"] = (
        history["fp_funding_debt_usd"] + history["fp_funding_debt_usd"].shift(1)
    ) / 2.0
    history["fp_funding_cost_proxy_pct"] = (
        history["financial_products_fp_interest_expense_usd"]
        / history["fp_average_funding_debt_usd"]
        * 100.0
    )
    history["fp_average_finance_receivables_usd"] = (
        history["fp_finance_receivables_total_usd"]
        + history["fp_finance_receivables_total_usd"].shift(1)
    ) / 2.0
    history["fp_revenue_yield_proxy_pct"] = (
        history["financial_products_total_revenue_usd"]
        / history["fp_average_finance_receivables_usd"]
        * 100.0
    )
    history["fp_funding_spread_proxy_pct"] = (
        history["fp_revenue_yield_proxy_pct"] - history["fp_funding_cost_proxy_pct"]
    )
    history["fp_credit_loss_provision_pct_receivables"] = (
        history["fp_credit_loss_provision_usd"]
        / history["fp_finance_receivables_total_usd"]
        * 100.0
    )
    history["fp_credit_loss_allowance_pct_receivables"] = (
        history["fp_credit_loss_allowance_usd"]
        / history["fp_finance_receivables_total_usd"]
        * 100.0
    )
    history["revenue_reconciliation_error_usd"] = (
        history["consolidated_total_revenue_usd"]
        - history["mpe_total_revenue_usd"]
        - history["financial_products_total_revenue_usd"]
        - history["adjustments_total_revenue_usd"]
    )
    history["operating_profit_reconciliation_error_usd"] = (
        history["consolidated_operating_profit_usd"]
        - history["mpe_operating_profit_usd"]
        - history["financial_products_operating_profit_usd"]
        - history["adjustments_operating_profit_usd"]
    )
    history["segment_reconciliation_pass"] = (
        history[
            [
                "revenue_reconciliation_error_usd",
                "operating_profit_reconciliation_error_usd",
            ]
        ]
        .abs()
        .max(axis=1)
        .le(1.0)
    )
    if not history["segment_reconciliation_pass"].all():
        raise ValueError("CAT supplemental segment reconciliation failed")
    return history.reset_index(drop=True)


def build_segment_claim_reconciliation(segment_history: pd.DataFrame) -> pd.DataFrame:
    latest = segment_history.iloc[-1]
    rows = [
        {
            "claim": "CONSOLIDATED_REVENUE",
            "consolidated_usd": latest["consolidated_total_revenue_usd"],
            "mpe_usd": latest["mpe_total_revenue_usd"],
            "financial_products_usd": latest["financial_products_total_revenue_usd"],
            "adjustments_usd": latest["adjustments_total_revenue_usd"],
        },
        {
            "claim": "CONSOLIDATED_OPERATING_PROFIT",
            "consolidated_usd": latest["consolidated_operating_profit_usd"],
            "mpe_usd": latest["mpe_operating_profit_usd"],
            "financial_products_usd": latest["financial_products_operating_profit_usd"],
            "adjustments_usd": latest["adjustments_operating_profit_usd"],
        },
        {
            "claim": "LONG_TERM_DEBT_AFTER_ONE_YEAR",
            "consolidated_usd": latest["consolidated_debt_noncurrent_usd"],
            "mpe_usd": latest["mpe_debt_noncurrent_usd"],
            "financial_products_usd": latest["financial_products_debt_noncurrent_usd"],
            "adjustments_usd": latest["adjustments_debt_noncurrent_usd"],
        },
        {
            "claim": "SHAREHOLDERS_EQUITY",
            "consolidated_usd": latest["consolidated_equity_usd"],
            "mpe_usd": latest["mpe_equity_usd"],
            "financial_products_usd": latest["financial_products_equity_usd"],
            "adjustments_usd": latest["adjustments_equity_usd"],
        },
    ]
    frame = pd.DataFrame(rows)
    frame["reconciliation_error_usd"] = (
        frame["consolidated_usd"]
        - frame["mpe_usd"]
        - frame["financial_products_usd"]
        - frame["adjustments_usd"]
    )
    frame["reconciliation_pass"] = frame["reconciliation_error_usd"].abs().le(1.0)
    return frame
