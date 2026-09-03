from __future__ import annotations

import pandas as pd

from equity_platform.core.uncertainty import prequential_absolute_conformal


def build_lmt_uncertainty_calibration(*, walk_forward: pd.DataFrame, point_summary: pd.DataFrame, minimum_calibration_observations: int) -> dict[str, pd.DataFrame]:
    revenue_rows, revenue_summary = prequential_absolute_conformal(
        walk_forward, company="LMT", actual_column="actual_sales_usd", predicted_column="predicted_sales_usd",
        target_name="SEGMENT_REVENUE_USD", minimum_calibration_observations=minimum_calibration_observations,
        eligible_column="revenue_performance_claim_allowed",
    )
    margin_rows, margin_summary = prequential_absolute_conformal(
        walk_forward, company="LMT", actual_column="actual_operating_margin_pct", predicted_column="predicted_operating_margin_pct",
        target_name="SEGMENT_OPERATING_MARGIN_PCT", minimum_calibration_observations=minimum_calibration_observations,
        eligible_column="margin_performance_claim_allowed",
    )
    summary = pd.concat([revenue_summary, margin_summary], ignore_index=True)
    point = pd.concat([
        point_summary[["segment", "revenue_champion_eligible"]].rename(columns={"revenue_champion_eligible": "point_champion"}).assign(target="SEGMENT_REVENUE_USD"),
        point_summary[["segment", "margin_champion_eligible"]].rename(columns={"margin_champion_eligible": "point_champion"}).assign(target="SEGMENT_OPERATING_MARGIN_PCT"),
    ], ignore_index=True)
    summary = summary.merge(point, on=["segment", "target"], how="left", validate="one_to_one")
    summary["point_and_uncertainty_authority_separate"] = True
    gate = pd.DataFrame([{
        "segments_targets_evaluated": len(summary), "point_champions": int(summary["point_champion"].sum()),
        "uncertainty_champions": int(summary["uncertainty_champion"].sum()),
        "insufficient_calibration_targets": int(summary["status"].eq("INSUFFICIENT_CALIBRATION_N").sum()),
        "point_champion_equals_uncertainty_champion_policy": False, "uncertainty_terminal_input_allowed": False,
        "status": "HOLD_UNCERTAINTY_CALIBRATION" if not summary["uncertainty_champion"].all() else "UNCERTAINTY_RESEARCH_READY",
    }])
    return {"lmt_conformal_intervals": pd.concat([revenue_rows, margin_rows], ignore_index=True), "lmt_uncertainty_summary": summary, "lmt_uncertainty_gate": gate}

