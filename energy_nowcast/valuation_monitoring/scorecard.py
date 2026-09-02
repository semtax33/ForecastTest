from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


MINIMUM_MATCHED_OBSERVATIONS = 20


def build_valuation_live_scorecard(
    connection: Any,
    minimum_observations: int = MINIMUM_MATCHED_OBSERVATIONS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    matched = pd.read_sql_query(
        """
        SELECT
            s.*,
            a.actual_ttm_fcff_usd,
            a.settlement_market_price,
            a.release_date,
            a.source_path AS settlement_source_path
        FROM valuation_snapshots s
        INNER JOIN valuation_settlements a
          ON s.as_of_date = a.snapshot_as_of_date
         AND s.ticker = a.ticker
         AND s.target_quarter = a.target_quarter
         AND s.model_version = a.model_version
        WHERE a.release_date > s.as_of_date
        ORDER BY s.as_of_date, s.ticker, s.target_quarter
        """,
        connection,
    )
    if matched.empty:
        return matched, pd.DataFrame([{
            "matched_observations": 0,
            "fcff_mape_pct": np.nan,
            "fair_value_to_settlement_price_mape_pct": np.nan,
            "median_initial_value_gap_pct": np.nan,
            "ep_matched_observations": 0,
            "model_change_lock": "LOCKED",
            "observations_needed": minimum_observations,
            "production_status": "NOT_PROMOTED_REQUIRES_SEPARATE_REVIEW",
        }])
    matched["fcff_error_usd"] = (
        matched["base_year1_fcff_usd"] - matched["actual_ttm_fcff_usd"]
    )
    matched["fcff_ape_pct"] = (
        matched["fcff_error_usd"].abs()
        / matched["actual_ttm_fcff_usd"].abs().replace(0, np.nan)
        * 100.0
    )
    matched["fair_value_to_settlement_price_ape_pct"] = (
        matched["fair_value"] / matched["settlement_market_price"] - 1.0
    ).abs() * 100.0
    count = int(len(matched))
    summary = pd.DataFrame([{
        "matched_observations": count,
        "fcff_mape_pct": float(matched["fcff_ape_pct"].mean()),
        "fair_value_to_settlement_price_mape_pct": float(
            matched["fair_value_to_settlement_price_ape_pct"].mean()
        ),
        "median_initial_value_gap_pct": float(matched["value_gap_pct"].median()),
        "ep_matched_observations": int(matched["subindustry"].eq("ep").sum()),
        "model_change_lock": (
            "UNLOCKED_FOR_EVALUATION"
            if count >= minimum_observations else "LOCKED"
        ),
        "observations_needed": max(0, minimum_observations - count),
        "production_status": "NOT_PROMOTED_REQUIRES_SEPARATE_REVIEW",
    }])
    return matched, summary
