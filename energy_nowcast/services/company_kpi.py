from __future__ import annotations

import numpy as np
import pandas as pd

from .model import predict_services


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
