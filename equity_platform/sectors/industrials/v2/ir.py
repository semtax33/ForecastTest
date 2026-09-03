from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd


_PERIOD = re.compile(r"cmi(20\d{2}).*?q([1-4])", re.IGNORECASE)
_SEGMENT_ALIASES = {
    "engine": ("Engine",),
    "components": ("Components",),
    "distribution": ("Distribution",),
    "power_systems": ("Power Systems",),
    "accelera": ("Accelera", "New Power"),
}
_METRICS = {
    "external_sales_usd": ("External sales",),
    "intersegment_sales_usd": ("Intersegment sales", "Less: Intersegment sales"),
    "total_sales_usd": ("Total sales", "Segment sales"),
    "rd_engineering_usd": ("Research, development and engineering expenses",),
    "equity_royalty_interest_income_usd": ("Equity, royalty and interest income",),
    "interest_income_usd": ("Interest income",),
    "ebitda_usd": ("EBITDA", "Segment EBITDA"),
    "depreciation_amortization_usd": ("Depreciation and amortization",),
}


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
    if not text or text in {"nan", "—", "-", "NM"}:
        return None
    negative = text.startswith("(")
    if negative:
        text = text.lstrip("(").rstrip(")")
    try:
        result = float(text)
    except ValueError:
        return None
    return -result if negative else result


