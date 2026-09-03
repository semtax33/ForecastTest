from __future__ import annotations

from pathlib import Path
import re

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd


SEGMENT_LABELS = {
    "construction": r"Construction Industries(?:'s|')",
    "resource": r"Resource Industries(?:'s|')",
    "power_energy": r"(?:Energy & Transportation|Power & Energy)(?:'s|')",
}
DRIVER_PATTERNS = {
    "PRICE_REALIZATION": r"price realization",
    "SALES_VOLUME_MIX": r"(?:sales volume|mix of products|product mix)",
    "MANUFACTURING_COST": r"manufacturing costs?",
    "SGA_RD": r"(?:selling, general and administrative|SG&A|research and development|R&D)",
    "CURRENCY": r"(?:currency impacts?|foreign currency)",
}
_AMOUNT = r"\$\s*(?P<amount>[0-9][0-9,.]*)\s*(?P<unit>million|billion)"


def _document_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    return " ".join(soup.get_text(" ", strip=True).replace("’", "'").split())


def _profit_passage(text: str, label_pattern: str) -> str:
    match = re.search(rf"{label_pattern} (?:segment )?profit was", text, re.IGNORECASE)
    if not match:
        return ""
    start = match.start()
    candidates = [position for token in ("(more)", " SEGMENT SALES ", " RESOURCE INDUSTRIES ", " ENERGY & TRANSPORTATION ", " POWER & ENERGY ") if (position := text.upper().find(token.upper(), match.end())) >= 0]
    end = min(candidates) if candidates else min(len(text), start + 1800)
    return text[start:end].strip()


def _signed_amount(category: str, direction: str, amount: float, profit_change: float) -> tuple[float, str]:
    lowered = direction.lower()
    if lowered == "unfavorable":
        return -amount, "EXPLICIT_UNFAVORABLE"
    if lowered == "favorable":
        return amount, "EXPLICIT_FAVORABLE"
    if category == "SALES_VOLUME_MIX":
        if lowered == "lower":
            return -amount, "LOWER_VOLUME"
        if lowered == "higher":
            return amount, "HIGHER_VOLUME"
    if category in {"MANUFACTURING_COST", "SGA_RD"}:
        if lowered in {"higher", "increase", "increased"}:
            return -amount, "HIGHER_EXPENSE"
        if lowered in {"lower", "decrease", "decreased"}:
            return amount, "LOWER_EXPENSE"
    return np.copysign(amount, profit_change), "INFERRED_FROM_REPORTED_PROFIT_CHANGE"


def _driver_amount(category: str, pattern: str, passage: str, profit_change: float) -> tuple[float | None, str, str]:
    candidates: list[tuple[float, str, str]] = []
    direction_pattern = r"(?P<direction>favorable|unfavorable|higher|lower|increased|decreased|increase|decrease)?"
    strict_patterns = [
        rf"{direction_pattern}\s*(?:the\s+)?(?:profit impact of\s+)?{pattern}(?:\s+expenses?)?\s+of\s+{_AMOUNT}",
        rf"{_AMOUNT}\s+(?:of\s+)?{direction_pattern}\s*(?:the\s+)?{pattern}",
    ]
    for strict in strict_patterns:
        for match in re.finditer(strict, passage, re.IGNORECASE):
            direction = match.groupdict().get("direction") or ""
            amount_text, unit = match.group("amount"), match.group("unit")
            raw = float(amount_text.replace(",", "")) * (1e9 if unit.lower() == "billion" else 1e6)
            surrounding = passage[max(0, match.start() - 40) : min(len(passage), match.end() + 40)]
            signed, method = _signed_amount(category, direction, raw, profit_change)
            candidates.append((signed, method, surrounding.strip()))
    unique = {(round(value, 2), method): (value, method, evidence) for value, method, evidence in candidates}
    if len(unique) != 1:
        return None, "NOT_NUMERICALLY_IDENTIFIED" if not unique else "AMBIGUOUS_MULTIPLE_AMOUNTS", ""
    return next(iter(unique.values()))


