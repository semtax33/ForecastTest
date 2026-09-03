from __future__ import annotations

import numpy as np
import pandas as pd


def build_aggregate_error_decomposition(
    walk_forward: pd.DataFrame,
    *,
    company: str,
    period_column: str = "period",
    segment_column: str = "segment",
    actual_column: str = "actual_sales_usd",
    prediction_column: str = "predicted_sales_usd",
    naive_column: str = "naive_prior_year_sales_usd",
) -> dict[str, pd.DataFrame]:
    """Decompose aggregate forecast skill into raw segment skill and cancellation.

    For each period:
      aggregate naive error - aggregate model error
      = (aggregate naive error - sum absolute segment errors)
        + (sum absolute segment errors - absolute summed segment error)

    The first term is skill before diversification; the second is cancellation.
    """
    required = {
        period_column,
        segment_column,
        actual_column,
        prediction_column,
        naive_column,
    }
    missing = required - set(walk_forward.columns)
    if missing:
        raise ValueError(f"Missing error-decomposition columns: {sorted(missing)}")
    frame = walk_forward[list(required)].copy()
    if frame.duplicated([period_column, segment_column]).any():
        raise ValueError("One row per company-period-segment is required")
    frame["signed_segment_error_usd"] = frame[prediction_column] - frame[actual_column]
    frame["absolute_segment_error_usd"] = frame["signed_segment_error_usd"].abs()
    frame["signed_naive_segment_error_usd"] = frame[naive_column] - frame[actual_column]
    rows: list[dict[str, object]] = []
    for period, group in frame.groupby(period_column):
        signed = float(group["signed_segment_error_usd"].sum())
        signed_naive = float(group["signed_naive_segment_error_usd"].sum())
        gross = float(group["absolute_segment_error_usd"].sum())
        aggregate = abs(signed)
        naive = abs(signed_naive)
        cancellation = gross - aggregate
        pre_cancellation_skill = naive - gross
        aggregate_skill = naive - aggregate
        rows.append(
            {
                "company": company,
                "period": period,
                "segments": group[segment_column].nunique(),
                "aggregate_actual_usd": float(group[actual_column].sum()),
                "aggregate_prediction_usd": float(group[prediction_column].sum()),
                "aggregate_naive_usd": float(group[naive_column].sum()),
                "aggregate_model_absolute_error_usd": aggregate,
                "aggregate_naive_absolute_error_usd": naive,
                "sum_segment_absolute_error_usd": gross,
                "cancellation_benefit_usd": cancellation,
                "pre_cancellation_forecast_skill_usd": pre_cancellation_skill,
                "net_aggregate_forecast_skill_usd": aggregate_skill,
                "decomposition_identity_error_usd": abs(
                    aggregate_skill - (pre_cancellation_skill + cancellation)
                ),
                "cancellation_share_of_gross_segment_error_pct": (
                    cancellation / gross * 100.0 if gross else 0.0
                ),
            }
        )
    period = pd.DataFrame(rows).sort_values("period").reset_index(drop=True)
    pivot = frame.pivot(
        index=period_column, columns=segment_column, values="signed_segment_error_usd"
    )
    scaled = pivot.div(
        walk_forward.pivot(
            index=period_column, columns=segment_column, values=actual_column
        )
    )
    correlation = scaled.corr(min_periods=3)
    off_diagonal = correlation.to_numpy()[
        ~np.eye(len(correlation), dtype=bool)
    ]
    finite_off_diagonal = off_diagonal[np.isfinite(off_diagonal)]
    summary = pd.DataFrame(
        [
            {
                "company": company,
                "validation_periods": len(period),
                "segments": frame[segment_column].nunique(),
                "aggregate_model_mae_usd": float(
                    period["aggregate_model_absolute_error_usd"].mean()
                ),
                "aggregate_naive_mae_usd": float(
                    period["aggregate_naive_absolute_error_usd"].mean()
                ),
                "gross_segment_mae_sum_usd": float(
                    period["sum_segment_absolute_error_usd"].mean()
                ),
                "mean_cancellation_benefit_usd": float(
                    period["cancellation_benefit_usd"].mean()
                ),
                "mean_pre_cancellation_forecast_skill_usd": float(
                    period["pre_cancellation_forecast_skill_usd"].mean()
                ),
                "mean_net_aggregate_forecast_skill_usd": float(
                    period["net_aggregate_forecast_skill_usd"].mean()
                ),
                "mean_cancellation_share_pct": float(
                    period["cancellation_share_of_gross_segment_error_pct"].mean()
                ),
                "mean_off_diagonal_scaled_error_correlation": float(
                    finite_off_diagonal.mean()
                    if finite_off_diagonal.size
                    else np.nan
                ),
                "decomposition_identity_max_error_usd": float(
                    period["decomposition_identity_error_usd"].max()
                ),
                "aggregate_signal_positive_before_cancellation": bool(
                    period["pre_cancellation_forecast_skill_usd"].sum() > 0
                ),
                "aggregate_outperformance_depends_on_cancellation": bool(
                    period["net_aggregate_forecast_skill_usd"].sum() > 0
                    and period["pre_cancellation_forecast_skill_usd"].sum() <= 0
                ),
            }
        ]
    )
    correlation.index.name = "segment"
    return {
        "period_error_decomposition": period,
        "scaled_segment_error_correlation": correlation.reset_index(),
        "error_decomposition_summary": summary,
    }