def _metadata_inventory(ir_root: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metadata_path in sorted(ir_root.glob("*.metadata.json")):
        html_path = metadata_path.with_name(metadata_path.name.removesuffix(".metadata.json"))
        match = _PERIOD.search(html_path.name)
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        filing_date = pd.Timestamp(payload["filing_date"])
        selected = bool(
            match
            and pd.Period(f"{match.group(1)}Q{match.group(2)}", freq="Q")
            .asfreq("Q")
            .ordinal
            >= pd.Period("2019Q4", freq="Q").ordinal
            and filing_date <= cutoff
            and payload.get("document_type", "").startswith("EX-99")
        )
        actual_hash = _sha256(html_path) if selected and html_path.exists() else None
        rows.append(
            {
                "period": f"{match.group(1)}Q{match.group(2)}" if match else None,
                "filing_date": filing_date.date().isoformat(),
                "accession_number": payload.get("accession_number"),
                "document_type": payload.get("document_type"),
                "document_name": payload.get("document_name"),
                "source_url": payload.get("source_url"),
                "source_path": str(html_path),
                "metadata_sha256": payload.get("sha256"),
                "actual_sha256": actual_hash,
                "hash_match": bool(actual_hash == payload.get("sha256")) if selected else np.nan,
                "model_use": "QUARTERLY_EARNINGS_RELEASE" if selected else "NOT_SELECTED",
                "selection_reason": "CMI_PERIOD_TOKEN_AND_EX99" if selected else "NON_EARNINGS_OR_OUT_OF_WINDOW",
                "pdf_parsing_used": False,
            }
        )
    inventory = pd.DataFrame(rows)
    selected = inventory.loc[inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")]
    duplicated = selected["period"].duplicated(keep=False)
    if duplicated.any():
        periods = sorted(selected.loc[duplicated, "period"].unique())
        raise ValueError(f"CMI IR period selection is ambiguous: {periods}")
    return inventory


def _find_segment_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    for table in tables:
        text = " ".join(_label(value) for value in table.to_numpy().ravel())
        if "Total Segments" in text and "External sales" in text and "EBITDA" in text:
            return table.dropna(axis=1, how="all").reset_index(drop=True)
    raise ValueError("CMI segment EBITDA table not found")


def _header_map(table: pd.DataFrame) -> dict[str, tuple[int, int]]:
    header_index = next(
        index
        for index, row in table.iterrows()
        if any(_label(value) == "Total Segments" for value in row)
        and any(_label(value) in {"Engine", "Components"} for value in row)
    )
    header = table.iloc[header_index]
    starts: list[tuple[str, int]] = []
    for canonical, aliases in _SEGMENT_ALIASES.items():
        positions = [index for index, value in enumerate(header) if _label(value) in aliases]
        if positions:
            starts.append((canonical, min(positions)))
    starts.sort(key=lambda item: item[1])
    if len(starts) != 5:
        raise ValueError(f"Expected five CMI segments, found {starts}")
    result: dict[str, tuple[int, int]] = {}
    for index, (segment, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else next(
            position for position, value in enumerate(header) if _label(value) == "Total Segments"
        )
        result[segment] = (start, end)
    return result


def _metric_row(block: pd.DataFrame, prefixes: tuple[str, ...]) -> pd.Series | None:
    for _, row in block.iterrows():
        label = _label(row.iloc[0])
        if any(label.startswith(prefix) for prefix in prefixes):
            if "excluding" in label.lower():
                continue
            return row
    return None


def _group_value(row: pd.Series | None, start: int, end: int) -> float:
    if row is None:
        return np.nan
    values = [_number(value) for value in row.iloc[start:end]]
    values = [value for value in values if value is not None]
    if values:
        return float(values[0])
    if any(_label(value) in {"—", "-"} for value in row.iloc[start:end]):
        return 0.0
    return np.nan


def _parse_segment_release(source: pd.Series) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    tables = pd.read_html(Path(str(source["source_path"])), flavor="lxml")
    table = _find_segment_table(tables)
    columns = _header_map(table)
    period = pd.Period(str(source["period"]), freq="Q")
    markers = [
        index for index, row in table.iterrows()
        if _label(row.iloc[0]).startswith("Three months ended")
    ]
    if len(markers) < 2:
        raise ValueError(f"CMI segment table lacks current/prior quarter blocks: {source['source_path']}")
    blocks = [
        (period, table.iloc[markers[0] + 1 : markers[1]]),
        (period - 4, table.iloc[markers[1] + 1 :]),
    ]
    current_rows: list[dict[str, object]] = []
    comparable_rows: list[dict[str, object]] = []
    for block_index, (referenced, block) in enumerate(blocks):
        for segment, (start, end) in columns.items():
            values: dict[str, float] = {}
            for metric, row_prefixes in _METRICS.items():
                values[metric] = _group_value(_metric_row(block, row_prefixes), start, end) * 1e6
            values["ebitda_margin_pct"] = (
                values["ebitda_usd"] / values["total_sales_usd"] * 100.0
                if values["total_sales_usd"]
                else np.nan
            )
            row = {
                "period": str(referenced),
                "segment": segment,
                **values,
                "filing_period": str(period),
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_path": source["source_path"],
                "source_sha256": source["actual_sha256"],
                "reported_basis": "CURRENT_RELEASE" if block_index == 0 else "CURRENT_RELEASE_PRIOR_YEAR_COMPARABLE",
            }
            (current_rows if block_index == 0 else comparable_rows).append(row)
    return current_rows, comparable_rows


def _quarter_column(table: pd.DataFrame, year: int, quarter: int) -> tuple[int, int] | None:
    labels = table.map(_label)
    year_rows = [index for index, row in labels.iterrows() if any(value == str(year) for value in row)]
    if not year_rows:
        return None
    start_row = year_rows[0]
    end_row = next((index for index in year_rows[1:] if index > start_row), len(table))
    for row_index in range(start_row, min(start_row + 4, end_row)):
        positions = [index for index, value in enumerate(labels.iloc[row_index]) if value == f"Q{quarter}"]
        if positions:
            start = min(positions)
            later = [index for index, value in enumerate(labels.iloc[row_index]) if value and index > start and value != f"Q{quarter}"]
            end = min(later) if later else table.shape[1]
            return start, end
    return None


def _classify_anchor(labels: set[str], text: str) -> tuple[str, str] | None:
    if {"Total units", "Heavy-duty", "Medium-duty"}.issubset(labels):
        return "engine", "ENGINE_UNIT_SHIPMENTS"
    if {"Total units", "Industrial", "Power generation"}.issubset(labels):
        return "power_systems", "POWER_SYSTEMS_UNIT_SHIPMENTS"
    if {"Heavy-duty truck", "Off-highway", "Total sales"}.issubset(labels):
        return "engine", "ENGINE_APPLICATION_SALES"
    if {"Generator technologies", "Industrial", "Power generation", "Total sales"}.issubset(labels):
        return "power_systems", "POWER_SYSTEMS_PRODUCT_SALES"
    if {"Parts", "Service", "Engines", "Power generation", "Total sales"}.issubset(labels):
        return "distribution", "DISTRIBUTION_PRODUCT_SALES"
    if "Emission solutions" in labels and "Total sales" in labels:
        return "components", "COMPONENTS_PRODUCT_SALES"
    return None


def _parse_product_anchors(source: pd.Series) -> list[dict[str, object]]:
    period = pd.Period(str(source["period"]), freq="Q")
    tables = pd.read_html(Path(str(source["source_path"])), flavor="lxml")
    rows: list[dict[str, object]] = []
    for table_index, raw in enumerate(tables):
        table = raw.dropna(axis=1, how="all").reset_index(drop=True)
        if table.empty or table.shape[1] == 0:
            continue
        labels = {_label(value) for value in table.iloc[:, 0]}
        text = " ".join(labels)
        classified = _classify_anchor(labels, text)
        if classified is None:
            continue
        segment, group = classified
        bounds = _quarter_column(table, period.year, period.quarter)
        if bounds is None:
            continue
        start, end = bounds
        for _, row in table.iterrows():
            item = _label(row.iloc[0])
            if not item or item.startswith("(") or item in {str(period.year), "Units (1)", "In millions"}:
                continue
            values = [_number(value) for value in row.iloc[start:end]]
            values = [value for value in values if value is not None]
            if not values:
                continue
            is_units = group == "ENGINE_UNIT_SHIPMENTS"
            rows.append(
                {
                    "period": str(period),
                    "segment": segment,
                    "anchor_group": group,
                    "anchor_item": item,
                    "value": float(values[0]) * (1.0 if is_units else 1e6),
                    "unit": "units" if is_units else "USD",
                    "table_index": table_index,
                    "filing_date": source["filing_date"],
                    "source_url": source["source_url"],
                    "source_sha256": source["actual_sha256"],
                    "historical_pit_input": True,
                }
            )
    return rows


def build_cmi_ir_evidence(ir_root: Path, cutoff: pd.Timestamp) -> dict[str, pd.DataFrame]:
    inventory = _metadata_inventory(ir_root, cutoff)
    selected = inventory.loc[
        inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")
        & inventory["hash_match"].eq(True)
    ].sort_values("period")
    current: list[dict[str, object]] = []
    comparable: list[dict[str, object]] = []
    anchors: list[dict[str, object]] = []
    for _, source in selected.iterrows():
        release_current, release_comparable = _parse_segment_release(source)
        current.extend(release_current)
        comparable.extend(release_comparable)
        anchors.extend(_parse_product_anchors(source))
    history = pd.DataFrame(current).sort_values(["period", "segment"]).reset_index(drop=True)
    prior = pd.DataFrame(comparable)
    original = history[["period", "segment", "total_sales_usd", "ebitda_usd"]].rename(
        columns={"total_sales_usd": "original_total_sales_usd", "ebitda_usd": "original_ebitda_usd"}
    )
    audit = prior.merge(original, on=["period", "segment"], how="inner", validate="many_to_one")
    audit["sales_difference_usd"] = audit["total_sales_usd"] - audit["original_total_sales_usd"]
    audit["ebitda_difference_usd"] = audit["ebitda_usd"] - audit["original_ebitda_usd"]
    audit["sales_difference_pct"] = audit["sales_difference_usd"] / audit["original_total_sales_usd"].abs() * 100.0
    audit["material_scope_change"] = (
        audit["sales_difference_pct"].abs().gt(5.0)
        | audit["ebitda_difference_usd"].abs().gt(25e6)
    )
    audit["scope_treatment"] = np.where(
        audit["material_scope_change"],
        "UNFORECASTABLE_SCOPE_CHANGE",
        "COMPARABLE_AND_REPORTED_PERIMETER_ALIGNED",
    )
    anchor_frame = pd.DataFrame(anchors).drop_duplicates(
        ["period", "segment", "anchor_group", "anchor_item"], keep="last"
    )
    atmus_source = selected.loc[selected["period"].eq("2025Q1")].iloc[0]
    atmus_text = Path(str(atmus_source["source_path"])).read_text(
        encoding="utf-8", errors="ignore"
    )
    if "Atmus" not in atmus_text or "March 18, 2024" not in atmus_text:
        raise ValueError("CMI Atmus scope-event evidence was not found in the 2025Q1 release")
    scope_events = pd.DataFrame(
        [
            {
                "segment": "components",
                "affected_forecast_period": "2025Q1",
                "event_name": "ATMUS_DIVESTITURE_COMPARABILITY_BREAK",
                "effective_date": "2024-03-18",
                "evidence_period": "2025Q1",
                "evidence_type": "IR_PRODUCT_TABLE_FOOTNOTE",
                "source_url": atmus_source["source_url"],
                "source_path": atmus_source["source_path"],
                "source_sha256": atmus_source["actual_sha256"],
                "treatment": "UNFORECASTABLE_SCOPE_CHANGE",
                "component_attribution_allowed": False,
            }
        ]
    )
    group_coverage = (
        anchor_frame.groupby(["segment", "anchor_group"], as_index=False)
        .agg(
            quarters=("period", "nunique"),
            first_period=("period", "min"),
            last_period=("period", "max"),
            items=("anchor_item", "nunique"),
        )
        .sort_values(["segment", "anchor_group"])
    )
    segment_coverage = (
        history.groupby("segment", as_index=False)
        .agg(
            quarters=("period", "nunique"),
            first_period=("period", "min"),
            last_period=("period", "max"),
            sales_coverage_pct=("total_sales_usd", lambda values: values.notna().mean() * 100.0),
            ebitda_coverage_pct=("ebitda_usd", lambda values: values.notna().mean() * 100.0),
            rd_coverage_pct=("rd_engineering_usd", lambda values: values.notna().mean() * 100.0),
            da_coverage_pct=("depreciation_amortization_usd", lambda values: values.notna().mean() * 100.0),
        )
    )
    summary = pd.DataFrame(
        [
            {
                "selected_ir_releases": len(selected),
                "parsed_quarters": history["period"].nunique(),
                "parsed_segments": history["segment"].nunique(),
                "segment_quarter_rows": len(history),
                "segment_sales_coverage_pct": history["total_sales_usd"].notna().mean() * 100.0,
                "segment_ebitda_coverage_pct": history["ebitda_usd"].notna().mean() * 100.0,
                "product_anchor_rows": len(anchor_frame),
                "product_anchor_groups": anchor_frame["anchor_group"].nunique(),
                "engine_unit_quarters": anchor_frame.loc[
                    anchor_frame["anchor_group"].eq("ENGINE_UNIT_SHIPMENTS"), "period"
                ].nunique(),
                "scope_change_cells": int(audit["material_scope_change"].sum()),
                "known_transaction_scope_events": len(scope_events),
                "all_selected_hashes_match": bool(selected["hash_match"].all()),
                "parser_gate_pass": bool(
                    len(selected) == 27
                    and history["period"].nunique() == 27
                    and history["segment"].nunique() == 5
                    and history["total_sales_usd"].notna().all()
                    and history["ebitda_usd"].notna().all()
                ),
                "pdf_parsing_used": False,
            }
        ]
    )
    return {
        "cmi_ir_source_inventory": inventory,
        "cmi_segment_quarterly_history": history,
        "cmi_prior_year_comparable_history": prior,
        "cmi_cross_release_scope_audit": audit,
        "cmi_scope_event_registry": scope_events,
        "cmi_product_anchor_history": anchor_frame,
        "cmi_product_anchor_coverage": group_coverage,
        "cmi_segment_field_coverage": segment_coverage,
        "cmi_ir_parser_summary": summary,
    }
