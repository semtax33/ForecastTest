from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .champion import sha256_file, verify_champion
from .decision import classify_disagreement
from .store import insert_forecast_snapshot


def timing_label(as_of_date: date, expected_release_date: date | None = None) -> str:
    if expected_release_date is None:
        return f"INTRA_QUARTER_{as_of_date.isoformat()}"
    days = (expected_release_date - as_of_date).days
    if days < 0:
        return "POST_RELEASE"
    nearest = min((30, 15, 5), key=lambda value: abs(value - days))
    return f"T-{nearest}"


def capture_v34_snapshots(
    connection: Any,
    root: Path,
    as_of_date: date,
    timing: str | None = None,
) -> pd.DataFrame:
    """Verify the champion and append immutable snapshots from its frozen artifact."""
    manifest = verify_champion(root, "3.4")
    nowcast_path = root / "output" / "v3_4" / "nowcast.csv"
    consensus_path = root / "output" / "v3_4" / "current_model_vs_consensus.csv"
    nowcast = pd.read_csv(nowcast_path)
    consensus = pd.read_csv(consensus_path)
    joined = nowcast.merge(
        consensus[["ticker", "quarter", "consensus_revenue", "providers"]],
        left_on=["ticker", "nowcast_quarter"],
        right_on=["ticker", "quarter"],
        how="left",
    )
    rows: list[dict[str, Any]] = []
    for _, source in joined.iterrows():
        model_revenue = float(source["predicted_revenue_B"]) * 1e9
        lower_80 = float(source["lower_80_revenue_B"]) * 1e9
        upper_80 = float(source["upper_80_revenue_B"]) * 1e9
        consensus_revenue = float(pd.to_numeric(source["consensus_revenue"], errors="coerce"))
        decision = classify_disagreement(model_revenue, consensus_revenue, lower_80, upper_80)
        row = {
            "as_of_date": as_of_date.isoformat(),
            "ticker": str(source["ticker"]),
            "quarter": str(source["nowcast_quarter"]),
            "timing_label": timing or timing_label(as_of_date),
            "model_version": "3.4",
            "model_revenue": model_revenue,
            "model_log_yoy": source["predicted_revenue_log_yoy"],
            "lower_80_revenue": lower_80,
            "upper_80_revenue": upper_80,
            "lower_95_revenue": float(source["lower_95_revenue_B"]) * 1e9,
            "upper_95_revenue": float(source["upper_95_revenue_B"]) * 1e9,
            "consensus_revenue": consensus_revenue if np.isfinite(consensus_revenue) else None,
            "consensus_sources": source.get("providers"),
            "decision": decision["decision"],
            "disagreement_gap_pct": decision["gap_pct"],
            "champion_manifest_sha256": manifest["manifest_sha256"],
            "model_artifact_sha256": sha256_file(nowcast_path),
        }
        row["store_status"] = insert_forecast_snapshot(connection, row)
        rows.append(row)
    return pd.DataFrame(rows)

