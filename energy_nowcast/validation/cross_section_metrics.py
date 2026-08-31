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
            "revenue_mape_pct": mape,
            "legacy_mae_log_points": legacy_mae,
            "candidate_mae_log_points": candidate_mae,
            "improvement_log_points": legacy_mae - candidate_mae,
            "pi_80_coverage": coverage,
            "directional_hit_rate": float(valid["direction_correct"].mean()) if n else np.nan,
            "company_gate_pass": company_pass,
            "promoted": False,
        })
    return pd.DataFrame(rows)


def universe_summary(scorecard: pd.DataFrame, predictions: pd.DataFrame, validation: str) -> pd.DataFrame:
    valid = scorecard.dropna(subset=["mase"])
    count = len(valid)
    return pd.DataFrame([{
        "validation": validation,
        "company_count": count,
        "quarter_forecasts": int(len(predictions.dropna(subset=["candidate_prediction"]))),
        "median_ticker_mase": float(valid["mase"].median()) if count else np.nan,
        "mean_ticker_mase": float(valid["mase"].mean()) if count else np.nan,
        "mase_below_1_count": int(valid["mase"].lt(1.0).sum()),
        "mase_below_0_8_count": int(valid["mase"].lt(0.8).sum()),
        "mase_below_0_6_count": int(valid["mase"].lt(0.6).sum()),
        "beats_naive_pct": float(valid["mase"].lt(1.0).mean() * 100.0) if count else np.nan,
        "beats_legacy_pct": float(valid["improvement_log_points"].ge(0.0).mean() * 100.0) if count else np.nan,
        "median_improvement_log_points": float(valid["improvement_log_points"].median()) if count else np.nan,
        "mean_pi_80_coverage": float(valid["pi_80_coverage"].mean()) if count else np.nan,
        "mean_directional_hit_rate": float(valid["directional_hit_rate"].mean()) if count else np.nan,
    }])