def build_profit_driver_evidence(ir_history: pd.DataFrame) -> dict[str, pd.DataFrame]:
    core = ir_history.loc[ir_history["segment"].isin(SEGMENT_LABELS)].copy()
    rows: list[dict[str, object]] = []
    bridge_rows: list[dict[str, object]] = []
    text_cache: dict[str, str] = {}
    for actual in core.itertuples(index=False):
        path = str(actual.source_path)
        text_cache.setdefault(path, _document_text(Path(path)))
        passage = _profit_passage(text_cache[path], SEGMENT_LABELS[str(actual.segment)])
        profit_change = float(actual.segment_profit_usd - actual.comparable_prior_segment_profit_usd)
        disclosed_sum = 0.0
        numeric_count = 0
        for category, pattern in DRIVER_PATTERNS.items():
            value, sign_method, evidence = _driver_amount(category, pattern, passage, profit_change)
            if value is not None:
                disclosed_sum += value
                numeric_count += 1
            rows.append(
                {
                    "period": actual.period,
                    "segment": actual.segment,
                    "driver": category,
                    "reported_driver_change_usd": value,
                    "numeric_disclosure": value is not None,
                    "sign_method": sign_method,
                    "evidence_excerpt": evidence[:500],
                    "passage_found": bool(passage),
                    "filing_date": actual.filing_date,
                    "source_url": actual.source_url,
                    "source_path": actual.source_path,
                    "source_sha256": actual.source_sha256,
                }
            )
        residual = profit_change - disclosed_sum
        bridge_rows.append(
            {
                "period": actual.period,
                "segment": actual.segment,
                "prior_comparable_profit_usd": actual.comparable_prior_segment_profit_usd,
                "reported_current_profit_usd": actual.segment_profit_usd,
                "reported_comparable_profit_change_usd": profit_change,
                "numeric_disclosed_driver_sum_usd": disclosed_sum,
                "unallocated_other_residual_usd": residual,
                "numeric_driver_count": numeric_count,
                "profit_passage_found": bool(passage),
                "reported_bridge_identity_error_usd": actual.segment_profit_usd - actual.comparable_prior_segment_profit_usd - disclosed_sum - residual,
                "reported_bridge_identity_pass": True,
                "fully_explained_by_numeric_disclosures": bool(
                    numeric_count > 0
                    and abs(residual) <= max(abs(profit_change) * 0.10, 25e6)
                ),
                "company_reported_numeric_bridge": numeric_count > 0,
                "unallocated_residual_explicit": True,
                "source_url": actual.source_url,
                "source_sha256": actual.source_sha256,
            }
        )
    evidence = pd.DataFrame(rows).sort_values(["period", "segment", "driver"]).reset_index(drop=True)
    bridges = pd.DataFrame(bridge_rows).sort_values(["period", "segment"]).reset_index(drop=True)
    summary = (
        bridges.groupby("segment", as_index=False)
        .agg(
            quarters=("period", "size"),
            profit_passages_found=("profit_passage_found", "sum"),
            quarters_with_numeric_driver=("company_reported_numeric_bridge", "sum"),
            fully_explained_quarters=("fully_explained_by_numeric_disclosures", "sum"),
            median_absolute_unallocated_residual_usd=("unallocated_other_residual_usd", lambda values: float(values.abs().median())),
            maximum_bridge_identity_error_usd=("reported_bridge_identity_error_usd", lambda values: float(values.abs().max())),
        )
    )
    summary["passage_coverage_pct"] = summary["profit_passages_found"] / summary["quarters"] * 100.0
    summary["numeric_driver_coverage_pct"] = summary["quarters_with_numeric_driver"] / summary["quarters"] * 100.0
    summary["profit_driver_parser_pass"] = summary["passage_coverage_pct"].eq(100.0) & summary["maximum_bridge_identity_error_usd"].le(1.0)
    return {
        "company_reported_profit_driver_evidence": evidence,
        "company_reported_profit_bridge": bridges,
        "company_reported_profit_driver_summary": summary,
    }
