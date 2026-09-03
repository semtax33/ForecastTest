from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


VINTAGE_COLUMNS = [
    "source",
    "dataset",
    "series_id",
    "observation_period",
    "vintage_value",
    "release_date",
    "available_at",
    "revision_number",
    "source_hash",
    "vintage_status",
    "pit_eligible",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_snapshot(path: Path, cutoff: pd.Timestamp) -> tuple[dict[str, object], pd.DataFrame]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    retrieved = pd.Timestamp(payload["retrieved_at"])
    cutoff_utc = pd.Timestamp(cutoff).tz_localize("UTC") if pd.Timestamp(cutoff).tzinfo is None else pd.Timestamp(cutoff).tz_convert("UTC")
    if retrieved > cutoff_utc + pd.Timedelta(days=1):
        raise ValueError("BLS segment-cost snapshot was unavailable at cutoff")
    rows: list[dict[str, object]] = []
    for series in payload["response"]["Results"]["series"]:
        for observation in series["data"]:
            period = str(observation["period"])
            if not period.startswith("M") or period == "M13":
                continue
            rows.append(
                {
                    "series_id": series["seriesID"],
                    "observation_date": pd.Timestamp(int(observation["year"]), int(period[1:]), 1),
                    "value": pd.to_numeric(observation["value"], errors="coerce"),
                }
            )
    return payload, pd.DataFrame(rows).dropna(subset=["value"])


def build_vintage_canonical(snapshot_path: Path, cutoff: pd.Timestamp) -> dict[str, pd.DataFrame]:
    payload, observations = _load_snapshot(snapshot_path, cutoff)
    source_hash = _sha256(snapshot_path)
    canonical = pd.DataFrame(
        {
            "source": "BLS_PUBLIC_API_V2",
            "dataset": payload["dataset"],
            "series_id": observations["series_id"],
            "observation_period": observations["observation_date"].dt.strftime("%Y-%m"),
            "vintage_value": observations["value"],
            "release_date": pd.NaT,
            "available_at": payload["retrieved_at"],
            "revision_number": pd.NA,
            "source_hash": source_hash,
            "vintage_status": "LATEST_REVISED_RELEASE_DATE_UNKNOWN",
            "pit_eligible": False,
        },
        columns=VINTAGE_COLUMNS,
    )
    schema = pd.DataFrame(
        [
            {
                "required_columns": "|".join(VINTAGE_COLUMNS),
                "schema_columns_complete": list(canonical.columns) == VINTAGE_COLUMNS,
                "observation_rows": len(canonical),
                "series_count": canonical["series_id"].nunique(),
                "release_date_coverage_pct": float(canonical["release_date"].notna().mean() * 100.0),
                "available_at_coverage_pct": float(canonical["available_at"].notna().mean() * 100.0),
                "source_hash_coverage_pct": float(canonical["source_hash"].notna().mean() * 100.0),
                "pit_eligible_rows": int(canonical["pit_eligible"].sum()),
                "historical_pit_ready": False,
                "status": "SCHEMA_READY_VINTAGE_HISTORY_DEFERRED",
            }
        ]
    )
    return {"pit_vintage_canonical": canonical, "pit_vintage_schema_audit": schema}


def _quarterly_yoy(observations: pd.DataFrame) -> pd.DataFrame:
    frame = observations.copy()
    frame["quarter"] = frame["observation_date"].dt.to_period("Q")
    monthly_counts = frame.groupby(["series_id", "quarter"])["value"].size().rename("months_in_quarter")
    quarterly = frame.groupby(["series_id", "quarter"])["value"].mean().rename("quarterly_value").to_frame().join(monthly_counts).reset_index()
    quarterly["yoy_pct"] = quarterly.groupby("series_id")["quarterly_value"].pct_change(4) * 100.0
    quarterly["full_quarter"] = quarterly["months_in_quarter"].eq(3)
    return quarterly


def build_segment_sensor_panel(
    *,
    snapshot_path: Path,
    sensor_map_path: Path,
    cutoff: pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    _, observations = _load_snapshot(snapshot_path, cutoff)
    sensors = pd.read_csv(sensor_map_path)
    missing = sorted(set(sensors["series_id"]) - set(observations["series_id"]))
    if missing:
        raise ValueError(f"BLS segment sensors missing: {missing}")
    for (segment, role), group in sensors.groupby(["segment", "role"]):
        if role in {"output_price"} and not np.isclose(group["weight"].sum(), 1.0):
            raise ValueError(f"Output-price weights must sum to one: {segment}")
    for segment, group in sensors.loc[sensors["role"].ne("output_price")].groupby("segment"):
        if not np.isclose(group["weight"].sum(), 1.0):
            raise ValueError(f"Cost weights must sum to one: {segment}")
    quarterly = _quarterly_yoy(observations)
    detail = sensors.merge(quarterly, on="series_id", how="left", validate="many_to_many")
    detail["weighted_yoy_pct"] = detail["weight"] * detail["yoy_pct"]
    detail["period"] = detail["quarter"].astype(str)
    detail["vintage_status"] = "LATEST_REVISED_NOT_HISTORICAL_PIT"
    detail["historical_pit_eligible"] = False
    complete = detail.loc[detail["full_quarter"] & detail["yoy_pct"].notna()].copy()
    output = (
        complete.loc[complete["role"].eq("output_price")]
        .groupby(["segment", "period"], as_index=False)["weighted_yoy_pct"]
        .sum()
        .rename(columns={"weighted_yoy_pct": "output_price_yoy_pct"})
    )
    cost = (
        complete.loc[complete["role"].ne("output_price")]
        .groupby(["segment", "period"], as_index=False)["weighted_yoy_pct"]
        .sum()
        .rename(columns={"weighted_yoy_pct": "dedicated_cost_yoy_pct"})
    )
    panel = output.merge(cost, on=["segment", "period"], how="inner", validate="one_to_one")
    panel["historical_pit_eligible"] = False
    coverage = (
        complete.groupby(["segment", "role"])
        .agg(series_count=("series_id", "nunique"), first_period=("period", "min"), latest_period=("period", "max"), full_quarter_observations=("period", "nunique"))
        .reset_index()
    )
    return {"segment_sensor_registry": sensors, "segment_sensor_quarterly_detail": detail, "segment_sensor_panel": panel, "segment_sensor_coverage": coverage}

