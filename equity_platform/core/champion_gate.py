from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ChampionMetrics:
    observations: int
    mae: float
    naive_mae: float
    mase: float
    eligible: bool


def assess_against_naive(
    *,
    actual: pd.Series,
    prediction: pd.Series,
    naive: pd.Series,
    minimum_observations: int = 4,
) -> ChampionMetrics:
    """Evaluate one target without granting authority to any other target."""
    frame = pd.DataFrame(
        {"actual": actual.astype(float), "prediction": prediction.astype(float), "naive": naive.astype(float)}
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if frame.empty:
        return ChampionMetrics(0, np.nan, np.nan, np.nan, False)
    mae = float((frame["actual"] - frame["prediction"]).abs().mean())
    naive_mae = float((frame["actual"] - frame["naive"]).abs().mean())
    mase = mae / naive_mae if naive_mae else np.nan
    eligible = bool(len(frame) >= minimum_observations and np.isfinite(mase) and mase < 1.0)
    return ChampionMetrics(len(frame), mae, naive_mae, mase, eligible)
