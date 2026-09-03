from __future__ import annotations

import math

import numpy as np
import pandas as pd


def prequential_absolute_conformal(
    frame: pd.DataFrame,
    *,
    company: str,
    actual_column: str,
    predicted_column: str,
    target_name: str,
    minimum_calibration_observations: int,
    target_coverage: float = 0.80,
    eligible_column: str = "performance_claim_allowed",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate intervals using only errors observed before each forecast row."""
    rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for segment, group in frame.groupby("segment"):
        group = group.sort_values("period").reset_index(drop=True)
        residuals: list[float] = []
        segment_rows: list[dict[str, object]] = []
        for _, row in group.iterrows():
            n = len(residuals)
            quantile = lower = upper = np.nan
            covered: bool | float = np.nan
            if n >= 3:
                level = min(1.0, math.ceil((n + 1) * target_coverage) / n)
                quantile = float(pd.Series(residuals).quantile(level, interpolation="higher"))
                lower = float(row[predicted_column]) - quantile
                upper = float(row[predicted_column]) + quantile
                covered = bool(lower <= float(row[actual_column]) <= upper)
            result = {
                "company": company,
                "segment": segment,
                "target": target_name,
                "period": row["period"],
                "actual": row[actual_column],
                "point_prediction": row[predicted_column],
                "calibration_observations": n,
                "conformal_absolute_error_quantile": quantile,
                "pi80_lower": lower,
                "pi80_upper": upper,
                "covered": covered,
                "historical_only_calibration": True,
            }
            rows.append(result)
            segment_rows.append(result)
            if bool(row.get(eligible_column, True)):
                residuals.append(
                    abs(float(row[actual_column]) - float(row[predicted_column]))
                )
        interval = pd.DataFrame(segment_rows)
        evaluable = interval.dropna(subset=["covered"])
        maximum_n = max(
            (int(value) for value in interval["calibration_observations"]), default=0
        )
        coverage = (
            float(evaluable["covered"].mean() * 100.0) if not evaluable.empty else np.nan
        )
        lower_gate = (target_coverage - 0.05) * 100.0
        upper_gate = (target_coverage + 0.05) * 100.0
        champion = bool(
            maximum_n >= minimum_calibration_observations
            and lower_gate <= coverage <= upper_gate
        )
        summaries.append(
            {
                "company": company,
                "segment": segment,
                "target": target_name,
                "target_coverage_pct": target_coverage * 100.0,
                "evaluable_intervals": len(evaluable),
                "maximum_calibration_observations": maximum_n,
                "empirical_coverage_pct": coverage,
                "minimum_calibration_observations": minimum_calibration_observations,
                "uncertainty_champion": champion,
                "status": (
                    "UNCERTAINTY_CHAMPION"
                    if champion
                    else "INSUFFICIENT_CALIBRATION_N"
                    if maximum_n < minimum_calibration_observations
                    else "PI80_MISCALIBRATED"
                ),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(summaries)
