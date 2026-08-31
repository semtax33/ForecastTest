from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ProjectPaths:
    root: Path = PROJECT_ROOT
    data_lake: Path | None = None
    output: Path | None = None

    def __post_init__(self) -> None:
        root = self.root.resolve()
        object.__setattr__(self, "root", root)
        object.__setattr__(
            self,
            "data_lake",
            (self.data_lake or root / "data-lake").resolve(),
        )
        object.__setattr__(
            self,
            "output",
            (self.output or root / "output").resolve(),
        )


@dataclass(frozen=True)
class ModelConfig:
    version: str
    source_version: str = "3.3"
    as_of_date: date = date(2026, 8, 31)
    tickers: tuple[str, ...] = ("COP", "EOG", "FANG", "DVN")
    component_tickers: tuple[str, ...] = ("EOG",)
    price_window: str = "same_day_of_quarter"
    blend_method: str = "shrunk_walk_forward"
    prediction_interval: bool = True
    interval_levels: tuple[float, ...] = (0.80, 0.95)
    ticker_residual_weight: float = 0.50
    shrinkage_prior_weight: float = 0.75
    shrinkage_k: float = 6.0
    min_blend_history: int = 3
    untouched_test_quarters: int = 2
    release_cutoff_day_of_quarter: int = 61
    realized_basis: bool = False
    basis_method: str = "expanding_median"
    basis_min_history: int = 4
    basis_adjustment_clip: float = 25.0
    promotion_tolerance_log_points: float = 0.0
    validation_regression_tolerance_pct: float = 2.0
    arcana_consensus_dir: str = "../Arcana/data-lake/bronze/consensus"
    consensus_file: str = "analyst_consensus.csv"
    minimum_consensus_observations: int = 20
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.ticker_residual_weight <= 1.0:
            raise ValueError("ticker_residual_weight must be between 0 and 1")
        if not 0.0 <= self.shrinkage_prior_weight <= 1.0:
            raise ValueError("shrinkage_prior_weight must be between 0 and 1")
        if self.shrinkage_k < 0:
            raise ValueError("shrinkage_k must be non-negative")
        if self.untouched_test_quarters < 0:
            raise ValueError("untouched_test_quarters must be non-negative")
        if not self.interval_levels:
            raise ValueError("interval_levels cannot be empty")
        if any(level <= 0 or level >= 1 for level in self.interval_levels):
            raise ValueError("interval levels must be between 0 and 1")


def load_config(path: str | Path) -> ModelConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    raw["as_of_date"] = date.fromisoformat(raw["as_of_date"])
    for key in ("tickers", "component_tickers", "interval_levels"):
        if key in raw:
            raw[key] = tuple(raw[key])
    return ModelConfig(**raw)
