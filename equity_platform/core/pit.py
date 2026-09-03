from __future__ import annotations

import pandas as pd


def build_quarterly_forecast_origins(
    releases: pd.DataFrame,
    *,
    period_column: str = "period",
    available_at_column: str = "filing_date",
) -> pd.DataFrame:
    """Build one-quarter-ahead origins using only the previous public release."""
    frame = (
        releases[[period_column, available_at_column]]
        .drop_duplicates()
        .assign(
            quarter=lambda values: pd.PeriodIndex(values[period_column], freq="Q"),
            available_at=lambda values: pd.to_datetime(values[available_at_column]),
        )
        .sort_values("quarter")
        .reset_index(drop=True)
    )
    rows: list[dict[str, object]] = []
    for index in range(1, len(frame)):
        origin = frame.iloc[index - 1]
        target = frame.iloc[index]
        if target["quarter"].ordinal - origin["quarter"].ordinal != 1:
            continue
        rows.append(
            {
                "period": str(target["quarter"]),
                "forecast_as_of": origin["available_at"].date().isoformat(),
                "actual_available_at": target["available_at"].date().isoformat(),
                "origin_period": str(origin["quarter"]),
                "horizon_quarters": 1,
                "actual_after_forecast": bool(target["available_at"] > origin["available_at"]),
            }
        )
    return pd.DataFrame(rows)
