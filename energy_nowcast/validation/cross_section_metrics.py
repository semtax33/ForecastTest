from __future__ import annotations

import numpy as np
import pandas as pd


def ticker_scorecard(predictions: pd.DataFrame, minimum_observations: int = 4) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker, group in predictions.groupby("ticker", sort=True):
        valid = group.dropna(subset=["actual_log_yoy", "legacy_prediction", "candidate_prediction"])
        n = len(valid)
        naive_mae = float(valid["actual_log_yoy"].abs().mean()) if n else np.nan
        legacy_mae = float((valid["actual_log_yoy"] - valid["legacy_prediction"]).abs().mean()) if n else np.nan
        candidate_mae = float((valid["actual_log_yoy"] - valid["candidate_prediction"]).abs().mean()) if n else np.nan
        mase = candidate_mae / naive_mae if n and naive_mae > 0 else np.nan
        mape = float(valid["candidate_revenue_ape_pct"].mean()) if n else np.nan
        median_ape = float(valid["candidate_revenue_ape_pct"].median()) if n else np.nan
        revenue_abs_error = (
            valid["candidate_revenue"] - valid["revenue"]
        ).abs() if n and {"candidate_revenue", "revenue"}.issubset(valid) else pd.Series(dtype=float)
        revenue_denominator = valid["revenue"].abs().sum() if n and "revenue" in valid else 0.0
        wape = float(revenue_abs_error.sum() / revenue_denominator * 100.0) if revenue_denominator > 0 else np.nan
        coverage = float(valid["covered_80"].mean()) if n else np.nan
        company_pass = bool(
            n >= minimum_observations
            and np.isfinite(candidate_mae)
            and candidate_mae <= legacy_mae
        )
        rows.append({
            "ticker": ticker,
            "observations": n,
            "mase": mase,
            "revenue_wape_pct": wape,
            "revenue_median_ape_pct": median_ape,
            "revenue_mape_pct_diagnostic": mape,
            # Backward-compatible alias; MAPE is diagnostic, not a gate KPI.
            "revenue_mape_pct": mape,
            "small_denominator_observations": int(
                valid.get("small_denominator_flag", pd.Series(False, index=valid.index)).eq(True).sum()  # noqa: E712
            ) if n else 0,
            "legacy_mae_log_points": legacy_mae,
            "candidate_mae_log_points": candidate_mae,
            "improvement_log_points": legacy_mae - candidate_mae,
            "pi_80_coverage": coverage,
            # Row-wise validation can yield numpy.bool_ values in an object
            # Series. Summing that object dtype may collapse to a single True
            # instead of counting True observations (for example 1/8 for every
            # ticker). Equality produces a native boolean Series first.
            "directional_hit_rate": float(valid["direction_correct"].eq(True).mean()) if n else np.nan,  # noqa: E712
            "company_gate_pass": company_pass,
            "promoted": False,
        })
    return pd.DataFrame(rows)


def universe_summary(scorecard: pd.DataFrame, predictions: pd.DataFrame, validation: str) -> pd.DataFrame:
    valid = scorecard.dropna(subset=["mase"])
    count = len(valid)
    mase_below_1_count = int(valid["mase"].lt(1.0).sum())
    legacy_no_regression_count = int(valid["improvement_log_points"].ge(0.0).sum())
    prediction_valid = predictions.dropna(subset=["candidate_prediction"])
    revenue_valid = prediction_valid.dropna(subset=["candidate_revenue", "revenue"])
    revenue_denominator = revenue_valid["revenue"].abs().sum()
    return pd.DataFrame([{
        "validation": validation,
        "evaluable_company_count": count,
        "company_count": count,
        "quarter_forecasts": int(len(prediction_valid)),
        "median_ticker_mase": float(valid["mase"].median()) if count else np.nan,
        "mean_ticker_mase": float(valid["mase"].mean()) if count else np.nan,
        "mean_candidate_mae_log_points": float(valid["candidate_mae_log_points"].mean()) if count else np.nan,
        "mase_below_1_count": mase_below_1_count,
        "mase_below_1_share": float(mase_below_1_count / count) if count else np.nan,
        "mase_below_0_8_count": int(valid["mase"].lt(0.8).sum()),
        "mase_below_0_6_count": int(valid["mase"].lt(0.6).sum()),
        "beats_naive_pct": float(mase_below_1_count / count * 100.0) if count else np.nan,
        "legacy_no_regression_count": legacy_no_regression_count,
        "legacy_no_regression_share": float(legacy_no_regression_count / count) if count else np.nan,
        "beats_legacy_pct": float(legacy_no_regression_count / count * 100.0) if count else np.nan,
        "median_improvement_log_points": float(valid["improvement_log_points"].median()) if count else np.nan,
        "overall_revenue_wape_pct": (
            float((revenue_valid["candidate_revenue"] - revenue_valid["revenue"]).abs().sum() / revenue_denominator * 100.0)
            if revenue_denominator > 0 else np.nan
        ),
        "overall_revenue_median_ape_pct": float(revenue_valid["candidate_revenue_ape_pct"].median()) if len(revenue_valid) else np.nan,
        "overall_revenue_mape_pct_diagnostic": float(revenue_valid["candidate_revenue_ape_pct"].mean()) if len(revenue_valid) else np.nan,
        "small_denominator_observations": int(
            revenue_valid.get("small_denominator_flag", pd.Series(False, index=revenue_valid.index)).eq(True).sum()  # noqa: E712
        ),
        "mean_pi_80_coverage": float(valid["pi_80_coverage"].mean()) if count else np.nan,
        "mean_directional_hit_rate": float(valid["directional_hit_rate"].mean()) if count else np.nan,
    }])
