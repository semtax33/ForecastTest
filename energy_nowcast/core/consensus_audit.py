from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.cutoff import quarter_cutoff_date


def latest_consensus_snapshot(consensus: pd.DataFrame) -> pd.DataFrame:
    """Aggregate latest snapshots for a diagnostic that is explicitly not PIT."""
    if consensus.empty:
        return consensus.copy()
    latest_provider = (
        consensus.dropna(subset=["snapshot_date", "consensus_revenue"])
        .sort_values("snapshot_date")
        .groupby(["provider", "ticker", "quarter"], as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
    if latest_provider.empty:
        return latest_provider
    return (
        latest_provider.groupby(["ticker", "quarter"], as_index=False)
        .agg(
            snapshot_date=("snapshot_date", "max"),
            consensus_revenue=("consensus_revenue", "median"),
            consensus_revenue_low=("consensus_revenue_low", "min"),
            consensus_revenue_high=("consensus_revenue_high", "max"),
            analyst_count=("analyst_count", "sum"),
            provider_count=("provider", "nunique"),
            providers=("provider", lambda values: ",".join(sorted(set(values)))),
        )
        .sort_values(["quarter", "ticker"])
        .reset_index(drop=True)
    )


def consensus_cutoff_audit(
    consensus: pd.DataFrame,
    targets: pd.DataFrame,
    day_of_quarter: int,
) -> pd.DataFrame:
    """Audit every available consensus snapshot against target-quarter cutoffs."""
    required = {"ticker", "quarter"}
    missing = required.difference(targets.columns)
    if missing:
        raise ValueError(f"consensus targets are missing columns: {sorted(missing)}")
    target_keys = targets[["ticker", "quarter"]].drop_duplicates().copy()
    target_keys["ticker"] = target_keys["ticker"].astype(str).str.upper()
    target_keys["quarter"] = target_keys["quarter"].astype(str)
    target_keys["forecast_cutoff_date"] = target_keys["quarter"].map(
        lambda quarter: quarter_cutoff_date(quarter, day_of_quarter)
    )
    if consensus.empty:
        result = target_keys.copy()
        result["provider"] = pd.NA
        result["snapshot_date"] = pd.NaT
        result["consensus_revenue"] = np.nan
    else:
        source = consensus.copy()
        source["ticker"] = source["ticker"].astype(str).str.upper()
        source["quarter"] = source["quarter"].astype(str)
        result = target_keys.merge(source, on=["ticker", "quarter"], how="left")
    result["snapshot_date"] = pd.to_datetime(
        result["snapshot_date"], errors="coerce"
    )
    result["point_in_time_eligible"] = (
        result["snapshot_date"].notna()
        & result["snapshot_date"].le(result["forecast_cutoff_date"])
    )
    result["status"] = np.select(
        [result["snapshot_date"].isna(), result["point_in_time_eligible"]],
        ["NO_REVENUE_CONSENSUS_SNAPSHOT", "POINT_IN_TIME_ELIGIBLE"],
        default="POST_CUTOFF_DIAGNOSTIC_ONLY",
    )
    return result.sort_values(
        ["quarter", "ticker", "provider", "snapshot_date"], na_position="last"
    ).reset_index(drop=True)
