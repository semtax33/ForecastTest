from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


NO_EDGE_THRESHOLD_PCT = 3.0


def classify_disagreement(
    model_revenue: float,
    consensus_revenue: float,
    lower_80: float,
    upper_80: float,
    no_edge_threshold_pct: float = NO_EDGE_THRESHOLD_PCT,
) -> dict[str, Any]:
    """Classify forecast disagreement; this is explicitly not an alpha signal."""
    values = (model_revenue, consensus_revenue, lower_80, upper_80)
    if any(not np.isfinite(value) for value in values) or consensus_revenue <= 0:
        return {
            "decision": "NO_CONSENSUS",
            "disagreement_direction": "UNKNOWN",
            "consensus_inside_80_pi": None,
            "gap_pct": np.nan,
            "interpretation": "No decision: comparable consensus/interval is unavailable.",
        }
    gap_pct = (model_revenue / consensus_revenue - 1.0) * 100.0
    inside = bool(lower_80 <= consensus_revenue <= upper_80)
    if abs(gap_pct) <= no_edge_threshold_pct:
        decision = "NO_EDGE"
    elif gap_pct > 0 and inside:
        decision = "WEAK_POSITIVE_DISAGREEMENT"
    elif gap_pct > 0:
        decision = "STRONG_POSITIVE_DISAGREEMENT"
    elif inside:
        decision = "WEAK_NEGATIVE_DISAGREEMENT"
    else:
        decision = "STRONG_NEGATIVE_DISAGREEMENT"
    return {
        "decision": decision,
        "disagreement_direction": "POSITIVE" if gap_pct > 0 else "NEGATIVE",
        "consensus_inside_80_pi": inside,
        "gap_pct": gap_pct,
        "interpretation": (
            "EDGE denotes model-consensus disagreement only; it is not demonstrated "
            "investment alpha or a buy/sell recommendation."
        ),
    }


def add_decision_layer(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    decisions = [
        classify_disagreement(
            float(row["model_revenue"]),
            float(row["consensus_revenue"]),
            float(row["lower_80_revenue"]),
            float(row["upper_80_revenue"]),
        )
        for _, row in result.iterrows()
    ]
    return pd.concat([result.reset_index(drop=True), pd.DataFrame(decisions)], axis=1)

