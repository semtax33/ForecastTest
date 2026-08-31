from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


MINIMUM_MATCHED_OBSERVATIONS = 20


def build_live_scorecard(connection: Any, minimum_observations: int = MINIMUM_MATCHED_OBSERVATIONS) -> tuple[pd.DataFrame, pd.DataFrame]:
    matched = pd.read_sql_query(
        """
        SELECT f.*, a.actual_revenue, a.release_date
        FROM forecast_snapshots f
        INNER JOIN actual_releases a
          ON f.ticker = a.ticker AND f.quarter = a.quarter
        WHERE a.release_date >= f.as_of_date
        ORDER BY f.as_of_date, f.ticker, f.quarter
        """,
        connection,
    )
    if matched.empty:
        summary = pd.DataFrame([_empty_summary(minimum_observations)])
        return matched, summary
    matched["model_error"] = matched["model_revenue"] - matched["actual_revenue"]
    matched["model_ape_pct"] = matched["model_error"].abs() / matched["actual_revenue"] * 100.0
    matched["consensus_error"] = matched["consensus_revenue"] - matched["actual_revenue"]
    matched["consensus_ape_pct"] = matched["consensus_error"].abs() / matched["actual_revenue"] * 100.0
    matched["model_consensus_edge"] = matched["model_revenue"] - matched["consensus_revenue"]
    matched["covered_80"] = matched["actual_revenue"].between(
        matched["lower_80_revenue"], matched["upper_80_revenue"]
    )
    matched["covered_95"] = matched["actual_revenue"].between(
        matched["lower_95_revenue"], matched["upper_95_revenue"]
    )
    matched["direction_correct"] = np.sign(matched["model_consensus_edge"]) == np.sign(
        matched["actual_revenue"] - matched["consensus_revenue"]
    )
    comparable = matched.dropna(subset=["consensus_revenue"])
    n = int(len(comparable))
    summary = pd.DataFrame([{
        "matched_observations": n,
        "model_mae": float(comparable["model_error"].abs().mean()) if n else np.nan,
        "consensus_mae": float(comparable["consensus_error"].abs().mean()) if n else np.nan,
        "model_vs_consensus_mae_ratio": (
            float(comparable["model_error"].abs().mean() / comparable["consensus_error"].abs().mean())
            if n and comparable["consensus_error"].abs().mean() > 0 else np.nan
        ),
        "pi_80_coverage": float(matched["covered_80"].mean()),
        "pi_95_coverage": float(matched["covered_95"].mean()),
        "directional_hit_rate": float(comparable["direction_correct"].mean()) if n else np.nan,
        "model_change_lock": "UNLOCKED_FOR_EVALUATION" if n >= minimum_observations else "LOCKED",
        "observations_needed": max(0, minimum_observations - n),
    }])
    return matched, summary


def _empty_summary(minimum_observations: int) -> dict[str, Any]:
    return {
        "matched_observations": 0,
        "model_mae": np.nan,
        "consensus_mae": np.nan,
        "model_vs_consensus_mae_ratio": np.nan,
        "pi_80_coverage": np.nan,
        "pi_95_coverage": np.nan,
        "directional_hit_rate": np.nan,
        "model_change_lock": "LOCKED",
        "observations_needed": minimum_observations,
    }

