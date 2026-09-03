from __future__ import annotations

import numpy as np
import pandas as pd


def ridge_predict(
    training: pd.DataFrame,
    row: pd.Series,
    *,
    features: list[str],
    target: str,
    penalty: float,
) -> float:
    """Small-sample ridge with train-only imputation and standardization."""
    train = training.dropna(subset=[target]).copy()
    if train.empty:
        return np.nan
    x = train[features].astype(float)
    medians = x.median().fillna(0.0)
    x = x.fillna(medians)
    test = row[features].astype(float).fillna(medians)
    means = x.mean()
    scales = x.std(ddof=0).replace(0.0, 1.0).fillna(1.0)
    standardized = (x - means) / scales
    target_values = train[target].astype(float).to_numpy()
    target_mean = float(np.mean(target_values))
    matrix = standardized.to_numpy()
    coefficients = np.linalg.solve(
        matrix.T @ matrix + penalty * np.eye(len(features)),
        matrix.T @ (target_values - target_mean),
    )
    return float(target_mean + ((test - means) / scales).to_numpy() @ coefficients)
