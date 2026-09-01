from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from ...data.cutoff import quarter_cutoff_date


FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
EIA_INVENTORY_URL = (
    "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?"
    "f=W&n=PET&s=WCESTUS1"
)
EIA_CURVE_1_URL = "https://www.eia.gov/dnav/pet/hist/rclc1D.htm"
EIA_CURVE_2_URL = "https://www.eia.gov/dnav/pet/hist/rclc2D.htm"
EIA_RIG_URL = "https://www.eia.gov/dnav/ng/hist/e_ertrro_xr0_nus_cm.htm"

OIL_FEATURES = (
    "ovx_regime_z",
    "wti_curve_slope_pct",
    "crude_inventory_z",
    "oil_rig_z",
    "dxy_regime_z",
)
MIXED_FEATURES = (
    "ovx_regime_z",
    "wti_curve_slope_pct",
    "henry_regime_z",
    "crude_inventory_z",
    "oil_gas_regime_spread",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _get_text(url: str) -> str:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.text


def _fred_series(series: str, availability_lag_days: int) -> pd.DataFrame:
    frame = pd.read_csv(StringIO(_get_text(FRED_URL.format(series=series))))
    frame.columns = ["date", "value"]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["date", "value"])
    frame["availability_date"] = frame["date"] + pd.Timedelta(days=availability_lag_days)
    frame["series"] = series
    frame["source_url"] = FRED_URL.format(series=series)
    return frame[["series", "date", "availability_date", "value", "source_url"]]


def _inventory_series() -> pd.DataFrame:
    tables = pd.read_html(StringIO(_get_text(EIA_INVENTORY_URL)))
    table = next(frame for frame in tables if frame.shape[1] == 13 and len(frame) > 100)
    rows: list[dict[str, object]] = []
    for _, row in table.iterrows():
        year_month = str(row.iloc[0])
        if len(year_month) < 4 or not year_month[:4].isdigit():
            continue
        year = int(year_month[:4])
        for offset in range(1, 12, 2):
            date_value = row.iloc[offset]
            stock_value = row.iloc[offset + 1]
            if pd.isna(date_value) or pd.isna(stock_value):
                continue
            date = pd.to_datetime(f"{year}-{date_value}", errors="coerce")
            value = pd.to_numeric(str(stock_value).replace(",", ""), errors="coerce")
            if pd.isna(date) or not np.isfinite(value):
                continue
            rows.append({
                "series": "EIA_CRUDE_INVENTORY_EX_SPR",
                "date": date,
                # Friday reference week is published in the following WPSR.
                "availability_date": date + pd.Timedelta(days=5),
                "value": float(value),
                "source_url": EIA_INVENTORY_URL,
            })
    return pd.DataFrame(rows).drop_duplicates("date").sort_values("date")


def _daily_eia_table(url: str, series: str) -> pd.DataFrame:
    tables = pd.read_html(StringIO(_get_text(url)))
    table = next(
        frame for frame in tables
        if "Week Of" in frame.columns and {"Mon", "Tue", "Wed", "Thu", "Fri"}.issubset(frame.columns)
    )
    rows: list[dict[str, object]] = []
    offsets = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
    for _, row in table.iterrows():
        match = re.match(
            r"^(\d{4})\s+([A-Za-z]{3})-\s*(\d{1,2})",
            str(row["Week Of"]),
        )
        week = (
            pd.to_datetime(
                f"{match.group(1)}-{match.group(2)}-{match.group(3)}",
                format="%Y-%b-%d",
                errors="coerce",
            )
            if match
            else pd.NaT
        )
        if pd.isna(week):
            continue
        for day, offset in offsets.items():
            value = pd.to_numeric(str(row[day]).replace(",", ""), errors="coerce")
            if not np.isfinite(value):
                continue
            date = week + pd.Timedelta(days=offset)
            rows.append({
                "series": series,
                "date": date,
                # EIA republishes these legacy NYMEX observations weekly.
                "availability_date": date + pd.Timedelta(days=7),
                "value": float(value),
                "source_url": url,
            })
    return pd.DataFrame(rows).drop_duplicates("date").sort_values("date")


