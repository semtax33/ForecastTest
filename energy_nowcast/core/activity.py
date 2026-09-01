from __future__ import annotations

import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from ..data.cutoff import quarter_cutoff_date


RIG_URLS = {
    "total_rigs": "https://www.eia.gov/dnav/ng/hist/e_ertrr0_xr0_nus_cm.htm",
    "oil_rigs": "https://www.eia.gov/dnav/ng/hist/e_ertrro_xr0_nus_cm.htm",
    "gas_rigs": "https://www.eia.gov/dnav/ng/hist/e_ertrrg_xr0_nus_cm.htm",
}


def _parse_rig_series(name: str, url: str) -> pd.DataFrame:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    table = next(frame for frame in tables if "Year" in frame.columns and len(frame) > 20)
    month_numbers = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }
    rows: list[dict[str, object]] = []
    for _, row in table.iterrows():
        year = pd.to_numeric(row["Year"], errors="coerce")
        if not np.isfinite(year):
            continue
        for label, month in month_numbers.items():
            value = pd.to_numeric(str(row[label]).replace(",", ""), errors="coerce")
            if not np.isfinite(value):
                continue
            period = pd.Period(f"{int(year)}-{month:02d}", freq="M")
            rows.append({
                "series": name,
                "observation_date": period.end_time.normalize(),
                "available_at": (period + 1).end_time.normalize(),
                "value": float(value),
                "source_url": url,
            })
    return pd.DataFrame(rows).sort_values("observation_date")


def refresh_rig_snapshot(snapshot_dir: Path) -> pd.DataFrame:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.concat(
        [_parse_rig_series(name, url) for name, url in RIG_URLS.items()],
        ignore_index=True,
    )
    frame.to_csv(snapshot_dir / "rig_monthly.csv", index=False)
    coverage = frame.groupby("series", as_index=False).agg(
        observations=("value", "size"),
        first_date=("observation_date", "min"),
        last_date=("observation_date", "max"),
        source_url=("source_url", "last"),
    )
    coverage.to_csv(snapshot_dir / "source_coverage.csv", index=False)
    (snapshot_dir / "metadata.json").write_text(
        json.dumps({
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "availability_policy": "monthly_average_available_next_month_end",
            "paid_market_data_used": False,
        }, indent=2),
        encoding="utf-8",
    )
    return frame


def load_rig_snapshot(snapshot_dir: Path) -> pd.DataFrame:
    path = snapshot_dir / "rig_monthly.csv"
    if not path.exists():
        raise FileNotFoundError(f"Rig snapshot missing: {path}")
    frame = pd.read_csv(path)
    frame["observation_date"] = pd.to_datetime(frame["observation_date"])
    frame["available_at"] = pd.to_datetime(frame["available_at"])
    return frame


def rig_features_for_quarters(
    rig_data: pd.DataFrame,
    quarters: list[str] | tuple[str, ...],
    cutoff_day: int = 61,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for quarter in sorted(set(map(str, quarters)), key=lambda value: pd.Period(value, "Q")):
        cutoff = quarter_cutoff_date(quarter, cutoff_day)
        prior_cutoff = cutoff - pd.DateOffset(years=1)
        row: dict[str, object] = {
            "target_quarter": quarter,
            "rig_cutoff_date": cutoff,
        }
        for series in RIG_URLS:
            current = rig_data.loc[
                rig_data["series"].eq(series)
                & rig_data["available_at"].le(cutoff)
            ].sort_values("observation_date")
            prior = rig_data.loc[
                rig_data["series"].eq(series)
                & rig_data["available_at"].le(prior_cutoff)
            ].sort_values("observation_date")
            current_value = float(current["value"].iloc[-1]) if len(current) else np.nan
            prior_value = float(prior["value"].iloc[-1]) if len(prior) else np.nan
            row[series] = current_value
            row[f"{series}_observation_date"] = (
                current["observation_date"].iloc[-1] if len(current) else pd.NaT
            )
            row[f"{series}_available_at"] = (
                current["available_at"].iloc[-1] if len(current) else pd.NaT
            )
            row[f"{series}_log_yoy"] = (
                100.0 * np.log(current_value / prior_value)
                if current_value > 0 and prior_value > 0
                else np.nan
            )
        rows.append(row)
    result = pd.DataFrame(rows)
    for column in [name for name in result if name.endswith("_available_at")]:
        if pd.to_datetime(result[column], errors="coerce").gt(
            pd.to_datetime(result["rig_cutoff_date"])
        ).any():
            raise AssertionError(f"Post-cutoff rig observation selected: {column}")
    return result
