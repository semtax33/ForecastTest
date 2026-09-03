from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd


SEGMENTS = (
    "aeronautics_systems",
    "defense_systems",
    "mission_systems",
    "space_systems",
)
SEGMENT_LABELS = {
    "Aeronautics Systems": "aeronautics_systems",
    "Defense Systems": "defense_systems",
    "Mission Systems": "mission_systems",
    "Space Systems": "space_systems",
}
_PERIOD = re.compile(r"(?P<date>1231|0?331|0?630|0?930)(?P<year>20\d{2})", re.IGNORECASE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _label(value: object) -> str:
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def _number(value: object) -> float | None:
    text = _label(value).replace(",", "").replace("$", "").replace("%", "")
    if not text or text.lower() == "nan" or text in {"—", "–", "-", "NM"}:
        return None
    negative = text.startswith("(")
    text = text.lstrip("(").rstrip(")")
    try:
        result = float(text)
    except ValueError:
        return None
    return -result if negative else result


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
    return next(
        (_label(value) for value in row if _label(value).lower() not in {"", "nan"}),
        "",
    )


def _segment_from_label(label: str) -> str | None:
    return SEGMENT_LABELS.get(re.sub(r"\d+$", "", label).strip())


def _period_from_document(document_name: str) -> str | None:
    match = _PERIOD.search(document_name)
    if not match:
        return None
    month_day = match.group("date").lstrip("0")
    quarter = {"331": 1, "630": 2, "930": 3, "1231": 4}[month_day]
    return f"{match.group('year')}Q{quarter}"


def _metadata_inventory(ir_root: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metadata_path in sorted(ir_root.glob("*.metadata.json")):
        html_path = metadata_path.with_name(metadata_path.name.removesuffix(".metadata.json"))
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        filing_date = pd.Timestamp(payload["filing_date"])
        document_name = str(payload.get("document_name", ""))
        period = _period_from_document(document_name)
        selected = bool(
            period
            and "earning" in document_name.lower()
            and pd.Period(period, freq="Q") >= pd.Period("2020Q1", freq="Q")
            and filing_date <= cutoff
            and str(payload.get("document_type", "")).startswith("EX-99")
        )
        actual_hash = _sha256(html_path) if selected and html_path.exists() else None
        rows.append(
            {
                "period": period,
                "filing_date": filing_date.date().isoformat(),
                "accession_number": payload.get("accession_number"),
                "document_type": payload.get("document_type"),
                "document_name": document_name,
                "source_url": payload.get("source_url"),
                "source_path": str(html_path),
                "metadata_sha256": payload.get("sha256"),
                "actual_sha256": actual_hash,
                "hash_match": bool(actual_hash == payload.get("sha256")) if selected else np.nan,
                "model_use": "QUARTERLY_EARNINGS_RELEASE" if selected else "NOT_SELECTED",
                "selection_reason": "NOC_EARNINGS_EX99_2020Q1_FORWARD" if selected else "NON_EARNINGS_OR_OUT_OF_WINDOW",
                "pdf_parsing_used": False,
            }
        )
    inventory = pd.DataFrame(rows)
    selected = inventory.loc[inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")]
    duplicates = selected["period"].duplicated(keep=False)
    if duplicates.any():
        raise ValueError(
            f"Ambiguous NOC earnings releases: {sorted(selected.loc[duplicates, 'period'].unique())}"
        )
    return inventory


def _find_segment_result_table(tables: list[pd.DataFrame]) -> tuple[int, pd.DataFrame]:
    for index, table in enumerate(tables):
        text = " ".join(_label(value) for value in table.to_numpy().ravel())
        lowered = text.lower()
        if (
            len(table) >= 25
            and all(label.lower() in lowered for label in SEGMENT_LABELS)
            and "sales" in lowered
            and "operating" in lowered
            and "income" in lowered
        ):
            return index, table
    raise ValueError("NOC segment result table not found")


def _parse_segment_results(
    source: pd.Series,
    tables: list[pd.DataFrame],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    table_index, table = _find_segment_result_table(tables)
    filing_period = pd.Period(str(source["period"]), freq="Q")
    metric: str | None = None
    values: dict[tuple[str, str], list[float]] = {}
    for _, row in table.iterrows():
        label = _first_label(row)
        normalized = label.lower().rstrip("1234567890")
        if normalized == "sales":
            metric = "sales_usd"
            continue
        if normalized in {
            "operating income",
            "operating (loss) income",
            "operating income (loss)",
            "segment operating income",
            "segment operating (loss) income",
            "segment operating income (loss)",
        }:
            metric = "operating_profit_usd"
            continue
        segment = _segment_from_label(label)
        if segment and metric:
            clusters = _numeric_clusters(row)
            if len(clusters) < 2:
                raise ValueError(f"Missing current/prior NOC values for {label} in {source['source_path']}")
            values[(segment, metric)] = clusters[:2]
    expected = {(segment, metric) for segment in SEGMENTS for metric in ("sales_usd", "operating_profit_usd")}
    if set(values) != expected:
        raise ValueError(f"Incomplete NOC segment result table in {source['source_path']}: {set(values)}")
    current: list[dict[str, object]] = []
    comparables: list[dict[str, object]] = []
    for segment in SEGMENTS:
        for block_index, period in enumerate((filing_period, filing_period - 4)):
            sales = values[(segment, "sales_usd")][block_index] * 1e6
            profit = values[(segment, "operating_profit_usd")][block_index] * 1e6
            row = {
                "period": str(period),
                "segment": segment,
                "sales_usd": sales,
                "operating_profit_usd": profit,
                "operating_margin_pct": profit / sales * 100.0 if sales else np.nan,
                "filing_period": str(filing_period),
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_path": source["source_path"],
                "source_sha256": source["actual_sha256"],
                "table_index": table_index,
                "reported_basis": "CURRENT_RELEASE" if block_index == 0 else "CURRENT_RELEASE_PRIOR_YEAR_COMPARABLE",
            }
            (current if block_index == 0 else comparables).append(row)
    return current, comparables


def _find_backlog_table(tables: list[pd.DataFrame]) -> tuple[int, pd.DataFrame]:
    for index, table in enumerate(tables):
        text = " ".join(_label(value) for value in table.to_numpy().ravel())
        if all(label in text for label in SEGMENT_LABELS) and "Funded" in text and "Total Backlog" in text:
            return index, table
    raise ValueError("NOC funded/unfunded backlog table not found")


def _parse_backlog(source: pd.Series, tables: list[pd.DataFrame]) -> list[dict[str, object]]:
    table_index, table = _find_backlog_table(tables)
    rows: list[dict[str, object]] = []
    for _, row in table.iterrows():
        label = _first_label(row)
        segment = _segment_from_label(label)
        if not segment:
            continue
        values = _numeric_clusters(row)
        if len(values) < 4:
            raise ValueError(f"Incomplete NOC backlog row {label} in {source['source_path']}")
        funded, unfunded, total, prior_total = values[:4]
        rows.append(
            {
                "period": source["period"],
                "segment": segment,
                "funded_backlog_usd": funded * 1e6,
                "unfunded_backlog_usd": unfunded * 1e6,
                "backlog_usd": total * 1e6,
                "prior_fiscal_year_end_backlog_usd": prior_total * 1e6,
                "funded_share_pct": funded / total * 100.0 if total else np.nan,
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_sha256": source["actual_sha256"],
                "table_index": table_index,
                "historical_pit_input": True,
            }
        )
    if len(rows) != 4:
        raise ValueError(f"Expected four NOC backlog rows in {source['source_path']}")
    return rows


def _build_scope_audit(current: pd.DataFrame, comparable: pd.DataFrame) -> pd.DataFrame:
    original = current[["period", "segment", "sales_usd", "operating_profit_usd"]].rename(
        columns={
            "sales_usd": "original_sales_usd",
            "operating_profit_usd": "original_operating_profit_usd",
        }
    )
    audit = comparable.merge(original, on=["period", "segment"], how="inner", validate="many_to_one")
    audit["sales_revision_usd"] = audit["sales_usd"] - audit["original_sales_usd"]
    audit["operating_profit_revision_usd"] = (
        audit["operating_profit_usd"] - audit["original_operating_profit_usd"]
    )
    audit["material_scope_change"] = (
        audit["sales_revision_usd"].abs().gt(1e6)
        | audit["operating_profit_revision_usd"].abs().gt(1e6)
    )
    audit["scope_treatment"] = np.where(
        audit["material_scope_change"],
        "EXCLUDE_FROM_POINT_PERFORMANCE_CLAIM",
        "COMPARABLE_TO_ORIGINAL",
    )
    return audit.sort_values(["period", "segment", "filing_period"]).reset_index(drop=True)


def build_noc_ir_evidence(ir_root: Path, cutoff: pd.Timestamp) -> dict[str, pd.DataFrame]:
    inventory = _metadata_inventory(ir_root, cutoff)
    selected = inventory.loc[inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")].copy()
    current_rows: list[dict[str, object]] = []
    comparable_rows: list[dict[str, object]] = []
    backlog_rows: list[dict[str, object]] = []
    for _, source in selected.sort_values("period").iterrows():
        tables = pd.read_html(Path(str(source["source_path"])), flavor="lxml")
        current, comparable = _parse_segment_results(source, tables)
        current_rows.extend(current)
        comparable_rows.extend(comparable)
        backlog_rows.extend(_parse_backlog(source, tables))
    history = pd.DataFrame(current_rows).sort_values(["period", "segment"]).reset_index(drop=True)
    comparables = pd.DataFrame(comparable_rows).sort_values(["period", "segment", "filing_period"]).reset_index(drop=True)
    backlog = pd.DataFrame(backlog_rows).sort_values(["period", "segment"]).reset_index(drop=True)
    scope = _build_scope_audit(history, comparables)
    summary = pd.DataFrame(
        [
            {
                "earnings_releases": len(selected),
                "hash_matches": int(selected["hash_match"].sum()),
                "segment_quarter_rows": len(history),
                "segment_sales_coverage_pct": float(history["sales_usd"].notna().mean() * 100.0),
                "segment_operating_profit_coverage_pct": float(history["operating_profit_usd"].notna().mean() * 100.0),
                "backlog_segment_quarter_rows": len(backlog),
                "total_backlog_coverage_pct": float(backlog["backlog_usd"].notna().mean() * 100.0),
                "funded_backlog_coverage_pct": float(backlog["funded_backlog_usd"].notna().mean() * 100.0),
                "funded_share_coverage_pct": float(backlog["funded_share_pct"].notna().mean() * 100.0),
                "scope_change_comparisons": len(scope),
                "material_scope_change_rows": int(scope["material_scope_change"].sum()),
                "parser_gate_pass": bool(
                    len(selected) == 26
                    and selected["hash_match"].all()
                    and len(history) == 104
                    and len(backlog) == 104
                    and history[["sales_usd", "operating_profit_usd"]].notna().all().all()
                    and backlog[["funded_backlog_usd", "unfunded_backlog_usd", "backlog_usd"]].notna().all().all()
                ),
                "pdf_parsing_used": False,
            }
        ]
    )
    return {
        "noc_ir_source_inventory": inventory,
        "noc_segment_quarterly_history": history,
        "noc_prior_year_comparables": comparables,
        "noc_backlog_history": backlog,
        "noc_cross_release_scope_audit": scope,
        "noc_ir_parser_summary": summary,
    }
