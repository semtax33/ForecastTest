from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.data_catalog import DataCatalog

from ..config import ModelConfig, ProjectPaths
from ..data.cutoff import quarter_cutoff_date


def _basis_forecast(history: pd.Series, method: str) -> float:
    clean = pd.to_numeric(history, errors="coerce").dropna()
    if clean.empty:
        return float("nan")
    if method == "expanding_mean":
        return float(clean.mean())
    if method == "ewm":
        return float(clean.ewm(span=4, adjust=False).mean().iloc[-1])
    if method != "expanding_median":
        raise ValueError(f"unsupported basis method: {method}")
    return float(clean.median())


def add_realized_basis_candidates(
    component_panel: pd.DataFrame,
    revenue_panel: pd.DataFrame,
    config: ModelConfig,
    paths: ProjectPaths,
) -> pd.DataFrame:
    """Build a point-in-time EOG realized-price/basis adjustment.

    Revenue-to-economic-driver basis is estimated only from actual quarters
    whose release date was available by each target quarter's cutoff.
    """
    component = component_panel.copy()
    component["ticker"] = "EOG"
    component["quarter"] = component["quarter"].astype(str)

    revenue = revenue_panel.loc[
        revenue_panel["ticker"].eq("EOG"), ["quarter", "revenue"]
    ].copy()
    revenue["quarter"] = revenue["quarter"].astype(str)
    revenue["revenue"] = pd.to_numeric(revenue["revenue"], errors="coerce")

    assert paths.data_lake is not None
    releases_path = (
        DataCatalog(paths.data_lake).model("v3_2_7")
        / "energy_v3_2_7_actual_EOG.csv"
    )
    releases = pd.read_csv(releases_path)[["quarter", "release_date"]]
    releases["quarter"] = releases["quarter"].astype(str)
    releases["release_date"] = pd.to_datetime(releases["release_date"], errors="coerce")

    result = component.merge(revenue, on="quarter", how="left").merge(
        releases, on="quarter", how="left"
    )
    result["realized_basis"] = result["revenue"] / pd.to_numeric(
        result["current_total_driver"], errors="coerce"
    ).where(lambda values: values > 0)
    basis_by_quarter = result.set_index("quarter")["realized_basis"]

    predicted_basis: list[float] = []
    prior_basis: list[float] = []
    history_counts: list[int] = []
    for _, row in result.iterrows():
        quarter = pd.Period(row["quarter"], freq="Q")
        cutoff = quarter_cutoff_date(
            quarter, config.release_cutoff_day_of_quarter
        )
        history = result.loc[
            result["release_date"].notna()
            & result["release_date"].le(cutoff)
            & result["realized_basis"].notna()
            & (pd.PeriodIndex(result["quarter"], freq="Q") < quarter),
            "realized_basis",
        ]
        history_counts.append(int(len(history)))
        predicted_basis.append(
            _basis_forecast(history, config.basis_method)
            if len(history) >= config.basis_min_history
            else float("nan")
        )
        prior_basis.append(basis_by_quarter.get(str(quarter - 4), float("nan")))

    result["predicted_realized_basis"] = predicted_basis
    result["prior_year_realized_basis"] = prior_basis
    result["basis_history_observations"] = history_counts
    result["basis_adjustment_log_points"] = 100.0 * np.log(
        result["predicted_realized_basis"] / result["prior_year_realized_basis"]
    )
    result["basis_adjustment_log_points"] = result[
        "basis_adjustment_log_points"
    ].clip(-config.basis_adjustment_clip, config.basis_adjustment_clip)
    result["v34_structural_log_yoy"] = (
        result["component_structural_log_yoy"]
        + result["basis_adjustment_log_points"]
    )
    result["basis_model_available"] = result["v34_structural_log_yoy"].notna()
    return result[
        [
            "ticker",
            "quarter",
            "realized_basis",
            "predicted_realized_basis",
            "prior_year_realized_basis",
            "basis_history_observations",
            "basis_adjustment_log_points",
            "component_structural_log_yoy",
            "v34_structural_log_yoy",
            "basis_model_available",
        ]
    ].copy()
