from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from lxml import html
import numpy as np
import pandas as pd


SEGMENTS = (
    "aeronautics",
    "missiles_fire_control",
    "rotary_mission_systems",
    "space",
)
SEGMENT_LABELS = {
    "Aeronautics": "aeronautics",
    "Missiles and Fire Control": "missiles_fire_control",
    "Rotary and Mission Systems": "rotary_mission_systems",
    "Space": "space",
}
_PERIOD = re.compile(r"q([1-4])(20\d{2})", re.IGNORECASE)


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


def _metadata_inventory(ir_root: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metadata_path in sorted(ir_root.glob("*.metadata.json")):
        html_path = metadata_path.with_name(metadata_path.name.removesuffix(".metadata.json"))
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        filing_date = pd.Timestamp(payload["filing_date"])
        match = _PERIOD.search(str(payload.get("document_name", "")))
        period = f"{match.group(2)}Q{match.group(1)}" if match else None
        selected = bool(
            period
            and pd.Period(period, freq="Q") >= pd.Period("2019Q4", freq="Q")
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
                "document_name": payload.get("document_name"),
                "source_url": payload.get("source_url"),
                "source_path": str(html_path),
                "metadata_sha256": payload.get("sha256"),
                "actual_sha256": actual_hash,
                "hash_match": bool(actual_hash == payload.get("sha256")) if selected else np.nan,
                "model_use": "QUARTERLY_EARNINGS_RELEASE" if selected else "NOT_SELECTED",
                "selection_reason": "LMT_Q_TOKEN_EX99_2019Q4_FORWARD" if selected else "NON_EARNINGS_OR_OUT_OF_WINDOW",
                "pdf_parsing_used": False,
            }
        )
    inventory = pd.DataFrame(rows)
    selected = inventory.loc[inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE")]
    duplicates = selected["period"].duplicated(keep=False)
    if duplicates.any():
        raise ValueError(f"Ambiguous LMT earnings releases: {sorted(selected.loc[duplicates, 'period'].unique())}")
    return inventory


def _contiguous_runs(mask: list[bool]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(mask + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append((start, index))
            start = None
    return runs


def _quarter_blocks(table: pd.DataFrame) -> list[tuple[int, int]]:
    for row_index, row in table.iterrows():
        mask = ["quarters ended" in _label(value).lower() for value in row]
        runs = [run for run in _contiguous_runs(mask) if run[1] - run[0] >= 2]
        if len(runs) >= 2:
            return runs[:2]
        if any(mask):
            # HTML colspans can forward-fill the quarter heading across the
            # blank separator.  The following date/year row still retains the
            # two independently disclosed quarter groups.
            for next_index in range(row_index + 1, min(row_index + 3, len(table))):
                next_row = table.iloc[next_index]
                next_mask = [
                    _label(value).lower() not in {"", "nan"}
                    and index >= min((i for i, marked in enumerate(mask) if marked), default=0)
                    for index, value in enumerate(next_row)
                ]
                date_runs = [run for run in _contiguous_runs(next_mask) if run[1] - run[0] >= 2]
                if len(date_runs) >= 2:
                    return date_runs[:2]
    raise ValueError("Quarter current/comparable column groups not found")


def _row_with_label(table: pd.DataFrame, labels: tuple[str, ...]) -> pd.Series:
    for _, row in table.iterrows():
        values = [_label(value).lower() for value in row if _label(value).lower() != "nan"]
        if any(
            value == label.lower() or re.fullmatch(re.escape(label.lower()) + r"\d+", value)
            for label in labels
            for value in values
        ):
            return row
    raise ValueError(f"Metric row not found: {labels}")


def _block_number(row: pd.Series, block: tuple[int, int]) -> float:
    values = [_number(value) for value in row.iloc[block[0] : block[1]]]
    values = [value for value in values if value is not None]
    return float(values[0]) if values else 0.0


def _segment_heading(tree: html.HtmlElement, table_index: int) -> str | None:
    nodes = tree.xpath("//table")
    if table_index >= len(nodes):
        return None
    preceding = nodes[table_index].xpath("preceding::*[self::div or self::p or self::span]")
    for node in reversed(preceding):
        value = _label(" ".join(node.itertext()))
        if value in SEGMENT_LABELS:
            return SEGMENT_LABELS[value]
    return None


def _segment_candidates(tables: list[pd.DataFrame]) -> list[int]:
    result: list[int] = []
    for index, table in enumerate(tables):
        labels = {_label(value).lower() for value in table.to_numpy().ravel()}
        has_sales = bool({"sales", "net sales"} & labels)
        has_profit = bool({"operating profit", "operating (loss) profit", "operating profit (loss)"} & labels)
        if has_sales and has_profit and "operating margin" in labels:
            result.append(index)
    return result


def _parse_segments(source: pd.Series) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    source_path = Path(str(source["source_path"]))
    tables = pd.read_html(source_path, flavor="lxml")
    tree = html.fromstring(source_path.read_bytes())
    candidates = _segment_candidates(tables)
    # Every release in the audited window presents the four segment result
    # tables in the same disclosed order.  The nearby prose heading occurs
    # after (rather than before) the table in some Workiva HTML vintages, so
    # DOM "preceding heading" inference would shift the names by one table.
    mapped = list(zip(SEGMENTS, candidates[:4]))
    if len(mapped) != 4:
        raise ValueError(f"Expected four LMT segment tables in {source_path}; found {mapped}")

    filing_period = pd.Period(str(source["period"]), freq="Q")
    current_rows: list[dict[str, object]] = []
    comparable_rows: list[dict[str, object]] = []
    for segment, table_index in mapped:
        table = tables[table_index]
        current_block, prior_block = _quarter_blocks(table)
        sales = _row_with_label(table, ("Sales", "Net sales"))
        profit = _row_with_label(table, ("Operating profit", "Operating (loss) profit", "Operating profit (loss)"))
        for block_index, (period, block) in enumerate(((filing_period, current_block), (filing_period - 4, prior_block))):
            sales_usd = _block_number(sales, block) * 1e6
            operating_profit_usd = _block_number(profit, block) * 1e6
            row = {
                "period": str(period),
                "segment": segment,
                "sales_usd": sales_usd,
                "operating_profit_usd": operating_profit_usd,
                "operating_margin_pct": operating_profit_usd / sales_usd * 100.0 if sales_usd else np.nan,
                "filing_period": str(filing_period),
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_path": source["source_path"],
                "source_sha256": source["actual_sha256"],
                "table_index": table_index,
                "segment_heading_resolved": segment,
                "segment_resolution_method": "AUDITED_DISCLOSED_TABLE_ORDER",
                "reported_basis": "CURRENT_RELEASE" if block_index == 0 else "CURRENT_RELEASE_PRIOR_YEAR_COMPARABLE",
            }
            (current_rows if block_index == 0 else comparable_rows).append(row)
    return current_rows, comparable_rows


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


def _find_table(tables: list[pd.DataFrame], required: tuple[str, ...]) -> tuple[int, pd.DataFrame]:
    for index, table in enumerate(tables):
        text = " ".join(_label(value) for value in table.to_numpy().ravel()).lower()
        if all(item.lower() in text for item in required):
            return index, table
    raise ValueError(f"LMT table not found: {required}")


def _parse_backlog(source: pd.Series, tables: list[pd.DataFrame]) -> list[dict[str, object]]:
    table_index, table = _find_table(tables, ("Backlog", "Total backlog", "Missiles and Fire Control"))
    rows: list[dict[str, object]] = []
    for reported, segment in SEGMENT_LABELS.items():
        row = _row_with_label(table, (reported,))
        values = _numeric_clusters(row, start=1)
        if not values:
            raise ValueError(f"Missing {reported} backlog in {source['source_path']}")
        rows.append(
            {
                "period": source["period"],
                "segment": segment,
                "backlog_usd": values[0] * 1e6,
                "comparison_backlog_usd": values[1] * 1e6 if len(values) > 1 else np.nan,
                "comparison_basis": "PRIOR_FISCAL_YEAR_END",
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_sha256": source["actual_sha256"],
                "table_index": table_index,
                "historical_pit_input": True,
            }
        )
    return rows


def _parse_deliveries(source: pd.Series, tables: list[pd.DataFrame]) -> list[dict[str, object]]:
    table_index, table = _find_table(tables, ("Aircraft Deliveries", "F-35", "C-130J"))
    current_block, prior_block = _quarter_blocks(table)
    items = (
        "F-35",
        "F-16",
        "C-130J",
        "C-5",
        "Government helicopter programs",
        "Commercial helicopter programs",
        "International military helicopter programs",
    )
    rows: list[dict[str, object]] = []
    for item in items:
        try:
            row = _row_with_label(table, (item,))
        except ValueError:
            continue
        rows.append(
            {
                "period": source["period"],
                "delivery_program": item,
                "segment": "aeronautics" if item in {"F-35", "F-16", "C-130J"} else "rotary_mission_systems",
                "quarter_deliveries": _block_number(row, current_block),
                "prior_year_quarter_deliveries": _block_number(row, prior_block),
                "filing_date": source["filing_date"],
                "source_url": source["source_url"],
                "source_sha256": source["actual_sha256"],
                "table_index": table_index,
                "historical_pit_input": True,
            }
        )
    return rows


def _parse_program_losses(source: pd.Series, tables: list[pd.DataFrame]) -> list[dict[str, object]]:
    mapping = {
        "aeronautics classified program loss": "aeronautics",
        "aeronautics classified program losses": "aeronautics",
        "aero classified program losses": "aeronautics",
        "mfc classified program losses": "missiles_fire_control",
        "cmhp program loss": "rotary_mission_systems",
        "tuhp program loss": "rotary_mission_systems",
        "rms program losses": "rotary_mission_systems",
    }
    rows: list[dict[str, object]] = []
    for table_index, table in enumerate(tables):
        for _, row in table.iterrows():
            labels = [_label(value) for value in row]
            matched = next(
                (
                    canonical
                    for canonical in mapping
                    for label in labels
                    if label.lower() == canonical or re.fullmatch(re.escape(canonical) + r"\d+", label.lower())
                ),
                None,
            )
            if matched is None:
                continue
            try:
                current_block = _quarter_blocks(table)[0]
                amount = abs(_block_number(row, current_block))
            except ValueError:
                values = _numeric_clusters(row, start=1)
                amount = abs(values[0]) if values else 0.0
            if amount == 0.0:
                continue
            rows.append(
                {
                    "period": source["period"],
                    "segment": mapping[matched],
                    "program_loss_name": matched.upper().replace(" ", "_"),
                    "pretax_program_loss_usd": amount * 1e6,
                    "filing_date": source["filing_date"],
                    "source_url": source["source_url"],
                    "source_sha256": source["actual_sha256"],
                    "table_index": table_index,
                    "normalization_treatment": "EXCLUDE_FROM_POINT_PERFORMANCE_CLAIM_KEEP_RAW_ACTUAL",
                    "terminal_input_allowed": False,
                }
            )
    return rows


def build_lmt_ir_evidence(ir_root: Path, cutoff: pd.Timestamp) -> dict[str, pd.DataFrame]:
    inventory = _metadata_inventory(ir_root, cutoff)
    selected = inventory.loc[
        inventory["model_use"].eq("QUARTERLY_EARNINGS_RELEASE") & inventory["hash_match"].eq(True)
    ].sort_values("period")
    current: list[dict[str, object]] = []
    comparable: list[dict[str, object]] = []
    backlog: list[dict[str, object]] = []
    deliveries: list[dict[str, object]] = []
    losses: list[dict[str, object]] = []
    for _, source in selected.iterrows():
        release_current, release_comparable = _parse_segments(source)
        tables = pd.read_html(Path(str(source["source_path"])), flavor="lxml")
        current.extend(release_current)
        comparable.extend(release_comparable)
        backlog.extend(_parse_backlog(source, tables))
        deliveries.extend(_parse_deliveries(source, tables))
        losses.extend(_parse_program_losses(source, tables))
    history = pd.DataFrame(current).sort_values(["period", "segment"]).reset_index(drop=True)
    prior = pd.DataFrame(comparable)
    original = history[["period", "segment", "sales_usd", "operating_profit_usd"]].rename(
        columns={"sales_usd": "original_sales_usd", "operating_profit_usd": "original_operating_profit_usd"}
    )
    scope = prior.merge(original, on=["period", "segment"], how="inner", validate="many_to_one")
    scope["sales_difference_usd"] = scope["sales_usd"] - scope["original_sales_usd"]
    scope["operating_profit_difference_usd"] = scope["operating_profit_usd"] - scope["original_operating_profit_usd"]
    scope["sales_difference_pct"] = scope["sales_difference_usd"] / scope["original_sales_usd"].abs() * 100.0
    scope["material_scope_change"] = scope["sales_difference_pct"].abs().gt(5.0)
    scope["scope_treatment"] = np.where(scope["material_scope_change"], "UNFORECASTABLE_SCOPE_CHANGE", "COMPARABLE_PERIMETER_ALIGNED")

    backlog_frame = pd.DataFrame(backlog)
    deliveries_frame = pd.DataFrame(deliveries)
    delivery_summary = deliveries_frame.groupby(["period", "segment"], as_index=False).agg(
        deliveries=("quarter_deliveries", "sum"),
        delivery_programs=("delivery_program", "nunique"),
        filing_date=("filing_date", "first"),
        source_url=("source_url", "first"),
        source_sha256=("source_sha256", "first"),
    )
    loss_frame = pd.DataFrame(losses, columns=[
        "period", "segment", "program_loss_name", "pretax_program_loss_usd", "filing_date",
        "source_url", "source_sha256", "table_index", "normalization_treatment", "terminal_input_allowed",
    ]).drop_duplicates(["period", "segment", "program_loss_name"])
    coverage = history.groupby("segment", as_index=False).agg(
        quarters=("period", "nunique"),
        first_period=("period", "min"),
        last_period=("period", "max"),
        sales_coverage_pct=("sales_usd", lambda values: values.notna().mean() * 100.0),
        operating_profit_coverage_pct=("operating_profit_usd", lambda values: values.notna().mean() * 100.0),
        heading_resolved_pct=("segment_heading_resolved", lambda values: values.notna().mean() * 100.0),
    )
    summary = pd.DataFrame([{
        "selected_ir_releases": len(selected),
        "parsed_quarters": history["period"].nunique(),
        "parsed_segments": history["segment"].nunique(),
        "segment_quarter_rows": len(history),
        "segment_sales_coverage_pct": history["sales_usd"].notna().mean() * 100.0,
        "segment_operating_profit_coverage_pct": history["operating_profit_usd"].notna().mean() * 100.0,
        "backlog_segment_quarter_rows": len(backlog_frame),
        "backlog_coverage_pct": len(backlog_frame) / (len(selected) * 4) * 100.0,
        "delivery_program_quarter_rows": len(deliveries_frame),
        "delivery_period_coverage_pct": deliveries_frame["period"].nunique() / len(selected) * 100.0,
        "program_loss_rows": len(loss_frame),
        "material_scope_change_cells": int(scope["material_scope_change"].sum()),
        "all_selected_hashes_match": bool(selected["hash_match"].all()),
        "parser_gate_pass": bool(len(selected) == 27 and len(history) == 108 and len(backlog_frame) == 108 and history[["sales_usd", "operating_profit_usd"]].notna().all().all()),
        "pdf_parsing_used": False,
    }])
    return {
        "lmt_ir_source_inventory": inventory,
        "lmt_segment_quarterly_history": history,
        "lmt_prior_year_comparable_history": prior,
        "lmt_cross_release_scope_audit": scope,
        "lmt_backlog_history": backlog_frame,
        "lmt_aircraft_delivery_history": deliveries_frame,
        "lmt_delivery_segment_summary": delivery_summary,
        "lmt_program_loss_registry": loss_frame,
        "lmt_segment_field_coverage": coverage,
        "lmt_ir_parser_summary": summary,
    }
