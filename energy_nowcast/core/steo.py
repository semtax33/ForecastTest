from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from ..data.cutoff import quarter_cutoff_date


ARCHIVE_URL = "https://www.eia.gov/outlooks/steo/archives/{issue}_base.xlsx"
ISSUE_MONTHS = {1: "feb", 2: "may", 3: "aug", 4: "nov"}
MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

SERIES_SHEETS = {
    "WTIPUUS": "2tab",
    "BREPUUS": "2tab",
    "RACPUUS": "2tab",
    "MGWHUUS_$": "2tab",
    "MGWHUUS": "2tab",
    "DSWHUUS_$": "2tab",
    "DSWHUUS": "2tab",
    "JKTCUUS_$": "2tab",
    "JKTCUUS": "2tab",
    "PRMBUUS_$": "2tab",
    "NGHHMCF": "2tab",
    "COPRPUS": "1tab",
    "NGPRPUS": "1tab",
    "PATCPUSX": "1tab",
    "NGTCPUS": "1tab",
    "papr_world": "3ctab",
    "CORIPUS": "4atab",
}

OUTPUT_NAMES = {
    "WTIPUUS": "wti",
    "BREPUUS": "brent",
    "RACPUUS": "refiner_crude_cost",
    "MGWHUUS_$": "gasoline_wholesale",
    "MGWHUUS": "gasoline_wholesale",
    "DSWHUUS_$": "diesel_wholesale",
    "DSWHUUS": "diesel_wholesale",
    "JKTCUUS_$": "jet_wholesale",
    "JKTCUUS": "jet_wholesale",
    "PRMBUUS_$": "propane",
    "NGHHMCF": "henry",
    "COPRPUS": "us_crude_production",
    "NGPRPUS": "us_dry_gas_production",
    "PATCPUSX": "us_liquid_fuels_consumption",
    "NGTCPUS": "us_gas_consumption",
    "papr_world": "world_liquids_production",
    "CORIPUS": "refinery_crude_input",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _issue_for_quarter(quarter: str) -> str:
    period = pd.Period(quarter, freq="Q")
    return f"{ISSUE_MONTHS[period.quarter]}{str(period.year)[-2:]}"


def required_issues(start_year: int, end_year: int) -> tuple[str, ...]:
    current = pd.Timestamp.today()
    issue_month_numbers = {1: 2, 2: 5, 3: 8, 4: 11}
    return tuple(
        _issue_for_quarter(f"{year}Q{quarter}")
        for year in range(start_year, end_year + 1)
        for quarter in range(1, 5)
        if not (
            year == current.year
            and issue_month_numbers[quarter] > current.month
        )
    )


def _parse_dates(
    issue: str,
    workbook: bytes,
) -> tuple[pd.Timestamp, pd.Timestamp, int]:
    frame = pd.read_excel(BytesIO(workbook), sheet_name="Dates", header=None)
    completed = pd.to_datetime(frame.iloc[1, 3], errors="coerce")
    if pd.isna(completed):
        month = next(number for number, label in ISSUE_MONTHS.items() if label == issue[:3])
        calendar_month = {1: 2, 2: 5, 3: 8, 4: 11}[month]
        year = 2000 + int(issue[-2:])
        # Older workbooks omit the completion timestamp. The 15th of the issue
        # month is a conservative archive-availability proxy and is still
        # before the corresponding day-61 quarterly cutoff.
        completed = pd.Timestamp(year, calendar_month, 8)
        available_at = pd.Timestamp(year, calendar_month, 15)
    else:
        available_at = completed + pd.Timedelta(days=7)
    last_historical = int(pd.to_numeric(frame.iloc[6, 3], errors="raise"))
    # Publication is normally a few days after modeling completion. Seven days
    # is a conservative availability rule that remains before each day-61 cutoff.
    return completed, available_at, last_historical


def _month_columns(frame: pd.DataFrame) -> list[tuple[int, pd.Timestamp]]:
    years = pd.to_numeric(frame.iloc[2], errors="coerce").ffill()
    columns: list[tuple[int, pd.Timestamp]] = []
    for column in range(2, frame.shape[1]):
        month = str(frame.iloc[3, column]).strip()
        year = years.iloc[column]
        if month not in MONTHS or not np.isfinite(year):
            continue
        columns.append((column, pd.Timestamp(int(year), MONTHS[month], 1)))
    return columns


def _parse_issue(issue: str, workbook: bytes) -> tuple[pd.DataFrame, dict[str, object]]:
    completed, available_at, last_historical = _parse_dates(issue, workbook)
    sheet_cache: dict[str, pd.DataFrame] = {}
    pieces: list[pd.DataFrame] = []
    for series, sheet in SERIES_SHEETS.items():
        if sheet not in sheet_cache:
            try:
                sheet_cache[sheet] = pd.read_excel(
                    BytesIO(workbook), sheet_name=sheet, header=None
                )
            except ValueError:
                continue
        frame = sheet_cache[sheet]
        matches = frame.index[frame.iloc[:, 0].astype(str).str.strip().eq(series)]
        if len(matches) == 0:
            continue
        row = frame.loc[matches[0]]
        records = []
        for column, target_month in _month_columns(frame):
            value = pd.to_numeric(row.iloc[column], errors="coerce")
            if np.isfinite(value):
                records.append({
                    "target_month": target_month,
                    "series": OUTPUT_NAMES[series],
                    "value": float(value),
                })
        pieces.append(pd.DataFrame(records))
    if not pieces:
        raise ValueError(f"No required STEO series parsed from {issue}")
    long = pd.concat(pieces, ignore_index=True)
    if not long["series"].eq("world_liquids_production").any():
        try:
            frame = pd.read_excel(BytesIO(workbook), sheet_name="3atab", header=None)
            matches = frame.index[
                frame.iloc[:, 0].astype(str).str.strip().eq("papr_world")
            ]
            if len(matches):
                records = []
                row = frame.loc[matches[0]]
                for column, target_month in _month_columns(frame):
                    value = pd.to_numeric(row.iloc[column], errors="coerce")
                    if np.isfinite(value):
                        records.append({
                            "target_month": target_month,
                            "series": "world_liquids_production",
                            "value": float(value),
                        })
                long = pd.concat([long, pd.DataFrame(records)], ignore_index=True)
        except ValueError:
            pass
    wide = long.pivot_table(
        index="target_month", columns="series", values="value", aggfunc="last"
    ).reset_index()
    wide.columns.name = None
    for price_column in (
        "gasoline_wholesale", "diesel_wholesale", "jet_wholesale", "propane"
    ):
        if price_column in wide and float(wide[price_column].median()) > 20.0:
            # Older STEO workbooks express wholesale product prices in cents
            # per gallon; newer workbooks use dollars per gallon.
            wide[price_column] = wide[price_column] / 100.0
    wide["issue"] = issue
    wide["vintage_completed"] = completed
    wide["available_at"] = available_at
    wide["last_historical_month"] = pd.to_datetime(
        str(last_historical), format="%Y%m"
    )
    wide["is_forecast"] = wide["target_month"].gt(
        wide["last_historical_month"]
    )
    wide["source_url"] = ARCHIVE_URL.format(issue=issue)
    metadata = {
        "issue": issue,
        "vintage_completed": completed.isoformat(),
        "available_at": available_at.isoformat(),
        "last_historical_month": str(last_historical),
        "source_url": ARCHIVE_URL.format(issue=issue),
        "source_sha256": _sha256_bytes(workbook),
        "rows": len(wide),
    }
    return wide, metadata


def refresh_steo_vintages(
    snapshot_dir: Path,
    start_year: int = 2019,
    end_year: int = 2026,
) -> pd.DataFrame:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    sources: list[dict[str, object]] = []
    for issue in required_issues(start_year, end_year):
        url = ARCHIVE_URL.format(issue=issue)
        response = requests.get(url, timeout=90)
        response.raise_for_status()
        frame, metadata = _parse_issue(issue, response.content)
        frames.append(frame)
        sources.append(metadata)
    result = pd.concat(frames, ignore_index=True).sort_values(
        ["available_at", "target_month"]
    ).reset_index(drop=True)
    monthly_path = snapshot_dir / "steo_monthly_vintages.csv"
    result.to_csv(monthly_path, index=False)
    pd.DataFrame(sources).to_csv(snapshot_dir / "source_manifest.csv", index=False)
    metadata = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_year": start_year,
        "end_year": end_year,
        "issues": len(sources),
        "steo_monthly_vintages_sha256": _sha256_file(monthly_path),
        "availability_policy": "modeling_completion_plus_7_days",
        "paid_market_data_used": False,
        "forbidden_sources": ["CME", "CMA", "CME DataMine"],
    }
    (snapshot_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return result


def load_steo_vintages(snapshot_dir: Path) -> pd.DataFrame:
    path = snapshot_dir / "steo_monthly_vintages.csv"
    if not path.exists():
        raise FileNotFoundError(f"STEO snapshot missing: {path}")
    frame = pd.read_csv(path)
    for column in (
        "target_month", "vintage_completed", "available_at", "last_historical_month"
    ):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def quarterly_vintage_features(monthly: pd.DataFrame) -> pd.DataFrame:
    values = monthly.copy()
    values["target_quarter"] = values["target_month"].dt.to_period("Q").astype(str)
    numeric = list(dict.fromkeys(OUTPUT_NAMES.values()))
    quarterly = values.groupby(
        ["issue", "vintage_completed", "available_at", "target_quarter"],
        as_index=False,
    )[numeric].mean()
    quarterly["product_price_basket"] = (
        0.50 * quarterly["gasoline_wholesale"]
        + 0.34 * quarterly["diesel_wholesale"]
        + 0.16 * quarterly["jet_wholesale"]
    )
    quarterly["crack_321_per_bbl"] = (
        2.0 * quarterly["gasoline_wholesale"] * 42.0
        + quarterly["diesel_wholesale"] * 42.0
        - 3.0 * quarterly["wti"]
    ) / 3.0
    quarterly["source_url"] = quarterly["issue"].map(
        lambda issue: ARCHIVE_URL.format(issue=issue)
    )
    level_columns = [
        *numeric, "product_price_basket", "crack_321_per_bbl"
    ]
    lookup = quarterly.set_index(["issue", "target_quarter"])
    for column in level_columns:
        prior_values: list[float] = []
        for _, row in quarterly.iterrows():
            prior = str(pd.Period(str(row["target_quarter"]), freq="Q") - 4)
            try:
                value = lookup.loc[(row["issue"], prior), column]
                if isinstance(value, pd.Series):
                    value = value.iloc[-1]
            except KeyError:
                value = np.nan
            prior_values.append(float(value) if np.isfinite(value) else np.nan)
        prior_series = pd.Series(prior_values, index=quarterly.index)
        ratio = (quarterly[column] / prior_series).where(
            quarterly[column].gt(0) & prior_series.gt(0)
        )
        quarterly[f"{column}_log_yoy"] = 100.0 * np.log(ratio)
    return quarterly.replace([np.inf, -np.inf], np.nan)


def select_point_in_time_features(
    quarterly: pd.DataFrame,
    target_quarters: list[str] | tuple[str, ...],
    cutoff_day: int = 61,
) -> pd.DataFrame:
    rows: list[pd.Series] = []
    for quarter in sorted(set(map(str, target_quarters)), key=lambda q: pd.Period(q, "Q")):
        cutoff = quarter_cutoff_date(quarter, cutoff_day)
        eligible = quarterly.loc[
            quarterly["target_quarter"].eq(quarter)
            & quarterly["available_at"].le(cutoff)
        ].sort_values("available_at")
        if eligible.empty:
            continue
        row = eligible.iloc[-1].copy()
        row["forecast_cutoff_date"] = cutoff
        if pd.Timestamp(row["available_at"]) > cutoff:
            raise AssertionError(f"Post-cutoff STEO vintage selected for {quarter}")
        rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)
