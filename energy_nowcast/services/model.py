from __future__ import annotations

import numpy as np
import pandas as pd


ACTIVITY_PROFILES = {
    "SLB": {"north_america_share": 0.20, "international_share": 0.80},
    "HAL": {"north_america_share": 0.65, "international_share": 0.35},
    "BKR": {"north_america_share": 0.35, "international_share": 0.65},
}


def predict_services(row: pd.Series) -> dict[str, float | str]:
    profile = ACTIVITY_PROFILES[str(row["ticker"])]
    rig_activity = float(row["total_rigs_log_yoy"])
    service_intensity = float(row["us_crude_production_log_yoy"]) - rig_activity
    north_america_activity = rig_activity + 0.35 * service_intensity
    international_activity = float(row["world_liquids_production_log_yoy"])
    # Price signals lead customer CapEx, but cap the contribution so the model
    # remains an activity model rather than a disguised commodity-price model.
    capex_signal = float(np.clip(
        0.20 * float(row["wti_log_yoy"]) + 0.05 * float(row["henry_log_yoy"]),
        -8.0,
        8.0,
    ))
    activity = (
        profile["north_america_share"] * north_america_activity
        + profile["international_share"] * international_activity
    )
    prediction = activity + capex_signal
    return {
        "candidate_prediction": prediction,
        "activity_contribution_log_points": (
            profile["north_america_share"] * rig_activity
            + profile["international_share"] * international_activity
        ),
        "service_intensity_contribution_log_points": (
            profile["north_america_share"] * 0.35 * service_intensity
        ),
        "capex_pricing_contribution_log_points": capex_signal,
        "north_america_share": profile["north_america_share"],
        "structural_model": "OFS_ACTIVITY_X_INTENSITY_X_PRICING_V1",
    }
