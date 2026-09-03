from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _logical_values(row: pd.Series) -> list[str]:
    values: list[str] = []
    for value in row.tolist():
        if pd.isna(value):
            continue
        text = " ".join(str(value).split())
        if text and (not values or values[-1] != text):
            values.append(text)
    return values


def _period(value: str) -> str | None:
    match = re.search(r"([1-4])(?:st|nd|rd|th) Quarter (\d{4})", value, re.IGNORECASE)
    return f"{match.group(2)}Q{match.group(1)}" if match else None


def _percent(value: str) -> float:
    upper = value.upper().replace("−", "-")
    if "UNCHANGED" in upper:
        return 0.0
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*%", upper)
    if not match:
        raise ValueError(f"Unrecognized CAT retail-sales percentage: {value}")
    amount = float(match.group(1))
    return -abs(amount) if "DOWN" in upper else abs(amount)


def _parse_source(path: Path) -> list[dict[str, object]]:
    table = pd.read_html(path)[0]
    rows: list[dict[str, object]] = []
    section: str | None = None
    periods: list[str] = []
    period_columns: list[int] = []
    metrics = {
        "Asia/Pacific": "asia_pacific_retail_yoy_pct",
        "EAME": "eame_retail_yoy_pct",
        "Latin America": "latin_america_retail_yoy_pct",
        "North America": "north_america_retail_yoy_pct",
        "World": "world_retail_yoy_pct",
        "Total": "world_retail_yoy_pct",
    }
    for _, raw in table.iterrows():
        values = _logical_values(raw)
        if not values:
            continue
        label = values[0]
        if label.startswith("Resource Industries"):
            section = "resource"
        elif label.startswith("Construction Industries"):
            section = "construction"
        elif (
            label.startswith("Energy & Transportation (E&T)")
            or label.startswith("Power & Energy (P&E)")
        ) and len(values) > 1:
            section = "power_energy"
        if section and len(values) > 1 and any("Quarter" in value for value in values[1:]):
            periods = []
            period_columns = []
            prior_period: str | None = None
            for column, raw_value in enumerate(raw.tolist()):
                parsed_period = _period(str(raw_value)) if pd.notna(raw_value) else None
                if parsed_period and parsed_period != prior_period:
                    periods.append(parsed_period)
                    period_columns.append(column)
                    prior_period = parsed_period
            continue
        if section is None or not periods or label not in metrics:
            continue
        if section == "power_energy" and label != "Total":
            continue
        observations = [raw.iloc[column] for column in period_columns]
        if len(observations) != len(periods):
            continue
        for period, observation in zip(periods, observations):
            rows.append(
                {
                    "period": period,
                    "segment": section,
                    "metric": metrics[label],
                    "vintage_value": _percent(observation),
                }
            )
    return rows


def build_cat_retail_history(ir_directory: Path, cutoff: pd.Timestamp) -> dict[str, pd.DataFrame]:
    parsed: list[dict[str, object]] = []
    source_rows: list[dict[str, object]] = []
    for path in sorted(ir_directory.glob("*.htm")):
        if b"quarterly retail sales statistics" not in path.read_bytes().lower():
            continue
        metadata_path = path.with_name(path.name + ".metadata.json")
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        filing_date = pd.Timestamp(metadata["filing_date"])
        if filing_date > cutoff:
            continue
        actual_hash = _sha256(path)
        if actual_hash != metadata["sha256"]:
            raise ValueError(f"CAT retail IR hash mismatch: {path}")
        observations = _parse_source(path)
        for row in observations:
            parsed.append(
                {
                    **row,
                    "release_date": filing_date.date().isoformat(),
                    "available_at": filing_date.date().isoformat(),
                    "source_path": str(path),
                    "source_url": metadata["source_url"],
                    "source_sha256": actual_hash,
                    "pit_eligible": True,
                }
            )
        source_rows.append(
            {
                "filing_date": filing_date.date().isoformat(),
                "source_path": str(path),
                "source_url": metadata["source_url"],
                "source_sha256": actual_hash,
                "parsed_observations": len(observations),
                "hash_match": True,
            }
        )
    vintages = pd.DataFrame(parsed).drop_duplicates(
        ["period", "segment", "metric", "release_date"]
    ).sort_values(["period", "segment", "metric", "release_date"]).reset_index(drop=True)
    vintages["revision_number"] = vintages.groupby(["period", "segment", "metric"]).cumcount()
    value_ranges = vintages.groupby(["period", "segment", "metric"])["vintage_value"].agg(["min", "max"]).reset_index()
    value_ranges["cross_release_exact"] = np.isclose(value_ranges["min"], value_ranges["max"])
    latest = vintages.loc[vintages.groupby(["period", "segment", "metric"])["release_date"].idxmax()].copy()
    panel = latest.pivot(index=["period", "segment"], columns="metric", values="vintage_value").reset_index()
    construction_regions = [
        "asia_pacific_retail_yoy_pct", "eame_retail_yoy_pct",
        "latin_america_retail_yoy_pct", "north_america_retail_yoy_pct",
    ]
    panel["regional_dispersion_pct"] = panel[construction_regions].std(axis=1, ddof=0, skipna=True)
    panel["historical_pit_eligible"] = True
    audit = pd.DataFrame(
        [
            {
                "source_files": len(source_rows),
                "source_hash_mismatches": 0,
                "vintage_rows": len(vintages),
                "quarters": vintages["period"].nunique(),
                "segments": vintages["segment"].nunique(),
                "cross_release_cells": len(value_ranges),
                "cross_release_exact_cells": int(value_ranges["cross_release_exact"].sum()),
                "cross_release_changed_cells": int((~value_ranges["cross_release_exact"]).sum()),
                "pit_eligible_rows": int(vintages["pit_eligible"].sum()),
                "retail_pit_ready": bool(vintages["pit_eligible"].all()),
            }
        ]
    )
    return {
        "cat_retail_ir_sources": pd.DataFrame(source_rows),
        "cat_retail_vintages": vintages,
        "cat_retail_cross_release_audit": value_ranges,
        "cat_retail_quarterly_panel": panel,
        "cat_retail_parser_audit": audit,
    }
