from __future__ import annotations

import numpy as np
import pandas as pd

from ..v35.taxonomy import E_AND_P_GROUPS


def gas_research_gate(
    time_score: pd.DataFrame,
    strict_prices: pd.DataFrame,
) -> pd.DataFrame:
    gas_tickers = set(E_AND_P_GROUPS["gas_heavy"])
    valid = time_score.loc[time_score["ticker"].isin(gas_tickers)].dropna(subset=["mase"])
    denominator = len(valid)
    covered_tickers = int(strict_prices["ticker"].nunique())
    mase_count = int(valid["mase"].lt(1.0).sum())
    no_regression = int(valid["improvement_log_points"].ge(0.0).sum())
    severe = int(valid["improvement_log_points"].lt(-2.0).sum())
    median_mase = float(valid["mase"].median()) if denominator else np.nan
    mean_mase = float(valid["mase"].mean()) if denominator else np.nan
    median_improvement = (
        float(valid["improvement_log_points"].median()) if denominator else np.nan
    )
    mase_share = mase_count / denominator if denominator else 0.0
    no_regression_share = no_regression / denominator if denominator else 0.0
    rows = [
        ("strict_realized_price_ticker_coverage", covered_tickers == 4, f"{covered_tickers}/4 gas-heavy tickers"),
        ("minimum_8_forecasts_per_gas_ticker", denominator == 4 and valid["observations"].ge(8).all(), f"{int(valid['observations'].ge(8).sum())}/4 gas-heavy tickers"),
        ("time_median_mase_below_0_80", median_mase < 0.80, f"{median_mase:.4f}"),
        ("time_mean_mase_below_0_90", mean_mase < 0.90, f"{mean_mase:.4f}"),
        ("time_mase_below_1_share_at_least_70pct", mase_share >= 0.70, f"{mase_count}/{denominator} evaluable = {mase_share:.1%}"),
        ("time_legacy_no_regression_at_least_70pct", no_regression_share >= 0.70, f"{no_regression}/{denominator} evaluable = {no_regression_share:.1%}"),
        ("time_median_improvement_positive", median_improvement > 0.0, f"{median_improvement:.4f}"),
        ("time_no_severe_ticker_regression", severe == 0, f"{severe}/{denominator} below -2.0"),
    ]
    passed = all(check for _, check, _ in rows)
    result = pd.DataFrame(rows, columns=["condition", "passed", "detail"])
    result["gas_research_gate"] = passed
    result["active_group_model"] = "GAS_BASIS_CANDIDATE" if passed else "LEGACY"
    result["gas_macro_research_unlocked"] = passed
    result["production_champion_changed"] = False
    return result

