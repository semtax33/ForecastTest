from __future__ import annotations

import pandas as pd

from equity_platform.core.uncertainty import prequential_absolute_conformal


def build_uncertainty_calibration(
    *,
    cat_margin_walk_forward: pd.DataFrame,
    cat_margin_summary: pd.DataFrame,
    cmi_walk_forward: pd.DataFrame,
    cmi_summary: pd.DataFrame,
    minimum_calibration_observations: int,
) -> dict[str, pd.DataFrame]:
    cat = cat_margin_walk_forward.rename(
        columns={
            "actual_reported_margin_pct": "actual_margin_pct",
            "selected_predicted_margin_pct": "predicted_margin_pct",
        }
    ).copy()
    cat["performance_claim_allowed"] = ~cat["unforecastable_scope_change"].astype(bool)
    cat_rows, cat_summary = prequential_absolute_conformal(
        cat,
        company="CAT",
        actual_column="actual_margin_pct",
        predicted_column="predicted_margin_pct",
        target_name="MARGIN_PCT",
        minimum_calibration_observations=minimum_calibration_observations,
    )
    cmi_rows, cmi_uncertainty = prequential_absolute_conformal(
        cmi_walk_forward,
        company="CMI",
        actual_column="actual_ebitda_margin_pct",
        predicted_column="predicted_ebitda_margin_pct",
        target_name="EBITDA_MARGIN_PCT",
        minimum_calibration_observations=minimum_calibration_observations,
    )
    summary = pd.concat([cat_summary, cmi_uncertainty], ignore_index=True)
    point = pd.concat(
        [
            cat_margin_summary[["segment", "margin_champion_eligible"]]
            .rename(columns={"margin_champion_eligible": "point_champion"})
            .assign(company="CAT", target="MARGIN_PCT"),
            cmi_summary[["segment", "margin_champion_eligible"]]
            .rename(columns={"margin_champion_eligible": "point_champion"})
            .assign(company="CMI", target="EBITDA_MARGIN_PCT"),
        ],
        ignore_index=True,
    )
    summary = summary.merge(point, on=["company", "segment", "target"], how="left", validate="one_to_one")
    summary["point_and_uncertainty_authority_separate"] = True
    summary["point_champion_not_uncertainty_champion"] = (
        summary["point_champion"].astype(bool) & ~summary["uncertainty_champion"].astype(bool)
    )
    gate = pd.DataFrame(
        [
            {
                "segments_evaluated": len(summary),
                "point_champions": int(summary["point_champion"].sum()),
                "uncertainty_champions": int(summary["uncertainty_champion"].sum()),
                "insufficient_calibration_segments": int(summary["status"].eq("INSUFFICIENT_CALIBRATION_N").sum()),
                "point_champion_equals_uncertainty_champion_policy": False,
                "pi80_target_lower_pct": 75.0,
                "pi80_target_upper_pct": 85.0,
                "uncertainty_terminal_input_allowed": False,
                "status": "HOLD_UNCERTAINTY_CALIBRATION",
            }
        ]
    )
    return {
        "portability_conformal_intervals": pd.concat([cat_rows, cmi_rows], ignore_index=True),
        "portability_uncertainty_summary": summary,
        "portability_uncertainty_gate": gate,
    }
