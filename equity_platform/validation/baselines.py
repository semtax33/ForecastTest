from __future__ import annotations

import pandas as pd


def attach_naive_baseline(
    validation: pd.DataFrame,
    v21_validation: pd.DataFrame,
) -> pd.DataFrame:
    baseline = v21_validation[["quarter", "ticker", "naive"]].copy()
    baseline = baseline.rename(columns={"naive": "naive_log_yoy"})
    result = validation.merge(baseline, on=["quarter", "ticker"], how="left")
    if result["naive_log_yoy"].isna().any():
        missing = result.loc[
            result["naive_log_yoy"].isna(), ["ticker", "quarter"]
        ].to_dict("records")
        raise ValueError(f"missing naive predictions for validation rows: {missing}")
    return result

