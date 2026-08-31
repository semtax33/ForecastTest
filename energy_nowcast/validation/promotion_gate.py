from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


MINIMUM_CONSENSUS_OBSERVATIONS = 20


def seven_condition_promotion_gate(
    champion: dict[str, float],
    candidate: dict[str, float],
    ticker_scorecard: pd.DataFrame,
    consensus: dict[str, Any],
    minimum_candidate_observations: int = 20,
    revenue_mape_tolerance_pct: float = 0.25,
    severe_regression_log_points: float = 2.0,
) -> pd.DataFrame:
    observations = int(candidate.get("observations", 0))
    consensus_n = int(consensus.get("matched_observations", 0))
    rows = [
        ("overall_mase_not_worse", candidate.get("mase", np.nan) <= champion["mase"], f"{candidate.get('mase')} <= {champion['mase']}"),
        ("revenue_mape_within_tolerance", candidate.get("revenue_mape_pct", np.nan) <= champion["revenue_mape_pct"] + revenue_mape_tolerance_pct, f"tolerance={revenue_mape_tolerance_pct}"),
        ("untouched_or_live_forward_not_worse", bool(candidate.get("untouched_not_worse", False)), str(candidate.get("untouched_status", "MISSING"))),
        ("prediction_interval_coverage_normal", 0.65 <= candidate.get("pi_80_coverage", np.nan) <= 0.95, f"80% coverage={candidate.get('pi_80_coverage')}"),
        ("minimum_candidate_observations", observations >= minimum_candidate_observations, f"{observations}/{minimum_candidate_observations}"),
        ("no_severe_existing_ticker_regression", bool((ticker_scorecard["improvement_log_points"] >= -severe_regression_log_points).all()), f"floor={-severe_regression_log_points}"),
        (
            "beats_consensus_when_eligible",
            True if consensus_n < MINIMUM_CONSENSUS_OBSERVATIONS else consensus.get("model_mae", np.inf) < consensus.get("consensus_mae", -np.inf),
            f"matched={consensus_n}; deferred below {MINIMUM_CONSENSUS_OBSERVATIONS}",
        ),
    ]
    result = pd.DataFrame(rows, columns=["condition", "passed", "detail"])
    locked = consensus_n < MINIMUM_CONSENSUS_OBSERVATIONS
    result["model_change_lock"] = "LOCKED" if locked else "UNLOCKED_FOR_EVALUATION"
    result["promotion_eligible"] = bool(result["passed"].all()) and not locked
    return result


def universe_promotion_gate(
    time_scorecard: pd.DataFrame,
    loco_scorecard: pd.DataFrame,
    live_forward_not_worse: bool | None,
    minimum_no_regression_share: float = 0.70,
) -> pd.DataFrame:
    time_median = float(time_scorecard["improvement_log_points"].median())
    loco_median = float(loco_scorecard["improvement_log_points"].median())
    time_share = float(time_scorecard["improvement_log_points"].ge(0).mean())
    loco_share = float(loco_scorecard["improvement_log_points"].ge(0).mean())
    rows = [
        ("company_no_regression", bool(loco_scorecard["company_gate_pass"].all()), "all LOCO companies"),
        ("median_universe_improvement", time_median >= 0 and loco_median >= 0, f"time={time_median:.3f}; loco={loco_median:.3f}"),
        ("at_least_70pct_no_regression", min(time_share, loco_share) >= minimum_no_regression_share, f"time={time_share:.1%}; loco={loco_share:.1%}"),
        ("untouched_company_holdout", loco_median >= 0, f"LOCO median improvement={loco_median:.3f}"),
        ("live_forward_not_worse", live_forward_not_worse is True, "PENDING" if live_forward_not_worse is None else str(live_forward_not_worse)),
    ]
    result = pd.DataFrame(rows, columns=["condition", "passed", "detail"])
    result["universe_promotion"] = bool(result["passed"].all())
    return result


def apply_combined_promotion(scorecard: pd.DataFrame, universe_gate: pd.DataFrame) -> pd.DataFrame:
    result = scorecard.copy()
    result["promoted"] = result["company_gate_pass"] & bool(universe_gate["universe_promotion"].iloc[0])
    return result

