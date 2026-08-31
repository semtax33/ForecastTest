from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import ModelConfig
from ..models.blender import guarded_weight, quality_adjusted_weight


def shrink_weight(
    estimated_weight: float,
    n_observations: int,
    prior_weight: float = 0.75,
    k: float = 6.0,
) -> float:
    if n_observations < 0:
        raise ValueError("n_observations cannot be negative")
    denominator = n_observations + k
    reliability = 1.0 if denominator == 0 else n_observations / denominator
    return float(
        reliability * estimated_weight + (1.0 - reliability) * prior_weight
    )


def _base_weight(history: pd.DataFrame, config: ModelConfig) -> tuple[float, float]:
    if len(history) < config.min_blend_history:
        return 0.0, 0.0
    raw = guarded_weight(history)
    if raw <= 0.0:
        return 0.0, 0.0
    shrunk = shrink_weight(
        raw,
        len(history),
        prior_weight=config.shrinkage_prior_weight,
        k=config.shrinkage_k,
    )
    return raw, shrunk


def _predict_row(
    row: pd.Series,
    raw_weight: float,
    shrunk_weight: float,
) -> dict[str, float]:
    effective = quality_adjusted_weight(
        shrunk_weight,
        float(pd.to_numeric(row.get("source_quality_score"), errors="coerce")),
        str(row.get("production_yoy_source", "INDUSTRY_FALLBACK")),
    )
    prediction = float(
        np.clip(
            effective * float(row["structural_log_yoy"])
            + (1.0 - effective) * float(row["v21_log_yoy"]),
            -100.0,
            150.0,
        )
    )
    return {
        "raw_structural_weight": raw_weight,
        "shrunk_structural_weight": shrunk_weight,
        "effective_structural_weight": effective,
        "v21_weight": 1.0 - effective,
        "prediction_log_yoy": prediction,
    }


def walk_forward_validation(
    validation: pd.DataFrame,
    config: ModelConfig,
) -> pd.DataFrame:
    """Re-run blending with a genuinely untouched final test block per ticker."""
    rows: list[dict] = []
    for ticker, source in validation.groupby("ticker", sort=True):
        company = source.sort_values("quarter").reset_index(drop=True).copy()
        test_size = min(config.untouched_test_quarters, len(company))
        train_size = len(company) - test_size
        training = company.iloc[:train_size].copy()

        for index, row in company.iterrows():
            is_test = index >= train_size and test_size > 0
            if is_test:
                history = training
            else:
                history = training.iloc[:index]
            raw, shrunk = _base_weight(history, config)
            output = row.to_dict()
            output.update(_predict_row(row, raw, shrunk))
            output["evaluation_split"] = (
                "untouched_test" if is_test else "train_validation"
            )
            output["weight_history_observations"] = int(len(history))
            rows.append(output)
    return pd.DataFrame(rows).sort_values(["quarter", "ticker"]).reset_index(drop=True)


def current_weights(
    validation: pd.DataFrame,
    config: ModelConfig,
) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for ticker, history in validation.groupby("ticker", sort=True):
        raw, shrunk = _base_weight(history, config)
        rows.append(
            {
                "ticker": ticker,
                "history_observations": int(len(history)),
                "raw_structural_weight": raw,
                "shrunk_structural_weight": shrunk,
            }
        )
    return pd.DataFrame(rows)
