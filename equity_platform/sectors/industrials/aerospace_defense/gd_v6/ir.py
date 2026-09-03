from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from equity_platform.parsing import parse_numeric_token


SEGMENTS = ("aerospace", "marine_systems", "combat_systems", "technologies")
SEGMENT_LABELS = {
    "Aerospace": "aerospace",
    "Marine Systems": "marine_systems",
    "Combat Systems": "combat_systems",
    "Technologies": "technologies",
}
_DOCUMENT_DATE = re.compile(r"(?P<year>20\d{2})(?P<month>\d{2})(?P<day>\d{2})")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _label(value: object) -> str:
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def _number(value: object) -> float | None:
    return parse_numeric_token(_label(value))


def _numeric_clusters(row: pd.Series) -> list[float]:
    clusters: list[float] = []
    in_cluster = False
    for value in row:
        number = _number(value)
        if number is None:
            in_cluster = False
        elif not in_cluster:
            clusters.append(number)
            in_cluster = True
    return clusters


def _first_label(row: pd.Series) -> str:
    return next(
        (_label(value) for value in row if _label(value).lower() not in {"", "nan"}),
        "",
    )


def _segment_from_label(label: str) -> str | None:
    normalized = re.sub(r"\s*\([a-z0-9]+\)\s*$", "", label, flags=re.IGNORECASE)
    return SEGMENT_LABELS.get(normalized)


def _period_from_document(document_name: str) -> str | None:
    matches = list(_DOCUMENT_DATE.finditer(document_name))
    if not matches:
        return None
    match = matches[-1]
    year, month = int(match.group("year")), int(match.group("month"))
    quarter = 1 if month <= 4 else 2 if month <= 7 else 3 if month <= 10 else 4
    return f"{year}Q{quarter}"


