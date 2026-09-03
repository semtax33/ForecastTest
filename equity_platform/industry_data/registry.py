from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {
    "sector",
    "subindustry",
    "sensor_id",
    "source",
    "dataset",
    "raw_series",
    "pqci_dimension",
    "economic_role",
    "lead_months",
    "grade",
    "direction",
    "weight",
    "target",
    "transformation",
    "availability_status",
}
VALID_DIMENSIONS = {"P", "Q", "C", "I"}
VALID_ROLES = {"LEADING", "COINCIDENT", "LAGGING"}
VALID_GRADES = {"A", "B", "C", "D", "E"}
VALID_AVAILABILITY = {
    "AVAILABLE_ARCANA",
    "SOURCE_AVAILABLE_NOT_INGESTED",
    "ALTERNATIVE_DATA_DEFERRED",
}
VALID_TRANSFORMATIONS = {
    "event_count",
    "half_year_yoy",
    "latest_yoy",
    "level_change",
    "quarter_average_yoy",
    "quarter_yoy",
    "same_period_yoy",
    "three_month_momentum",
    "ytd_yoy",
}


def load_industry_sensor_registry(path: Path) -> pd.DataFrame:
    registry = pd.read_csv(path)
    missing = REQUIRED_COLUMNS.difference(registry.columns)
    if missing:
        raise ValueError(f"Industry sensor registry columns missing: {sorted(missing)}")
    if registry[["sector", "subindustry", "sensor_id"]].duplicated().any():
        raise ValueError("Industry sensor registry contains duplicate sensor keys")
    if not registry["pqci_dimension"].isin(VALID_DIMENSIONS).all():
        raise ValueError("Industry sensor registry contains an invalid P/Q/C/I dimension")
    if not registry["economic_role"].isin(VALID_ROLES).all():
        raise ValueError("Industry sensor registry contains an invalid economic role")
    if not registry["grade"].isin(VALID_GRADES).all():
        raise ValueError("Industry sensor registry contains an invalid source grade")
    if not registry["availability_status"].isin(VALID_AVAILABILITY).all():
        raise ValueError("Industry sensor registry contains an invalid availability status")
    if not registry["transformation"].isin(VALID_TRANSFORMATIONS).all():
        invalid = sorted(set(registry["transformation"]).difference(VALID_TRANSFORMATIONS))
        raise ValueError(f"Industry sensor registry contains invalid transformations: {invalid}")
    registry["lead_months"] = pd.to_numeric(registry["lead_months"], errors="raise")
    registry["weight"] = pd.to_numeric(registry["weight"], errors="raise")
    registry["direction"] = pd.to_numeric(registry["direction"], errors="raise")
    if not registry["direction"].isin([-1, 1]).all():
        raise ValueError("Industry sensor direction must be -1 or +1")
    if registry["weight"].le(0).any():
        raise ValueError("Industry sensor weights must be positive")
    if registry.loc[registry["economic_role"].eq("LEADING"), "lead_months"].le(0).any():
        raise ValueError("Leading industry sensors require a positive lead")
    registry["forecast_use"] = registry["economic_role"].map(
        {
            "LEADING": "FORECAST",
            "COINCIDENT": "NOWCAST",
            "LAGGING": "CALIBRATION_ONLY",
        }
    )
    registry["grade_weight"] = registry["grade"].map(
        {"A": 1.0, "B": 0.8, "C": 0.5, "D": 0.25, "E": 0.0}
    )
    registry["model_weight"] = registry["weight"] * registry["grade_weight"]
    return registry


def build_registry_coverage(registry: pd.DataFrame) -> pd.DataFrame:
    coverage = (
        registry.assign(
            ingested=registry["availability_status"].eq("AVAILABLE_ARCANA"),
            leading=registry["economic_role"].eq("LEADING"),
        )
        .groupby(["sector", "subindustry"], as_index=False)
        .agg(
            sensor_count=("sensor_id", "size"),
            ingested_sensor_count=("ingested", "sum"),
            leading_sensor_count=("leading", "sum"),
            pqci_dimensions=("pqci_dimension", lambda values: "|".join(sorted(set(values)))),
            targets=("target", lambda values: "|".join(sorted(set(values)))),
        )
    )
    coverage["ingested_coverage_pct"] = (
        coverage["ingested_sensor_count"] / coverage["sensor_count"] * 100.0
    )
    coverage["forecast_ready"] = (
        coverage["ingested_sensor_count"].eq(coverage["sensor_count"])
        & coverage["leading_sensor_count"].gt(0)
    )
    return coverage
