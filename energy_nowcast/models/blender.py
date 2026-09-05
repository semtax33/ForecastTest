from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.validation.metrics import mean_absolute_error


DEFAULT_WEIGHT_GRID = np.round(np.arange(0.0, 1.0001, 0.05), 2)


def best_weight(
    history: pd.DataFrame,
    weight_grid: np.ndarray = DEFAULT_WEIGHT_GRID,
) -> float:
    if history.empty:
        return 0.0
    best = 0.0
    best_error = float("inf")
    for weight in weight_grid:
        prediction = (
            weight * history["structural_log_yoy"]
            + (1.0 - weight) * history["v21_log_yoy"]
        )
        error = mean_absolute_error(history["actual_log_yoy"], prediction)
        if error < best_error:
            best = float(weight)
            best_error = error
    return best


def guarded_weight(history: pd.DataFrame) -> float:
    if history.empty:
        return 0.0
    structural_error = mean_absolute_error(
        history["actual_log_yoy"], history["structural_log_yoy"]
    )
    v21_error = mean_absolute_error(
        history["actual_log_yoy"], history["v21_log_yoy"]
    )
    return 0.0 if structural_error >= v21_error else best_weight(history)


def quality_adjusted_weight(
    base_weight: float,
    source_quality: float,
    production_source: str,
    no_company_production_max_weight: float = 0.25,
) -> float:
    quality = source_quality if np.isfinite(source_quality) else 0.35
    effective = base_weight * quality
    if production_source == "INDUSTRY_FALLBACK":
        effective = min(effective, no_company_production_max_weight)
    return float(np.clip(effective, 0.0, 1.0))
