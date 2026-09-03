from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.sectors.industrials.segments import (
    CASH_FLOW_ROWS,
    POSITION_ROWS,
    RESULT_ROWS,
    _entity_values,
    _find_table,
    _group_value,
    _find_row,
    _normalize_label,
)


def _cat_prior_values(source: pd.Series) -> dict[str, float]:
    tables = pd.read_html(Path(source["resolved_path"]))
    results = _find_table(tables, "Supplemental Data for Results of Operations")
    position = _find_table(tables, "Supplemental Data for Financial Position")
    cashflow = _find_table(tables, "Supplemental Data for Cash Flow")
    if results is None or position is None:
        raise ValueError("CAT supplemental prior-period tables missing")
    values = {
        **_entity_values(results, RESULT_ROWS, periods_per_entity=3, period_slot=1),
        **_entity_values(position, POSITION_ROWS, periods_per_entity=2, period_slot=1),
    }
    if cashflow is not None:
        values.update(_entity_values(cashflow, CASH_FLOW_ROWS, periods_per_entity=2, period_slot=1))
    return values


def _cfsc_prior_values(source: pd.Series) -> dict[str, float]:
    tables = pd.read_html(Path(source["resolved_path"]))
    income_matches = [table for table in tables if {"Retail finance", "Interest", "Total revenues"}.issubset({_normalize_label(value) for value in table.iloc[:, 0].dropna()})]
    balance_matches = [table for table in tables if {"Cash and cash equivalents", "Short-term borrowings", "Total assets"}.issubset({_normalize_label(value) for value in table.iloc[:, 0].dropna()})]
    income = max(income_matches, key=lambda table: table.shape[1]) if income_matches else None
    balance = max(balance_matches, key=lambda table: table.shape[1]) if balance_matches else None
    if income is None or balance is None:
        raise ValueError("CFSC prior-period statements missing")
    income_rows = {
        "total_revenue_usd": "Total revenues",
        "interest_expense_usd": "Interest",
        "credit_loss_provision_usd": "Provision for credit losses",
        "pretax_profit_usd": "Profit before income taxes",
    }
    balance_rows = {
        "cash_usd": "Cash and cash equivalents",
        "short_term_borrowings_usd": "Short-term borrowings",
        "current_debt_usd": "Current maturities of long-term debt",
        "long_term_debt_usd": "Long-term debt",
        "standalone_equity_usd": "Total shareholder’s equity",
    }
    profit_labels = {_normalize_label(value) for value in income.iloc[:, 0].dropna()}
    profit_label = next(label for label in ["Profit attributable to Caterpillar Financial Services Corporation", "Profit(1)", "Profit"] if label in profit_labels)
    return {
        **{key: _group_value(_find_row(income, label), 1) for key, label in income_rows.items()},
        "standalone_profit_usd": _group_value(_find_row(income, profit_label), 1),
        **{key: _group_value(_find_row(balance, label), 1) for key, label in balance_rows.items()},
    }


def build_parser_quality_audit(
    *,
    cat_sources: pd.DataFrame,
    cat_segments: pd.DataFrame,
    cat_backlog: pd.DataFrame,
    cfsc_sources: pd.DataFrame,
    cfsc_history: pd.DataFrame,
    tolerance_usd: float,
) -> dict[str, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    cat_current = cat_segments.set_index("fiscal_year")
    for _, source in cat_sources.iloc[1:].iterrows():
        prior_year = int(source["fiscal_year"]) - 1
        for metric, repeated in _cat_prior_values(source).items():
            if metric.startswith("adjustments_"):
                continue
            original = float(cat_current.loc[prior_year, metric])
            if pd.isna(original):
                continue
            rows.append({"issuer": "CAT", "filing_year": int(source["fiscal_year"]), "referenced_year": prior_year, "metric": metric, "original_filing_value_usd": original, "repeated_value_usd": repeated, "difference_usd": repeated - original})
    cfsc_current = cfsc_history.set_index("fiscal_year")
    for _, source in cfsc_sources.iloc[1:].iterrows():
        prior_year = int(source["fiscal_year"]) - 1
        for metric, repeated in _cfsc_prior_values(source).items():
            original = float(cfsc_current.loc[prior_year, metric])
            rows.append({"issuer": "CFSC", "filing_year": int(source["fiscal_year"]), "referenced_year": prior_year, "metric": metric, "original_filing_value_usd": original, "repeated_value_usd": repeated, "difference_usd": repeated - original})
    cross = pd.DataFrame(rows)
    cross["within_tolerance"] = cross["difference_usd"].abs().le(tolerance_usd)
    latest_cat = cat_segments.iloc[-1]
    latest_backlog = cat_backlog.iloc[-1]
    latest_cfsc = cfsc_history.iloc[-1]
    gold_specs = [
        ("CAT", "mpe_total_revenue_usd", latest_cat["mpe_total_revenue_usd"], 63.980e9),
        ("CAT", "financial_products_total_revenue_usd", latest_cat["financial_products_total_revenue_usd"], 4.382e9),
        ("CAT", "firm_backlog_usd", latest_backlog["firm_backlog_usd"], 51.2e9),
        ("CAT", "not_expected_next_year_usd", latest_backlog["not_expected_next_year_usd"], 19.3e9),
        ("CFSC", "total_revenue_usd", latest_cfsc["total_revenue_usd"], 3.634e9),
        ("CFSC", "standalone_profit_usd", latest_cfsc["standalone_profit_usd"], 540e6),
        ("CFSC", "finance_receivables_net_usd", latest_cfsc["finance_receivables_net_usd"], 32.815e9),
        ("CFSC", "standalone_equity_usd", latest_cfsc["standalone_equity_usd"], 3.227e9),
    ]
    gold = pd.DataFrame(
        [
            {"issuer": issuer, "fiscal_year": 2025, "metric": metric, "parsed_value_usd": parsed, "gold_value_usd": expected, "difference_usd": parsed - expected, "gold_match": abs(parsed - expected) <= tolerance_usd}
            for issuer, metric, parsed, expected in gold_specs
        ]
    )
    summary = pd.DataFrame(
        [
            {
                "cross_filing_cells": len(cross),
                "cross_filing_exact_matches": int(cross["within_tolerance"].sum()),
                "cross_filing_mismatches": int((~cross["within_tolerance"]).sum()),
                "gold_cells": len(gold),
                "gold_matches": int(gold["gold_match"].sum()),
                "parser_quality_gate_pass": bool(cross["within_tolerance"].all() and gold["gold_match"].all()),
                "manual_source_excerpt_review_required": True,
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return {"parser_cross_filing_audit": cross, "parser_gold_cell_audit": gold, "parser_quality_summary": summary}