def _inventory(ir_root: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metadata_path in sorted(ir_root.glob("*.metadata.json")):
        html_path = metadata_path.with_name(
            metadata_path.name.removesuffix(".metadata.json")
        )
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        filing_date = pd.Timestamp(payload["filing_date"])
        document_name = str(payload.get("document_name", html_path.name))
        period = _period_from_document(document_name)
        selected = bool(
            period
            # GD still reported the pre-realignment five-segment perimeter in
            # 2020Q1-Q3.  The four-segment perimeter begins in the original
            # 2020Q4 release; older values shown later remain comparables only.
            and pd.Period(period, freq="Q") >= pd.Period("2020Q4", freq="Q")
            and filing_date <= cutoff
            and str(payload.get("document_type", "")).startswith("EX-99")
            and html_path.is_file()
            and html_path.stat().st_size > 250_000
        )
        actual_hash = _sha256(html_path) if selected else None
        rows.append(
            {
                "period": period,
                "filing_date": filing_date.date().isoformat(),
                "accession_number": payload.get("accession_number"),
                "document_type": payload.get("document_type"),
                "document_name": document_name,
                "source_url": payload.get("source_url"),
                "source_path": str(html_path),
                "source_size_bytes": html_path.stat().st_size if html_path.exists() else 0,
                "metadata_sha256": payload.get("sha256"),
                "actual_sha256": actual_hash,
                "hash_match": (
                    bool(actual_hash == payload.get("sha256")) if selected else np.nan
                ),
                "model_use": "QUARTERLY_EARNINGS_RELEASE" if selected else "NOT_SELECTED",
                "selection_reason": (
                    "GD_LARGE_EARNINGS_EX99_STABLE_FOUR_SEGMENT_2020Q4_FORWARD"
                    if selected
                    else "NON_EARNINGS_SMALL_OR_OUT_OF_WINDOW"
                ),
                "pdf_parsing_used": False,
            }
        )
    inventory = pd.DataFrame(rows)
    selected = inventory.loc[inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")]
    duplicates = selected["period"].duplicated(keep=False)
    if duplicates.any():
        raise ValueError(
            f"Ambiguous GD earnings releases: {sorted(selected.loc[duplicates, 'period'].unique())}"
        )
    return inventory


def _find_segment_table(tables: list[pd.DataFrame]) -> tuple[int, pd.DataFrame]:
    for index, table in enumerate(tables):
        text = " ".join(_label(value) for value in table.to_numpy().ravel()).lower()
        if (
            all(label.lower() in text for label in SEGMENT_LABELS)
            and "revenue:" in text
            and "operating earnings:" in text
            and "three months" in text
        ):
            return index, table
    raise ValueError("GD quarterly segment result table not found")


def _parse_segment_table(
    source: pd.Series, tables: list[pd.DataFrame]
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    table_index, table = _find_segment_table(tables)
    filing_period = pd.Period(str(source["period"]), freq="Q")
    metric: str | None = None
    values: dict[tuple[str, str], list[float]] = {}
    corporate: list[float] | None = None
    totals: dict[str, list[float]] = {}
    for _, row in table.iterrows():
        label = _first_label(row)
        lowered = label.lower()
        if lowered == "revenue:":
            metric = "sales_usd"
            continue
        if lowered == "operating earnings:":
            metric = "operating_profit_usd"
            continue
        if lowered == "operating margin:":
            metric = None
            continue
        segment = _segment_from_label(label)
        clusters = _numeric_clusters(row)
        if segment and metric and len(clusters) >= 2:
            values[(segment, metric)] = clusters[:2]
        elif label == "Corporate" and metric == "operating_profit_usd" and len(clusters) >= 2:
            corporate = clusters[:2]
        elif label == "Total" and metric and len(clusters) >= 2:
            totals[metric] = clusters[:2]

    expected = {
        (segment, metric)
        for segment in SEGMENTS
        for metric in ("sales_usd", "operating_profit_usd")
    }
    if set(values) != expected or corporate is None or set(totals) != {
        "sales_usd",
        "operating_profit_usd",
    }:
        raise ValueError(f"Incomplete GD segment result table in {source['source_path']}")

    current: list[dict[str, object]] = []
    comparable: list[dict[str, object]] = []
    company: list[dict[str, object]] = []
    for block, period in enumerate((filing_period, filing_period - 4)):
        for segment in SEGMENTS:
            sales = values[(segment, "sales_usd")][block] * 1e6
            profit = values[(segment, "operating_profit_usd")][block] * 1e6
            record = {
                "period": str(period),
                "segment": segment,
                "sales_usd": sales,
                "operating_profit_usd": profit,
                "operating_margin_pct": profit / sales * 100.0,
                "filing_period": str(filing_period),
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_path": source["source_path"],
                "source_sha256": source["actual_sha256"],
                "table_index": table_index,
                "history_authority": (
                    "AS_REPORTED_PIT_HISTORY"
                    if block == 0
                    else "CURRENT_RELEASE_PRIOR_YEAR_COMPARABLE"
                ),
            }
            (current if block == 0 else comparable).append(record)
        segment_sales = sum(values[(segment, "sales_usd")][block] for segment in SEGMENTS)
        segment_profit = sum(
            values[(segment, "operating_profit_usd")][block] for segment in SEGMENTS
        )
        company.append(
            {
                "period": str(period),
                "filing_period": str(filing_period),
                "revenue_usd": totals["sales_usd"][block] * 1e6,
                "operating_income_usd": totals["operating_profit_usd"][block] * 1e6,
                "corporate_operating_loss_usd": corporate[block] * 1e6,
                "segment_sum_revenue_usd": segment_sales * 1e6,
                "segment_sum_operating_profit_usd": segment_profit * 1e6,
                "revenue_identity_error_usd": (
                    totals["sales_usd"][block] - segment_sales
                )
                * 1e6,
                "operating_income_identity_error_usd": (
                    totals["operating_profit_usd"][block]
                    - segment_profit
                    - corporate[block]
                )
                * 1e6,
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_path": source["source_path"],
                "source_sha256": source["actual_sha256"],
                "table_index": table_index,
                "history_authority": (
                    "AS_REPORTED_PIT_HISTORY"
                    if block == 0
                    else "CURRENT_RELEASE_PRIOR_YEAR_COMPARABLE"
                ),
            }
        )
    return current, comparable, company


def _find_backlog_table(tables: list[pd.DataFrame]) -> tuple[int, pd.DataFrame]:
    for index, table in enumerate(tables):
        text = " ".join(_label(value) for value in table.to_numpy().ravel())
        if (
            all(label in text for label in SEGMENT_LABELS)
            and "Funded" in text
            and "Unfunded" in text
            and "Total Backlog" in text
            and "EstimatedPotentialContract Value".replace(" ", "")
            in text.replace(" ", "")
        ):
            return index, table
    raise ValueError("GD backlog table not found")


def _parse_backlog(source: pd.Series, tables: list[pd.DataFrame]) -> list[dict[str, object]]:
    table_index, table = _find_backlog_table(tables)
    seen: set[str] = set()
    rows: list[dict[str, object]] = []
    for _, row in table.iterrows():
        label = _first_label(row)
        segment = _segment_from_label(label)
        if not segment or segment in seen:
            continue
        values = _numeric_clusters(row)
        if len(values) < 5:
            raise ValueError(f"Incomplete GD backlog row {label} in {source['source_path']}")
        funded, unfunded, total, potential, estimated_total = values[:5]
        rows.append(
            {
                "period": source["period"],
                "segment": segment,
                "funded_backlog_usd": funded * 1e6,
                "unfunded_backlog_usd": unfunded * 1e6,
                "backlog_usd": total * 1e6,
                "estimated_potential_contract_value_usd": potential * 1e6,
                "total_estimated_contract_value_usd": estimated_total * 1e6,
                "funded_share_pct": funded / total * 100.0 if total else np.nan,
                "backlog_identity_error_usd": (funded + unfunded - total) * 1e6,
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_path": source["source_path"],
                "source_sha256": source["actual_sha256"],
                "table_index": table_index,
                "historical_pit_input": True,
                "potential_value_model_input_allowed": False,
            }
        )
        seen.add(segment)
    if set(seen) != set(SEGMENTS):
        raise ValueError(f"Expected four GD backlog rows in {source['source_path']}")
    return rows


def _parse_aerospace_deliveries(
    source: pd.Series, tables: list[pd.DataFrame]
) -> dict[str, object]:
    for table_index, table in enumerate(tables):
        labels = [_first_label(row) for _, row in table.iterrows()]
        start = next(
            (
                index
                for index, label in enumerate(labels)
                if label.startswith("Gulfstream Aircraft Deliveries")
            ),
            None,
        )
        if start is None:
            continue
        for row_index in range(start + 1, min(start + 6, len(table))):
            row = table.iloc[row_index]
            if _first_label(row) != "Total":
                continue
            values = _numeric_clusters(row)
            if len(values) < 2:
                break
            return {
                "period": source["period"],
                "gulfstream_deliveries_units": values[0],
                "prior_year_gulfstream_deliveries_units": values[1],
                "deliveries_yoy_pct": (values[0] / values[1] - 1.0) * 100.0,
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_path": source["source_path"],
                "source_sha256": source["actual_sha256"],
                "table_index": table_index,
                "historical_pit_input": True,
                "primary_anchor": True,
            }
    raise ValueError(f"GD Gulfstream delivery table not found in {source['source_path']}")


def _scope_audit(current: pd.DataFrame, comparable: pd.DataFrame) -> pd.DataFrame:
    original = current[
        ["period", "segment", "sales_usd", "operating_profit_usd"]
    ].rename(
        columns={
            "sales_usd": "original_sales_usd",
            "operating_profit_usd": "original_operating_profit_usd",
        }
    )
    audit = comparable.merge(
        original, on=["period", "segment"], how="inner", validate="many_to_one"
    )
    audit["sales_revision_usd"] = audit["sales_usd"] - audit["original_sales_usd"]
    audit["operating_profit_revision_usd"] = (
        audit["operating_profit_usd"] - audit["original_operating_profit_usd"]
    )
    audit["material_scope_change"] = (
        audit[["sales_revision_usd", "operating_profit_revision_usd"]]
        .abs()
        .max(axis=1)
        .gt(1e6)
    )
    audit["scope_treatment"] = np.where(
        audit["material_scope_change"],
        "EXCLUDE_FROM_POINT_PERFORMANCE_CLAIM",
        "COMPARABLE_TO_ORIGINAL",
    )
    return audit.sort_values(["period", "segment", "filing_period"]).reset_index(
        drop=True
    )


def build_gd_ir_evidence(ir_root: Path, cutoff: pd.Timestamp) -> dict[str, pd.DataFrame]:
    inventory = _inventory(ir_root, cutoff)
    selected = inventory.loc[
        inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")
    ].sort_values("period")
    current_rows: list[dict[str, object]] = []
    comparable_rows: list[dict[str, object]] = []
    company_rows: list[dict[str, object]] = []
    backlog_rows: list[dict[str, object]] = []
    delivery_rows: list[dict[str, object]] = []
    for _, source in selected.iterrows():
        tables = pd.read_html(Path(str(source["source_path"])), flavor="lxml")
        current, comparable, company = _parse_segment_table(source, tables)
        current_rows.extend(current)
        comparable_rows.extend(comparable)
        company_rows.extend(company)
        backlog_rows.extend(_parse_backlog(source, tables))
        delivery_rows.append(_parse_aerospace_deliveries(source, tables))

    history = pd.DataFrame(current_rows).sort_values(["period", "segment"])
    comparables = pd.DataFrame(comparable_rows).sort_values(
        ["period", "segment", "filing_period"]
    )
    companies = pd.DataFrame(company_rows)
    company_current = companies.loc[
        companies["history_authority"].eq("AS_REPORTED_PIT_HISTORY")
    ].sort_values("period")
    company_comparables = companies.loc[
        companies["history_authority"].eq("CURRENT_RELEASE_PRIOR_YEAR_COMPARABLE")
    ].sort_values(["period", "filing_period"])
    backlog = pd.DataFrame(backlog_rows).sort_values(["period", "segment"])
    deliveries = pd.DataFrame(delivery_rows).sort_values("period")
    scope = _scope_audit(history, comparables)
    summary = pd.DataFrame(
        [
            {
                "earnings_releases": len(selected),
                "hash_matches": int(selected["hash_match"].sum()),
                "segment_quarter_rows": len(history),
                "company_quarter_rows": len(company_current),
                "backlog_segment_quarter_rows": len(backlog),
                "aerospace_delivery_quarters": len(deliveries),
                "segment_metric_coverage_pct": float(
                    history[["sales_usd", "operating_profit_usd"]]
                    .notna()
                    .mean()
                    .mean()
                    * 100.0
                ),
                "funded_backlog_coverage_pct": float(
                    backlog["funded_backlog_usd"].notna().mean() * 100.0
                ),
                "company_revenue_identity_max_abs_usd": float(
                    company_current["revenue_identity_error_usd"].abs().max()
                ),
                "company_operating_income_identity_max_abs_usd": float(
                    company_current["operating_income_identity_error_usd"].abs().max()
                ),
                "backlog_identity_max_abs_usd": float(
                    backlog["backlog_identity_error_usd"].abs().max()
                ),
                "scope_change_comparisons": len(scope),
                "material_scope_change_rows": int(scope["material_scope_change"].sum()),
                "parser_gate_pass": bool(
                    len(selected) == 23
                    and selected["hash_match"].all()
                    and len(history) == 92
                    and len(company_current) == 23
                    and len(backlog) == 92
                    and len(deliveries) == 23
                    and company_current["revenue_identity_error_usd"].abs().max() == 0
                    and company_current["operating_income_identity_error_usd"].abs().max()
                    == 0
                    and backlog["backlog_identity_error_usd"].abs().max() == 0
                ),
                "pdf_parsing_used": False,
            }
        ]
    )
    return {
        "gd_ir_source_inventory": inventory.reset_index(drop=True),
        "gd_segment_as_reported_pit_history": history.reset_index(drop=True),
        "gd_segment_prior_year_comparables": comparables.reset_index(drop=True),
        "gd_company_as_reported_pit_history": company_current.reset_index(drop=True),
        "gd_company_prior_year_comparables": company_comparables.reset_index(drop=True),
        "gd_backlog_history": backlog.reset_index(drop=True),
        "gd_aerospace_delivery_history": deliveries.reset_index(drop=True),
        "gd_cross_release_scope_audit": scope,
        "gd_ir_parser_summary": summary,
    }