def _rig_series() -> pd.DataFrame:
    tables = pd.read_html(StringIO(_get_text(EIA_RIG_URL)))
    table = next(frame for frame in tables if "Year" in frame.columns and len(frame) > 30)
    rows: list[dict[str, object]] = []
    months = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }
    for _, row in table.iterrows():
        year = pd.to_numeric(row["Year"], errors="coerce")
        if not np.isfinite(year):
            continue
        for label, month in months.items():
            value = pd.to_numeric(str(row[label]).replace(",", ""), errors="coerce")
            if not np.isfinite(value):
                continue
            period = pd.Period(f"{int(year)}-{month:02d}", freq="M")
            date = period.end_time.normalize()
            rows.append({
                "series": "EIA_US_CRUDE_OIL_RIGS",
                "date": date,
                # Monthly average is conservatively available at next month-end.
                "availability_date": (period + 1).end_time.normalize(),
                "value": float(value),
                "source_url": EIA_RIG_URL,
            })
    return pd.DataFrame(rows).drop_duplicates("date").sort_values("date")


def _local_price_series(path: Path) -> pd.DataFrame:
    source = pd.read_csv(path)
    source["date"] = pd.to_datetime(source["date"], errors="coerce")
    rows = []
    for column, series in (("wti", "EIA_WTI_SPOT"), ("henry", "EIA_HENRY_SPOT")):
        part = source[["date", column]].rename(columns={column: "value"}).copy()
        part["value"] = pd.to_numeric(part["value"], errors="coerce")
        part = part.dropna()
        part["series"] = series
        part["availability_date"] = part["date"] + pd.Timedelta(days=7)
        part["source_url"] = str(path.resolve())
        rows.append(part[["series", "date", "availability_date", "value", "source_url"]])
    return pd.concat(rows, ignore_index=True)


def refresh_macro_snapshot(snapshot_dir: Path, local_price_path: Path) -> pd.DataFrame:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    cl1 = _daily_eia_table(EIA_CURVE_1_URL, "EIA_WTI_FUTURES_1")
    cl2 = _daily_eia_table(EIA_CURVE_2_URL, "EIA_WTI_FUTURES_2")
    combined = pd.concat([
        _fred_series("OVXCLS", availability_lag_days=1),
        _fred_series("DTWEXBGS", availability_lag_days=7),
        _inventory_series(),
        _rig_series(),
        cl1,
        cl2,
        _local_price_series(local_price_path),
    ], ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    combined["availability_date"] = pd.to_datetime(combined["availability_date"])
    combined = combined.sort_values(["series", "date"]).reset_index(drop=True)
    path = snapshot_dir / "macro_series.csv"
    combined.to_csv(path, index=False)
    coverage = combined.groupby("series", as_index=False).agg(
        observations=("value", "size"),
        first_date=("date", "min"),
        last_date=("date", "max"),
        last_available_date=("availability_date", "max"),
        source_url=("source_url", "last"),
    )
    coverage.to_csv(snapshot_dir / "source_coverage.csv", index=False)
    metadata = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "macro_series_sha256": _sha256(path),
        "release_lag_policy": {
            "OVXCLS": "observation_date_plus_1_day",
            "DTWEXBGS": "observation_date_plus_7_days",
            "EIA_CRUDE_INVENTORY_EX_SPR": "week_end_plus_5_days",
            "EIA_US_CRUDE_OIL_RIGS": "next_month_end",
            "EIA_WTI_FUTURES_1_2": "observation_date_plus_7_days",
            "EIA_WTI_HENRY_SPOT": "observation_date_plus_7_days",
        },
    }
    (snapshot_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return combined


def load_macro_snapshot(snapshot_dir: Path) -> pd.DataFrame:
    path = snapshot_dir / "macro_series.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Macro snapshot missing at {path}; run with --refresh-macro-data"
        )
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["availability_date"] = pd.to_datetime(
        frame["availability_date"], errors="coerce"
    )
    return frame


def _available(macro: pd.DataFrame, series: str, cutoff: pd.Timestamp) -> pd.DataFrame:
    return macro.loc[
        macro["series"].eq(series)
        & macro["availability_date"].le(cutoff)
        & macro["date"].le(cutoff)
    ].sort_values("date")


def _regime_z(
    macro: pd.DataFrame,
    series: str,
    cutoff: pd.Timestamp,
    history: int,
    minimum: int,
    recent: int,
    max_staleness_days: int,
) -> tuple[float, pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT]:
    available = _available(macro, series, cutoff).tail(history)
    if len(available) < minimum:
        return np.nan, pd.NaT, pd.NaT
    observation = pd.Timestamp(available["date"].iloc[-1])
    if (cutoff - observation).days > max_staleness_days:
        return np.nan, observation, available["availability_date"].iloc[-1]
    scale = float(available["value"].std(ddof=0))
    if not np.isfinite(scale) or scale <= 1e-12:
        return np.nan, pd.NaT, pd.NaT
    value = (
        float(available["value"].tail(recent).mean())
        - float(available["value"].mean())
    ) / scale
    return value, observation, available["availability_date"].iloc[-1]


