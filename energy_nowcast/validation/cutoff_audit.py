from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.data_catalog import DataCatalog

from ..config import ModelConfig, ProjectPaths
from ..data.cutoff import add_forecast_cutoff


def _guidance_source(paths: ProjectPaths, ticker: str) -> tuple[Path, str, str]:
    assert paths.data_lake is not None
    if ticker == "EOG":
        return (
            DataCatalog(paths.data_lake).model("v3_2_7")
            / "energy_v3_2_7_guidance_EOG.csv",
            "target_quarter",
            "release_date",
        )
    return (
        DataCatalog(paths.data_lake).model("v3_2_1")
        / f"energy_v3_2_1_guidance_selected_{ticker}.csv",
        "target_quarter",
        "filing_date",
    )


def build_release_cutoff_audit(
    validation: pd.DataFrame,
    config: ModelConfig,
    paths: ProjectPaths,
) -> pd.DataFrame:
    targets = add_forecast_cutoff(
        validation[["ticker", "quarter", "production_yoy_source"]].copy(),
        "quarter",
        config.release_cutoff_day_of_quarter,
    )
    records: list[pd.DataFrame] = []
    for ticker, group in targets.groupby("ticker", sort=True):
        source_path, target_column, date_column = _guidance_source(paths, str(ticker))
        current = group.copy()
        if not source_path.exists():
            current["source_release_date"] = pd.NaT
        else:
            guidance = pd.read_csv(source_path)
            guidance = guidance.rename(
                columns={target_column: "quarter", date_column: "source_release_date"}
            )
            guidance["quarter"] = guidance["quarter"].astype(str)
            guidance["source_release_date"] = pd.to_datetime(
                guidance["source_release_date"], errors="coerce"
            )
            guidance = (
                guidance.sort_values("source_release_date")
                .groupby("quarter", as_index=False)
                .tail(1)[["quarter", "source_release_date"]]
            )
            current["quarter"] = current["quarter"].astype(str)
            current = current.merge(guidance, on="quarter", how="left")
        current["release_date_cutoff_pass"] = (
            current["source_release_date"].notna()
            & current["source_release_date"].le(current["forecast_cutoff_date"])
        )
        no_guidance_needed = current["production_yoy_source"].isin(
            ["INDUSTRY_FALLBACK", "ACTUAL_VS_ACTUAL"]
        )
        current["cutoff_status"] = "NO_DATED_GUIDANCE"
        current.loc[no_guidance_needed, "cutoff_status"] = "NOT_APPLICABLE"
        current.loc[current["release_date_cutoff_pass"], "cutoff_status"] = "PASS"
        current.loc[
            current["source_release_date"].notna()
            & ~current["release_date_cutoff_pass"],
            "cutoff_status",
        ] = "FAIL_AFTER_CUTOFF"
        records.append(current)
    return pd.concat(records, ignore_index=True).sort_values(
        ["quarter", "ticker"]
    ).reset_index(drop=True)
