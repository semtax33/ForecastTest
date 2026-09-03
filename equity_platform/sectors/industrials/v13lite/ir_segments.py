from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.segments import _money, _normalize_label


SEGMENT_ALIASES = {
    "construction": ("Construction Industries",),
    "resource": ("Resource Industries",),
    "power_energy": ("Power & Energy", "Energy & Transportation"),
    "mpe": ("Machinery, Power & Energy", "Machinery, Energy & Transportation"),
}
QUARTERS = {"First": 1, "Second": 2, "Third": 3, "Fourth": 4}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_segment_table(tables: list[pd.DataFrame], phrase: str) -> pd.DataFrame:
    for table in tables:
        labels = table.iloc[:, 0].dropna().map(_normalize_label)
        if any(phrase in label for label in labels):
            return table
    raise ValueError(f"IR segment table not found: {phrase}")


def _row(table: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    labels = table.iloc[:, 0].map(_normalize_label)
    for alias in aliases:
        match = labels.eq(alias)
        if match.any():
            return table.loc[match].iloc[0]
    raise ValueError(f"IR segment row not found: {aliases}")


def _numbers(row: pd.Series) -> list[float]:
    values: list[float] = []
    for raw in row.iloc[1:]:
        parsed = _money(raw)
        if parsed is None:
            continue
        if not values or not np.isclose(parsed, values[-1]):
            values.append(float(parsed))
    return values


def _sales_pair(row: pd.Series) -> tuple[float, float]:
    values = _numbers(row)
    if len(values) < 3:
        raise ValueError("IR sales bridge has too few numeric cells")
    prior = values[0]
    for index in range(len(values) - 2, 0, -1):
        current, change = values[index], values[index + 1]
        if np.isclose(current - prior, change, atol=1.0):
            return prior * 1e6, current * 1e6
    raise ValueError(f"IR sales bridge identity failed: {values}")


def _profit_pair(row: pd.Series) -> tuple[float, float]:
    values = _numbers(row)
    if len(values) < 2:
        raise ValueError("IR profit bridge has too few numeric cells")
    return values[1] * 1e6, values[0] * 1e6


def _period(table: pd.DataFrame) -> tuple[int, int]:
    text = " ".join(table.astype(str).fillna("").to_numpy().ravel().tolist())
    matches = re.findall(r"(First|Second|Third|Fourth) Quarter (20\d{2})", text)
    if not matches:
        raise ValueError("IR quarter header not found")
    word, year = max(matches, key=lambda item: int(item[1]))
    return int(year), QUARTERS[word]


def _metadata_rows(ir_root: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metadata_path in sorted(ir_root.glob("*.metadata.json")):
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        filing_date = pd.Timestamp(payload["filing_date"])
        if filing_date > cutoff:
            continue
        html_path = metadata_path.with_name(metadata_path.name.removesuffix(".metadata.json"))
        is_earnings = (
            filing_date >= pd.Timestamp("2021-01-01")
            and "earnin" in html_path.name.lower()
            and payload.get("document_type") == "EX-99.1"
        )
        is_retail = "retail" in html_path.name.lower()
        actual_sha = _sha256(html_path) if html_path.exists() and is_earnings else None
        rows.append(
            {
                "filing_date": filing_date.date().isoformat(),
                "period_of_report": payload.get("period_of_report"),
                "document_type": payload.get("document_type"),
                "document_name": payload.get("document_name"),
                "source_url": payload.get("source_url"),
                "stored_path": str(html_path),
                "metadata_sha256": payload.get("sha256"),
                "actual_sha256": actual_sha,
                "hash_match": bool(actual_sha == payload.get("sha256")) if is_earnings else np.nan,
                "model_use": "SEGMENT_ACTUAL" if is_earnings else ("CONTEXT_ONLY" if is_retail else "NOT_SELECTED"),
                "selection_reason": "QUARTERLY_EARNINGS_RELEASE" if is_earnings else ("DEALER_RETAIL_CONTEXT" if is_retail else "NON_EARNINGS_IR"),
                "pdf_parsing_deferred": True,
            }
        )
    return pd.DataFrame(rows)


def _parse_release(source: pd.Series) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    tables = pd.read_html(Path(str(source["stored_path"])))
    sales = _find_segment_table(tables, "Sales and Revenues by Segment")
    try:
        profit = _find_segment_table(tables, "Profit (Loss) by Segment")
    except ValueError:
        profit = _find_segment_table(tables, "Profit by Segment")
    year, quarter = _period(sales)
    current_period = f"{year}Q{quarter}"
    prior_period = f"{year - 1}Q{quarter}"
    current: list[dict[str, object]] = []
    repeated: list[dict[str, object]] = []
    for segment, aliases in SEGMENT_ALIASES.items():
        prior_sales, current_sales = _sales_pair(_row(sales, aliases))
        prior_profit, current_profit = _profit_pair(_row(profit, aliases))
        common = {
            "segment": segment,
            "filing_date": source["filing_date"],
            "source_url": source["source_url"],
            "source_path": source["stored_path"],
            "source_sha256": source["actual_sha256"],
        }
        current.append(
            {
                **common,
                "period": current_period,
                "fiscal_year": year,
                "fiscal_quarter": quarter,
                "sales_usd": current_sales,
                "segment_profit_usd": current_profit,
                "comparable_prior_sales_usd": prior_sales,
                "comparable_prior_segment_profit_usd": prior_profit,
            }
        )
        repeated.extend(
            [
                {**common, "filing_period": current_period, "referenced_period": prior_period, "metric": "sales_usd", "repeated_value_usd": prior_sales},
                {**common, "filing_period": current_period, "referenced_period": prior_period, "metric": "segment_profit_usd", "repeated_value_usd": prior_profit},
            ]
        )
    return current, repeated


def build_ir_segment_history(ir_root: Path, cutoff: pd.Timestamp) -> dict[str, pd.DataFrame]:
    inventory = _metadata_rows(ir_root, cutoff)
    selected = inventory.loc[inventory["model_use"].eq("SEGMENT_ACTUAL") & inventory["hash_match"]].copy()
    current_rows: list[dict[str, object]] = []
    repeated_rows: list[dict[str, object]] = []
    for _, source in selected.iterrows():
        current, repeated = _parse_release(source)
        current_rows.extend(current)
        repeated_rows.extend(repeated)
    history = pd.DataFrame(current_rows).sort_values(["period", "segment"]).drop_duplicates(["period", "segment"], keep="last")
    history["operating_cost_usd"] = history["sales_usd"] - history["segment_profit_usd"]
    history["comparable_prior_operating_cost_usd"] = history["comparable_prior_sales_usd"] - history["comparable_prior_segment_profit_usd"]
    history["segment_margin_pct"] = history["segment_profit_usd"] / history["sales_usd"] * 100.0
    actual = history.set_index(["period", "segment"])
    audit = pd.DataFrame(repeated_rows)
    audit["original_value_usd"] = [
        actual.loc[(period, segment), metric] if (period, segment) in actual.index else np.nan
        for period, segment, metric in audit[["referenced_period", "segment", "metric"]].itertuples(index=False, name=None)
    ]
    audit = audit.loc[audit["original_value_usd"].notna()].copy()
    audit["difference_usd"] = audit["repeated_value_usd"] - audit["original_value_usd"]
    audit["exact_match"] = audit["difference_usd"].abs().le(1.0)
    audit["comparison_status"] = np.where(audit["exact_match"], "EXACT", "RECAST_OR_SEGMENT_SCOPE_CHANGE")
    summary = pd.DataFrame(
        [
            {
                "ir_html_inventory_count": len(inventory),
                "earnings_release_count": len(selected),
                "parsed_quarters": history["period"].nunique(),
                "parsed_segments": history["segment"].nunique(),
                "cross_release_cells": len(audit),
                "cross_release_exact_matches": int(audit["exact_match"].sum()),
                "cross_release_mismatches": int((~audit["exact_match"]).sum()),
                "all_selected_source_hashes_match": bool(selected["hash_match"].all()),
                "cross_release_recast_or_scope_change_cells": int((~audit["exact_match"]).sum()),
                "within_release_comparable_basis_used": True,
                "parser_gate_pass": bool(not audit.empty and selected["hash_match"].all() and history["period"].nunique() == len(selected)),
                "pdf_parsing_deferred": True,
                "production_eligible": False,
            }
        ]
    )
    return {
        "ir_source_inventory": inventory,
        "ir_segment_quarterly_history": history.reset_index(drop=True),
        "ir_cross_release_audit": audit.reset_index(drop=True),
        "ir_parser_summary": summary,
    }