def _curve_feature(
    macro: pd.DataFrame,
    cutoff: pd.Timestamp,
) -> tuple[float, pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT]:
    front = _available(macro, "EIA_WTI_FUTURES_1", cutoff)[
        ["date", "availability_date", "value"]
    ].rename(columns={"value": "front", "availability_date": "available_front"})
    second = _available(macro, "EIA_WTI_FUTURES_2", cutoff)[
        ["date", "availability_date", "value"]
    ].rename(columns={"value": "second", "availability_date": "available_second"})
    joined = front.merge(second, on="date", how="inner").tail(20)
    if len(joined) < 5:
        return np.nan, pd.NaT, pd.NaT
    observation = pd.Timestamp(joined["date"].iloc[-1])
    if (cutoff - observation).days > 45:
        return (
            np.nan,
            observation,
            max(
                joined["available_front"].iloc[-1],
                joined["available_second"].iloc[-1],
            ),
        )
    slope = ((joined["front"] - joined["second"]) / joined["front"] * 100.0)
    return (
        float(slope.mean()),
        observation,
        max(joined["available_front"].iloc[-1], joined["available_second"].iloc[-1]),
    )


def build_macro_feature_panel(
    quarters: list[str] | tuple[str, ...],
    macro: pd.DataFrame,
    cutoff_day: int = 61,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    specs = {
        # (series, rolling history, minimum history, recent window,
        #  maximum age of the newest observation at forecast cutoff)
        "ovx_regime_z": ("OVXCLS", 756, 252, 20, 45),
        "dxy_regime_z": ("DTWEXBGS", 756, 252, 20, 45),
        "crude_inventory_z": ("EIA_CRUDE_INVENTORY_EX_SPR", 260, 104, 1, 21),
        "oil_rig_z": ("EIA_US_CRUDE_OIL_RIGS", 60, 24, 1, 75),
        "wti_regime_z": ("EIA_WTI_SPOT", 756, 252, 20, 45),
        "henry_regime_z": ("EIA_HENRY_SPOT", 756, 252, 20, 45),
    }
    for quarter in sorted(set(map(str, quarters)), key=lambda value: pd.Period(value, freq="Q")):
        cutoff = quarter_cutoff_date(quarter, cutoff_day)
        row: dict[str, object] = {"quarter": quarter, "forecast_cutoff_date": cutoff}
        for feature, (series, history, minimum, recent, max_age) in specs.items():
            value, observation, available = _regime_z(
                macro, series, cutoff, history, minimum, recent, max_age
            )
            row[feature] = value
            row[f"{feature}_observation_date"] = observation
            row[f"{feature}_availability_date"] = available
        curve, observation, available = _curve_feature(macro, cutoff)
        row["wti_curve_slope_pct"] = curve
        row["wti_curve_slope_pct_observation_date"] = observation
        row["wti_curve_slope_pct_availability_date"] = available
        row["oil_gas_regime_spread"] = (
            row["wti_regime_z"] - row["henry_regime_z"]
            if np.isfinite(row["wti_regime_z"]) and np.isfinite(row["henry_regime_z"])
            else np.nan
        )
        observation_dates = pd.to_datetime([
            row["wti_regime_z_observation_date"],
            row["henry_regime_z_observation_date"],
        ], errors="coerce")
        availability_dates = pd.to_datetime([
            row["wti_regime_z_availability_date"],
            row["henry_regime_z_availability_date"],
        ], errors="coerce")
        row["oil_gas_regime_spread_observation_date"] = (
            observation_dates.max() if observation_dates.notna().any() else pd.NaT
        )
        row["oil_gas_regime_spread_availability_date"] = (
            availability_dates.max() if availability_dates.notna().any() else pd.NaT
        )
        rows.append(row)
    result = pd.DataFrame(rows)
    for feature in (*OIL_FEATURES, *MIXED_FEATURES):
        available_column = f"{feature}_availability_date"
        if available_column not in result:
            continue
        invalid = pd.to_datetime(result[available_column], errors="coerce").gt(
            pd.to_datetime(result["forecast_cutoff_date"], errors="coerce")
        )
        if invalid.any():
            raise AssertionError(f"Post-cutoff macro values found for {feature}")
    return result
