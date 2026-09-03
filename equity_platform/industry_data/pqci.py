from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _load_snapshot(path: Path, cutoff: pd.Timestamp) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    retrieved_at = pd.Timestamp(payload["retrieved_at"])
    if retrieved_at.tzinfo is not None:
        retrieved_at = retrieved_at.tz_convert(None)
    if retrieved_at > pd.Timestamp(cutoff):
        raise ValueError(f"Industry snapshot was unavailable at cutoff: {path}")
    return payload


def load_census_m3_snapshot(path: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    payload = _load_snapshot(path, cutoff)
    response = payload["response"]
    frame = pd.DataFrame(response[1:], columns=response[0])
    frame["observation_date"] = pd.to_datetime(frame["time"], errors="raise")
    frame["value"] = pd.to_numeric(frame["cell_value"], errors="coerce")
    frame["retrieved_at"] = pd.Timestamp(payload["retrieved_at"])
    frame["source"] = "CENSUS_M3"
    frame["vintage_status"] = "LATEST_REVISED_SNAPSHOT_NO_HISTORICAL_RELEASE_DATE"
    frame["historical_pit_backtest_eligible"] = False
    return frame.loc[
        frame["observation_date"].le(pd.Timestamp(cutoff))
        & frame["value"].notna()
        & frame["error_data"].eq("no")
    ].reset_index(drop=True)


def load_bls_snapshot(path: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    payload = _load_snapshot(path, cutoff)
    rows: list[dict[str, object]] = []
    for series in payload["response"]["Results"]["series"]:
        for observation in series["data"]:
            period = str(observation["period"])
            if not period.startswith("M") or period == "M13":
                continue
            value = pd.to_numeric(observation["value"], errors="coerce")
            rows.append(
                {
                    "series_id": series["seriesID"],
                    "observation_date": pd.Timestamp(
                        year=int(observation["year"]),
                        month=int(period[1:]),
                        day=1,
                    ),
                    "value": value,
                    "footnote": "|".join(
                        str(item.get("text", ""))
                        for item in observation.get("footnotes", [])
                        if item.get("text")
                    ),
                }
            )
    frame = pd.DataFrame(rows)
    frame["retrieved_at"] = pd.Timestamp(payload["retrieved_at"])
    frame["source"] = "BLS_PUBLIC_API"
    frame["vintage_status"] = "LATEST_REVISED_SNAPSHOT_NO_HISTORICAL_RELEASE_DATE"
    frame["historical_pit_backtest_eligible"] = False
    return frame.loc[
        frame["observation_date"].le(pd.Timestamp(cutoff)) & frame["value"].notna()
    ].reset_index(drop=True)
