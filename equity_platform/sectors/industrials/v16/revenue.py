from __future__ import annotations

import numpy as np
import pandas as pd


def build_revenue_champion_validation(
    validation: pd.DataFrame,
    *,
    maximum_mase: float,
    minimum_direction_accuracy_pct: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for segment, group in validation.groupby("segment"):
        errors = (group["actual_sales_usd"] - group["predicted_sales_usd"]).abs()
        naive_errors = (group["actual_sales_usd"] - group["naive_prior_year_sales_usd"]).abs()
        model_mae = float(errors.mean())
        naive_mae = float(naive_errors.mean())
        model_wape = float(errors.sum() / group["actual_sales_usd"].abs().sum() * 100.0)
        naive_wape = float(naive_errors.sum() / group["actual_sales_usd"].abs().sum() * 100.0)
        direction = float(
            (np.sign(group["actual_revenue_growth_pct"]) == np.sign(group["predicted_revenue_growth_pct"])).mean()
            * 100.0
        )
        mase = model_mae / naive_mae if naive_mae else np.nan
        champion = bool(
            mase < maximum_mase
            and model_wape < naive_wape
            and direction >= minimum_direction_accuracy_pct
        )
        rows.append(
            {
                "segment": segment,
                "validation_observations": len(group),
                "revenue_level_mae_usd": model_mae,
                "naive_prior_year_revenue_mae_usd": naive_mae,
                "revenue_level_mase": mase,
                "maximum_revenue_mase": maximum_mase,
                "revenue_wape_pct": model_wape,
                "naive_revenue_wape_pct": naive_wape,
                "revenue_direction_accuracy_pct": direction,
                "minimum_direction_accuracy_pct": minimum_direction_accuracy_pct,
                "no_material_regression": bool(model_mae <= naive_mae),
                "target_level_scaled_metric_pass": bool(mase < maximum_mase and model_wape < naive_wape),
                "revenue_champion_eligible": champion,
                "historical_pit_input": bool(group["historical_pit_input"].all()),
            }
        )
    return pd.DataFrame(rows)
