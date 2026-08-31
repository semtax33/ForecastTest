from __future__ import annotations

import pandas as pd


def quarter_cutoff_date(
    quarter: str | pd.Period,
    day_of_quarter: int,
) -> pd.Timestamp:
    """Return the inclusive point-in-time cutoff for a target quarter."""
    period = pd.Period(quarter, freq="Q")
    end = period.end_time.normalize()
    candidate = period.start_time.normalize() + pd.Timedelta(days=day_of_quarter)
    return min(candidate, end)


def add_forecast_cutoff(
    frame: pd.DataFrame,
    quarter_column: str,
    day_of_quarter: int,
    output_column: str = "forecast_cutoff_date",
) -> pd.DataFrame:
    result = frame.copy()
    result[output_column] = result[quarter_column].map(
        lambda value: quarter_cutoff_date(value, day_of_quarter)
    )
    return result


def filter_available_as_of(
    frame: pd.DataFrame,
    as_of: str | pd.Timestamp,
    release_date_column: str,
) -> pd.DataFrame:
    """Keep only records that had been released by ``as_of`` (inclusive)."""
    if release_date_column not in frame.columns:
        raise KeyError(f"missing release date column: {release_date_column}")
    result = frame.copy()
    release_dates = pd.to_datetime(result[release_date_column], errors="coerce")
    cutoff = pd.Timestamp(as_of).normalize()
    result[release_date_column] = release_dates
    return result.loc[release_dates.notna() & release_dates.le(cutoff)].copy()


def latest_available_by_target(
    frame: pd.DataFrame,
    target_columns: list[str],
    cutoff_column: str,
    release_date_column: str,
) -> pd.DataFrame:
    """Select the latest released record for every target without look-ahead."""
    result = frame.copy()
    result[cutoff_column] = pd.to_datetime(result[cutoff_column], errors="coerce")
    result[release_date_column] = pd.to_datetime(
        result[release_date_column], errors="coerce"
    )
    eligible = result.loc[
        result[release_date_column].notna()
        & result[cutoff_column].notna()
        & result[release_date_column].le(result[cutoff_column])
    ].copy()
    if eligible.empty:
        return eligible
    return (
        eligible.sort_values(release_date_column)
        .groupby(target_columns, as_index=False, sort=False)
        .tail(1)
        .sort_values(target_columns)
        .reset_index(drop=True)
    )
