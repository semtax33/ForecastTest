from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from equity_platform.sectors.industrials.aerospace_defense.lmt.industry import (
    build_lmt_industry_evidence,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _labor_context(path: Path, maximum_reference_period: str) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for series in payload["response"]["Results"]["series"]:
        series_id = series["seriesID"]
        for item in series["data"]:
            if item["period"] == "M13":
                continue
            reference_period = f"{item['year']}{item['period']}"
            if reference_period > maximum_reference_period:
                continue
            rows.append(
                {
                    "series_id": series_id,
                    "series_title": payload["series_titles"][series_id],
                    "reference_period": reference_period,
                    "value": float(item["value"]),
                    "preliminary": any(
                        note.get("code") == "P" for note in item.get("footnotes", [])
                    ),
                    "source": payload["source"],
                    "source_url": payload["source_url"],
                    "source_path": str(path),
                    "source_sha256": _sha256(path),
                    "historical_pit_eligible": False,
                    "model_input_allowed": False,
                    "authority": "CURRENT_REVISED_MARINE_LABOR_CONTEXT_ONLY",
                }
            )
    return pd.DataFrame(rows).sort_values(["series_id", "reference_period"])


def build_gd_industry_evidence(
    *,
    arcana_pqci_root: Path,
    labor_snapshot_path: Path,
    labor_maximum_reference_period: str,
    sensor_map: pd.DataFrame,
    bls_vintage_audit: pd.DataFrame,
    pit_feature_summary: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    base = build_lmt_industry_evidence(
        arcana_pqci_root=arcana_pqci_root,
        sensor_map=sensor_map,
        bls_vintage_audit=bls_vintage_audit,
        pit_feature_summary=pit_feature_summary,
    )
    renamed = {key.replace("lmt_", "gd_"): value for key, value in base.items()}
    labor = _labor_context(labor_snapshot_path, labor_maximum_reference_period)
    authority = renamed["gd_industry_sensor_authority"].copy()
    authority = pd.concat(
        [
            authority,
            labor[["source", "series_id", "series_title", "authority"]]
            .drop_duplicates()
            .rename(columns={"series_title": "title"})
            .assign(
                dataset="CES_CURRENT_REVISED",
                role="marine_labor_context",
                segments="marine_systems",
                historical_pit_eligible=False,
                model_input_allowed=False,
            ),
        ],
        ignore_index=True,
    )
    summary = renamed["gd_industry_data_summary"].copy()
    summary["marine_labor_context_series"] = labor["series_id"].nunique()
    summary["marine_labor_context_rows"] = len(labor)
    summary["marine_labor_source_sha256"] = _sha256(labor_snapshot_path)
    summary["current_revised_labor_used_in_oos_claim"] = False
    renamed["gd_industry_sensor_authority"] = authority
    renamed["gd_industry_data_summary"] = summary
    renamed["gd_marine_labor_current_revised_context"] = labor
    return renamed
