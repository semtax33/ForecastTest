from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.sectors.industrials.segments import _find_row, _find_table, _group_value


def _value(table: pd.DataFrame, labels: list[str]) -> float:
    available = {str(value) for value in table.iloc[:, 0].dropna()}
    label = next((candidate for candidate in labels if candidate in available), None)
    if label is None:
        raise ValueError(f"CAT capex row not found: {labels}")
    return _group_value(_find_row(table, label), 0)


def build_segment_capex_history(cat_sources: pd.DataFrame) -> dict[str, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    for _, source in cat_sources.iterrows():
        table = _find_table(pd.read_html(Path(source["resolved_path"])), "Reconciliation of Capital expenditures:")
        if table is None:
            raise ValueError(f"CAT segment capex table missing: {source['resolved_path']}")
        total = _value(table, ["Total capital expenditures"])
        financial_products = _value(table, ["Financial Products Segment"])
        rows.append(
            {
                "fiscal_year": int(source["fiscal_year"]),
                "filing_date": source["filing_date"].date().isoformat(),
                "construction_capex_usd": _value(table, ["Construction Industries"]),
                "resource_capex_usd": _value(table, ["Resource Industries"]),
                "power_energy_capex_usd": _value(table, ["Power & Energy", "Energy & Transportation"]),
                "financial_products_capex_usd": financial_products,
                "all_other_capex_usd": _value(table, ["All Other Segment", "All Other operating segment"]),
                "total_capex_usd": total,
                "mpe_capex_proxy_usd": total - financial_products,
                "source_url": source["source_url"],
                "source_sha256": source["source_sha256"],
                "capex_semantics": "TOTAL_CAPEX_LESS_FINANCIAL_PRODUCTS_NOT_EQUAL_TO_NET_REINVESTMENT",
            }
        )
    history = pd.DataFrame(rows).sort_values("fiscal_year").reset_index(drop=True)
    latest = history.iloc[-1]
    summary = pd.DataFrame(
        [
            {
                "history_years": len(history),
                "first_fiscal_year": int(history.iloc[0]["fiscal_year"]),
                "latest_fiscal_year": int(latest["fiscal_year"]),
                "latest_total_capex_usd": latest["total_capex_usd"],
                "latest_financial_products_capex_usd": latest["financial_products_capex_usd"],
                "latest_mpe_capex_proxy_usd": latest["mpe_capex_proxy_usd"],
                "net_reinvestment_identity_claim_allowed": False,
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return {"segment_capex_history": history, "segment_capex_summary": summary}
