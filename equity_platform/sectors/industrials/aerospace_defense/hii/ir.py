from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd


SEGMENTS = ("ingalls_shipbuilding", "newport_news_shipbuilding", "mission_technologies")
SEGMENT_LABELS = {
    "Ingalls": "ingalls_shipbuilding",
    "Newport News": "newport_news_shipbuilding",
    "Technical Solutions": "mission_technologies",
    "Mission Technologies": "mission_technologies",
}
_PERIODS = (
    re.compile(r"(?P<year>20\d{2})q(?P<quarter>[1-4])", re.IGNORECASE),
    re.compile(r"q(?P<quarter>[1-4])(?P<year>20\d{2})", re.IGNORECASE),
)
_BACKLOG = re.compile(r"(?:total\s+)?backlog\s+(?:to|of|was|at)?\s*(?:approximately\s*)?\$([0-9.]+)\s*billion", re.I)
_AWARDS = re.compile(r"(?:new\s+(?:business|contract)\s+awards|contract\s+awards)[^$]{0,80}\$([0-9.]+)\s*billion", re.I)
_PROGRAM_TERMS = {
    "award_mentions": re.compile(r"\b(?:award|awarded|awards)\b", re.I),
    "delivery_mentions": re.compile(r"\b(?:deliver|delivered|delivery)\b", re.I),
    "milestone_mentions": re.compile(r"\bmilestone(?:s)?\b", re.I),
    "cost_to_cost_mentions": re.compile(r"cost[- ]to[- ]cost", re.I),
    "eac_mentions": re.compile(r"estimate[- ]at[- ]completion|\bEAC\b", re.I),
    "catch_up_adjustment_mentions": re.compile(r"catch[- ]up adjustment", re.I),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _period(name: str) -> str | None:
    for pattern in _PERIODS:
        match = pattern.search(name)
        if match:
            return f"{match.group('year')}Q{match.group('quarter')}"
    return None


def _label(value: object) -> str:
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def _number(value: object) -> float | None:
    text = _label(value).replace(",", "").replace("$", "").replace("%", "")
    if not text or text.lower() == "nan" or text in {"—", "–", "-", "NM"}:
        return None
    negative = text.startswith("(")
    try:
        value_float = float(text.lstrip("(").rstrip(")"))
    except ValueError:
        return None
    return -value_float if negative else value_float


def _numeric_clusters(row: pd.Series, start: int = 0) -> list[float]:
    clusters: list[float] = []
    in_cluster = False
    for value in row.iloc[start:]:
        number = _number(value)
        if number is None:
            in_cluster = False
        elif not in_cluster:
            clusters.append(float(number))
            in_cluster = True
    return clusters


def _first_label(row: pd.Series) -> str:
    return next((_label(value) for value in row if _label(value).lower() not in {"", "nan"}), "")


def _inventory(ir_root: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metadata_path in sorted(ir_root.glob("*.metadata.json")):
        html_path = metadata_path.with_name(metadata_path.name.removesuffix(".metadata.json"))
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        name = str(payload.get("document_name", html_path.name))
        filing_date = pd.Timestamp(payload["filing_date"])
        period = _period(name)
        selected = bool(
            period
            and pd.Period(period, freq="Q") >= pd.Period("2019Q4", freq="Q")
            and filing_date <= cutoff
            and str(payload.get("document_type", "")) == "EX-99.1"
            and "earningsrelea" in name.lower()
        )
        actual_hash = _sha256(html_path) if selected and html_path.exists() else None
        rows.append({
            "period": period, "filing_date": filing_date.date().isoformat(),
            "accession_number": payload.get("accession_number"),
            "document_type": payload.get("document_type"), "document_name": name,
            "source_url": payload.get("source_url"), "source_path": str(html_path),
            "metadata_sha256": payload.get("sha256"), "actual_sha256": actual_hash,
            "hash_match": bool(actual_hash == payload.get("sha256")) if selected else np.nan,
            "model_use": "QUARTERLY_EARNINGS_RELEASE" if selected else "NOT_SELECTED",
            "selection_reason": "HII_EARNINGS_EX991_2019Q4_FORWARD" if selected else "NON_EARNINGS_OR_OUT_OF_WINDOW",
            "pdf_parsing_used": False,
        })
    inventory = pd.DataFrame(rows)
    selected = inventory.loc[inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")]
    duplicates = selected["period"].duplicated(keep=False)
    if duplicates.any():
        raise ValueError(f"Ambiguous HII earnings releases: {sorted(selected.loc[duplicates, 'period'].unique())}")
    return inventory


def _find_table(tables: list[pd.DataFrame]) -> tuple[int, pd.DataFrame]:
    for index, table in enumerate(tables):
        text = " ".join(_label(value) for value in table.to_numpy().ravel()).lower()
        if (
            "ingalls revenues" in text
            and "newport news revenues" in text
            and "sales and service revenues" in text
            and "segment operating income" in text
        ):
            return index, table
    raise ValueError("HII segment result table not found")


def _parse_release(source: pd.Series) -> tuple[
    list[dict[str, object]], list[dict[str, object]], list[dict[str, object]],
    dict[str, object], dict[str, object]
]:
    path = Path(str(source["source_path"]))
    tables = pd.read_html(path)
    table_index, table = _find_table(tables)
    filing_period = pd.Period(str(source["period"]), freq="Q")
    segment_values: dict[tuple[str, str], list[float]] = {}
    company_values: dict[str, list[float]] = {}
    aliases: dict[str, str] = {}
    for _, row in table.iterrows():
        label = _first_label(row)
        values = _numeric_clusters(row)
        lowered = label.lower()
        for raw, segment in SEGMENT_LABELS.items():
            if lowered == f"{raw.lower()} revenues":
                segment_values[(segment, "sales_usd")] = values[:2]
                aliases[segment] = raw
            if (
                (
                    lowered.startswith(f"{raw.lower()} segment operating income")
                    or lowered.startswith(f"{raw.lower()} operating income")
                )
                and not lowered.startswith("adjusted ")
            ):
                segment_values[(segment, "operating_profit_usd")] = values[:2]
                aliases[segment] = raw
        if lowered == "intersegment eliminations":
            company_values["intersegment_eliminations_usd"] = values[:2]
        elif lowered == "sales and service revenues":
            company_values["revenue_usd"] = values[:2]
        elif lowered == "operating income":
            company_values["operating_income_usd"] = values[:2]
        elif lowered.startswith("segment operating income"):
            company_values["segment_operating_income_usd"] = values[:2]
    expected = {(segment, metric) for segment in SEGMENTS for metric in ("sales_usd", "operating_profit_usd")}
    if set(segment_values) != expected or any(len(values) < 2 for values in segment_values.values()):
        raise ValueError(f"Incomplete HII segment table in {path}")
    if set(company_values) != {"intersegment_eliminations_usd", "revenue_usd", "operating_income_usd", "segment_operating_income_usd"}:
        raise ValueError(f"Incomplete HII company table in {path}: {set(company_values)}")
    current: list[dict[str, object]] = []
    comparable: list[dict[str, object]] = []
    companies: list[dict[str, object]] = []
    for block_index, period in enumerate((filing_period, filing_period - 4)):
        for segment in SEGMENTS:
            sales = segment_values[(segment, "sales_usd")][block_index] * 1e6
            profit = segment_values[(segment, "operating_profit_usd")][block_index] * 1e6
            row = {
                "period": str(period), "segment": segment, "reported_segment_label": aliases[segment],
                "sales_usd": sales, "operating_profit_usd": profit,
                "operating_margin_pct": profit / sales * 100.0 if sales else np.nan,
                "filing_period": str(filing_period), "filing_date": source["filing_date"],
                "source_url": source["source_url"], "source_path": source["source_path"],
                "source_sha256": source["actual_sha256"], "table_index": table_index,
                "reported_basis": "AS_REPORTED_CURRENT_PIT" if block_index == 0 else "CURRENT_RELEASE_PRIOR_YEAR_COMPARABLE",
                "history_authority": "AS_REPORTED_PIT_HISTORY" if block_index == 0 else "CURRENTLY_RECAST_COMPARABLE_HISTORY",
            }
            (current if block_index == 0 else comparable).append(row)
        company = {
            "period": str(period), "filing_period": str(filing_period), "filing_date": source["filing_date"],
            **{metric: values[block_index] * 1e6 for metric, values in company_values.items()},
            "source_url": source["source_url"], "source_sha256": source["actual_sha256"], "table_index": table_index,
            "history_authority": "AS_REPORTED_PIT_HISTORY" if block_index == 0 else "CURRENTLY_RECAST_COMPARABLE_HISTORY",
        }
        company["segment_sum_revenue_usd"] = sum(segment_values[(segment, "sales_usd")][block_index] for segment in SEGMENTS) * 1e6
        company["revenue_reconciliation_difference_usd"] = (
            company["segment_sum_revenue_usd"] + company["intersegment_eliminations_usd"] - company["revenue_usd"]
        )
        companies.append(company)
    html = path.read_text(encoding="utf-8", errors="ignore")
    text = " ".join(BeautifulSoup(html, "lxml").get_text(" ").split())
    backlog = _BACKLOG.search(text)
    awards = _AWARDS.search(text)
    contract = {
        "period": str(filing_period), "filing_date": source["filing_date"],
        "total_backlog_usd": float(backlog.group(1)) * 1e9 if backlog else np.nan,
        "contract_awards_usd": float(awards.group(1)) * 1e9 if awards else np.nan,
        "backlog_disclosed": bool(backlog), "contract_awards_disclosed": bool(awards),
        "source_url": source["source_url"], "source_sha256": source["actual_sha256"],
        "historical_pit_input": True, "segment_backlog_available": False,
    }
    program = {
        "period": str(filing_period), "filing_date": source["filing_date"],
        **{name: len(pattern.findall(text)) for name, pattern in _PROGRAM_TERMS.items()},
        "source_url": source["source_url"], "source_sha256": source["actual_sha256"],
        "use": "PROGRAM_TIMING_DIAGNOSTIC_NOT_POINT_OVERRIDE", "historical_pit_input": True,
    }
    return current, comparable, companies, contract, program


def build_hii_ir_evidence(ir_root: Path, cutoff: pd.Timestamp) -> dict[str, pd.DataFrame]:
    inventory = _inventory(ir_root, cutoff)
    selected = inventory.loc[inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")].sort_values("period")
    current_rows: list[dict[str, object]] = []
    comparable_rows: list[dict[str, object]] = []
    company_rows: list[dict[str, object]] = []
    contract_rows: list[dict[str, object]] = []
    program_rows: list[dict[str, object]] = []
    for _, source in selected.iterrows():
        current, comparable, companies, contract, program = _parse_release(source)
        current_rows.extend(current)
        comparable_rows.extend(comparable)
        company_rows.extend(companies)
        contract_rows.append(contract)
        program_rows.append(program)
    current = pd.DataFrame(current_rows).sort_values(["period", "segment"]).reset_index(drop=True)
    comparable = pd.DataFrame(comparable_rows).sort_values(["period", "filing_period", "segment"]).reset_index(drop=True)
    companies = pd.DataFrame(company_rows)
    company_current = companies.loc[companies["history_authority"].eq("AS_REPORTED_PIT_HISTORY")].sort_values("period").reset_index(drop=True)
    company_comparable = companies.loc[companies["history_authority"].eq("CURRENTLY_RECAST_COMPARABLE_HISTORY")].sort_values(["period", "filing_period"]).reset_index(drop=True)
    original = current[["period", "segment", "sales_usd", "operating_profit_usd"]].rename(columns={"sales_usd": "original_sales_usd", "operating_profit_usd": "original_operating_profit_usd"})
    scope = comparable.merge(original, on=["period", "segment"], how="inner", validate="many_to_one")
    scope["sales_revision_usd"] = scope["sales_usd"] - scope["original_sales_usd"]
    scope["operating_profit_revision_usd"] = scope["operating_profit_usd"] - scope["original_operating_profit_usd"]
    scope["material_scope_revision"] = scope[["sales_revision_usd", "operating_profit_revision_usd"]].abs().max(axis=1).gt(1e6)
    parser = pd.DataFrame([{
        "selected_quarterly_ir_releases": len(selected), "selected_ir_hash_matches": int(selected["hash_match"].sum()),
        "segment_quarter_rows": len(current), "company_quarter_rows": len(company_current),
        "segment_sales_coverage_pct": float(current["sales_usd"].notna().mean() * 100),
        "segment_operating_profit_coverage_pct": float(current["operating_profit_usd"].notna().mean() * 100),
        "company_revenue_reconciliation_max_abs_usd": float(company_current["revenue_reconciliation_difference_usd"].abs().max()),
        "backlog_disclosure_quarters": int(pd.DataFrame(contract_rows)["backlog_disclosed"].sum()),
        "contract_award_disclosure_quarters": int(pd.DataFrame(contract_rows)["contract_awards_disclosed"].sum()),
        "material_scope_revision_rows": int(scope["material_scope_revision"].sum()),
        "as_reported_and_currently_recast_histories_separate": True,
        "parser_gate_pass": bool(len(selected) == 27 and selected["hash_match"].all() and company_current["revenue_reconciliation_difference_usd"].abs().max() == 0),
        "pdf_parsing_used": False,
    }])
    return {
        "hii_ir_source_inventory": inventory,
        "hii_segment_as_reported_pit_history": current,
        "hii_segment_currently_recast_comparable_history": comparable,
        "hii_company_as_reported_pit_history": company_current,
        "hii_company_currently_recast_comparable_history": company_comparable,
        "hii_cross_release_scope_audit": scope,
        "hii_contract_backlog_evidence": pd.DataFrame(contract_rows).sort_values("period").reset_index(drop=True),
        "hii_program_timing_evidence": pd.DataFrame(program_rows).sort_values("period").reset_index(drop=True),
        "hii_ir_parser_summary": parser,
    }
