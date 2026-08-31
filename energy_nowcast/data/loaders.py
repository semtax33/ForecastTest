from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..config import ProjectPaths


@dataclass
class LegacyArtifacts:
    validation: pd.DataFrame
    nowcast: pd.DataFrame
    metrics: pd.DataFrame
    weights: pd.DataFrame
    panel: pd.DataFrame
    component_panel: pd.DataFrame
    prices: pd.DataFrame
    v21_validation: pd.DataFrame


def _read_csv(path: Path, required: tuple[str, ...] = ()) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required artifact not found: {path}")
    frame = pd.read_csv(path)
    missing = set(required).difference(frame.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
    return frame


def load_legacy_artifacts(paths: ProjectPaths) -> LegacyArtifacts:
    lake = paths.data_lake
    assert lake is not None
    validation = _read_csv(
        lake / "energy_v3_3_validation.csv",
        ("quarter", "ticker", "actual_log_yoy", "blend_log_yoy"),
    )
    nowcast = _read_csv(
        lake / "energy_v3_3_nowcast.csv",
        ("ticker", "nowcast_quarter", "predicted_revenue_B"),
    )
    metrics = _read_csv(lake / "energy_v3_3_metrics.csv")
    weights = _read_csv(
        lake / "energy_v3_3_blend_weights.csv",
        ("ticker", "base_structural_weight", "guardrail"),
    )
    panel = _read_csv(
        lake / "energy_v3_3_structural_panel.csv",
        ("ticker", "quarter", "revenue"),
    )
    component_panel = _read_csv(
        lake / "energy_v3_3_eog_component_panel.csv",
        ("quarter", "current_total_driver", "component_structural_log_yoy"),
    )
    prices = _read_csv(
        lake / "energy_v3_3_price_quarters.csv",
        ("quarter", "wti_price", "henry_price", "propane_price_bbl"),
    )
    v21_validation = _read_csv(
        lake / "energy_v2_1_validation.csv",
        ("quarter", "ticker", "actual", "predicted", "naive"),
    )
    return LegacyArtifacts(
        validation=validation,
        nowcast=nowcast,
        metrics=metrics,
        weights=weights,
        panel=panel,
        component_panel=component_panel,
        prices=prices,
        v21_validation=v21_validation,
    )
