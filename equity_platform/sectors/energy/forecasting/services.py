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



import numpy as np
import pandas as pd


SAFE_ACTIVITY_METRICS = {
    "SLB": "international_activity_log_yoy",
    "HAL": "completion_production_activity_log_yoy",
    "BKR": "orders_activity_log_yoy",
}


def predict_services_company_kpi(row: pd.Series) -> dict[str, object]:
    base = predict_services(row)
    column = SAFE_ACTIVITY_METRICS[str(row["ticker"])]
    company_activity = pd.to_numeric(row.get(column), errors="coerce")
    if not np.isfinite(company_activity) or abs(float(company_activity)) > 80.0:
        return {
            **base,
            "company_kpi_used": "",
            "company_kpi_feature_count": 0,
            "company_activity_effect_log_points": 0.0,
            "structural_model": "P4.1_SERVICES_COMPANY_KPI_FALLBACK_PROXY",
        }
    company_activity = float(np.clip(company_activity, -50.0, 50.0))
    target_macro_activity = (
        float(base["activity_contribution_log_points"])
        + float(base["service_intensity_contribution_log_points"])
    )
    profile_north_america = float(base["north_america_share"])
    lag_rig_activity = float(row["lag_total_rigs_log_yoy"])
    lag_service_intensity = (
        float(row["lag_us_crude_production_log_yoy"]) - lag_rig_activity
    )
    lag_macro_activity = (
        profile_north_america * (lag_rig_activity + 0.35 * lag_service_intensity)
        + (1.0 - profile_north_america)
        * float(row["lag_world_liquids_production_log_yoy"])
    )
    effect = 0.50 * (company_activity - lag_macro_activity)
    return {
        **base,
        "candidate_prediction": float(base["candidate_prediction"]) + effect,
        "company_activity_effect_log_points": effect,
        "company_activity_log_yoy": company_activity,
        "target_macro_activity_log_yoy": target_macro_activity,
        "lag_macro_activity_log_yoy": lag_macro_activity,
        "company_kpi_used": column.removesuffix("_log_yoy"),
        "company_kpi_feature_count": 1,
        "structural_model": "P4.1_SERVICES_COMPANY_KPI",
    }

