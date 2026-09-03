from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from equity_platform.artifacts import content_hash, hash_files, sha256_file
from equity_platform.domain import ForecastSnapshot


ENERGY_V1_1_INPUTS = (
    "output/energy_valuation_v1_1/scenario_assumptions.csv",
    "output/energy_valuation_v1_1/dcf_projections.csv",
    "output/energy_valuation_v1_1/forward_dcf_probability_weighted.csv",
    "output/energy_valuation_v1_1/reverse_dcf_expectations.csv",
)


def target_quarter(base_quarter: str, quarters_forward: int = 4) -> str:
    return str(pd.Period(base_quarter, freq="Q") + quarters_forward)


def latest_consensus_by_target(
    consensus: pd.DataFrame,
    as_of_date: date,
) -> pd.DataFrame:
    if consensus.empty:
        return pd.DataFrame(
            columns=["ticker", "quarter", "consensus_value_usd", "consensus_as_of"]
        )
    eligible = consensus.copy()
    eligible["snapshot_date"] = pd.to_datetime(
        eligible["snapshot_date"], errors="coerce"
    )
    eligible = eligible.loc[
        eligible["snapshot_date"].notna()
        & eligible["snapshot_date"].le(pd.Timestamp(as_of_date))
        & pd.to_numeric(eligible["consensus_revenue"], errors="coerce").notna()
    ].copy()
    if eligible.empty:
        return pd.DataFrame(
            columns=["ticker", "quarter", "consensus_value_usd", "consensus_as_of"]
        )
    eligible = (
        eligible.sort_values("snapshot_date")
        .groupby(["ticker", "quarter", "provider"], as_index=False, group_keys=False)
        .tail(1)
    )
    return (
        eligible.groupby(["ticker", "quarter"], as_index=False)
        .agg(
            consensus_value_usd=("consensus_revenue", "median"),
            consensus_as_of=("snapshot_date", "max"),
        )
    )


def build_energy_v11_live_snapshots(
    *,
    root: Path,
    as_of_date: date,
    v11_manifest_sha256: str,
    v19_manifest_sha256: str,
    consensus: pd.DataFrame,
) -> list[ForecastSnapshot]:
    source_hashes = hash_files(root, ENERGY_V1_1_INPUTS)
    input_hash = content_hash(
        {
            "artifacts": source_hashes,
            "v1_1_manifest": v11_manifest_sha256,
            "v1_9_manifest": v19_manifest_sha256,
            "forecast_as_of": as_of_date.isoformat(),
        }
    )
    output = root / "output/energy_valuation_v1_1"
    assumptions = pd.read_csv(output / "scenario_assumptions.csv")
    base = assumptions.loc[assumptions["scenario"].eq("BASE")].copy()
    base["target_period"] = base["base_financial_quarter"].map(target_quarter)
    projections = pd.read_csv(output / "dcf_projections.csv")
    year_one = projections.loc[
        projections["scenario"].eq("BASE")
        & projections["forecast_year"].eq(1)
    ][
        [
            "ticker",
            "revenue_usd",
            "ebit_usd",
            "operating_margin_pct",
            "fcff_usd",
            "forecast_normalized_roic_pct",
        ]
    ]
    weighted = pd.read_csv(output / "forward_dcf_probability_weighted.csv")
    reverse = pd.read_csv(output / "reverse_dcf_expectations.csv")
    consensus_latest = latest_consensus_by_target(consensus, as_of_date).rename(
        columns={"quarter": "target_period"}
    )
    joined = (
        base[["ticker", "subindustry", "target_period"]]
        .merge(year_one, on="ticker", validate="one_to_one")
        .merge(
            weighted[
                [
                    "ticker",
                    "probability_weighted_fair_value",
                    "probability_weighted_value_gap_pct",
                ]
            ],
            on="ticker",
            validate="one_to_one",
        )
        .merge(
            reverse[
                [
                    "ticker",
                    "market_implied_operating_margin_pct",
                    "operating_margin_solver_status",
                ]
            ],
            on="ticker",
            validate="one_to_one",
        )
        .merge(
            consensus_latest,
            on=["ticker", "target_period"],
            how="left",
            validate="one_to_one",
        )
    )
    snapshots: list[ForecastSnapshot] = []
    for row in joined.to_dict("records"):
        reverse_value = pd.to_numeric(
            row["market_implied_operating_margin_pct"], errors="coerce"
        )
        snapshots.append(
            ForecastSnapshot(
                forecast_as_of=as_of_date.isoformat(),
                model_version="ENERGY_VALUATION_V1_1",
                sector="Energy",
                subindustry=str(row["subindustry"]),
                ticker=str(row["ticker"]),
                target_period=str(row["target_period"]),
                input_hash=input_hash,
                revenue_forecast_usd=_number(row["revenue_usd"]),
                ebit_forecast_usd=_number(row["ebit_usd"]),
                margin_forecast_pct=_number(row["operating_margin_pct"]),
                fcff_forecast_usd=_number(row["fcff_usd"]),
                roic_forecast_pct=_number(row["forecast_normalized_roic_pct"]),
                forward_dcf_value_per_share=_number(
                    row["probability_weighted_fair_value"]
                ),
                reverse_dcf_metric=(
                    "MARKET_IMPLIED_OPERATING_MARGIN_PCT"
                    if row["operating_margin_solver_status"] == "SOLVED"
                    else str(row["operating_margin_solver_status"])
                ),
                reverse_dcf_value=(
                    float(reverse_value) if np.isfinite(reverse_value) else None
                ),
                expectations_gap_pct=_number(
                    row["probability_weighted_value_gap_pct"]
                ),
                consensus_value_usd=_number(row.get("consensus_value_usd")),
                consensus_as_of=(
                    pd.Timestamp(row["consensus_as_of"]).date().isoformat()
                    if pd.notna(row.get("consensus_as_of"))
                    else None
                ),
                source_manifest_sha256=v11_manifest_sha256,
            )
        )
    return snapshots


def consensus_store_rows(consensus: pd.DataFrame, as_of_date: date) -> Iterable[dict[str, object]]:
    if consensus.empty:
        return []
    rows: list[dict[str, object]] = []
    for source in consensus.to_dict("records"):
        snapshot = pd.to_datetime(source.get("snapshot_date"), errors="coerce")
        value = pd.to_numeric(source.get("consensus_revenue"), errors="coerce")
        source_path = Path(str(source.get("source_path", "")))
        if pd.isna(snapshot) or snapshot.date() > as_of_date or not np.isfinite(value):
            continue
        rows.append(
            {
                "as_of_date": snapshot.date().isoformat(),
                "ticker": str(source["ticker"]),
                "target_period": str(source["quarter"]),
                "provider": str(source["provider"]),
                "metric": "REVENUE_USD",
                "value": float(value),
                "source_path": str(source_path),
                "source_hash": (
                    sha256_file(source_path) if source_path.is_file() else content_hash(source)
                ),
            }
        )
    return rows


def _number(value: object) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return float(number) if np.isfinite(number) else None
