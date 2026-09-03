from __future__ import annotations

import pandas as pd


CONTRACT_PROFILES = {
    "KMI": {"fee_share": 0.85, "gas_volume_share": 0.80, "tariff_escalator": 2.0},
    "WMB": {"fee_share": 0.90, "gas_volume_share": 0.90, "tariff_escalator": 2.0},
    "ET": {"fee_share": 0.70, "gas_volume_share": 0.55, "tariff_escalator": 2.0},
    "EPD": {"fee_share": 0.75, "gas_volume_share": 0.45, "tariff_escalator": 2.0},
}


def predict_midstream(row: pd.Series) -> dict[str, float | str]:
    profile = CONTRACT_PROFILES[str(row["ticker"])]
    volume = (
        profile["gas_volume_share"] * float(row["us_dry_gas_production_log_yoy"])
        + (1.0 - profile["gas_volume_share"])
        * float(row["us_crude_production_log_yoy"])
    )
    fee_driver = volume + profile["tariff_escalator"]
    commodity_driver = (
        profile["gas_volume_share"] * float(row["henry_log_yoy"])
        + (1.0 - profile["gas_volume_share"]) * float(row["wti_log_yoy"])
    )
    prediction = (
        profile["fee_share"] * fee_driver
        + (1.0 - profile["fee_share"]) * commodity_driver
    )
    return {
        "candidate_prediction": prediction,
        "fee_volume_contribution_log_points": profile["fee_share"] * fee_driver,
        "commodity_contribution_log_points": (
            (1.0 - profile["fee_share"]) * commodity_driver
        ),
        "fee_based_share": profile["fee_share"],
        "tariff_escalator_pct": profile["tariff_escalator"],
        "structural_model": "MIDSTREAM_VOLUME_X_FEE_TARIFF_V1",
    }



import numpy as np
import pandas as pd


SAFE_ACTIVITY_METRICS = {
    "KMI": ("gas_transport_volume_log_yoy", "gas_gathering_volume_log_yoy"),
    "WMB": ("gas_transport_volume_log_yoy", "gas_gathering_volume_log_yoy"),
    "ET": ("gas_transport_volume_log_yoy", "gas_gathering_volume_log_yoy"),
    "EPD": ("equivalent_pipeline_volume_log_yoy", "fee_gas_processing_volume_log_yoy"),
}


def predict_midstream_company_kpi(row: pd.Series) -> dict[str, object]:
    base = predict_midstream(row)
    ticker = str(row["ticker"])
    values: list[float] = []
    used: list[str] = []
    for column in SAFE_ACTIVITY_METRICS[ticker]:
        value = pd.to_numeric(row.get(column), errors="coerce")
        if np.isfinite(value) and abs(float(value)) <= 80.0:
            values.append(float(value))
            used.append(column.removesuffix("_log_yoy"))
    if not values:
        return {
            **base,
            "company_kpi_used": "",
            "company_kpi_feature_count": 0,
            "company_volume_effect_log_points": 0.0,
            "structural_model": "P3.1_MIDSTREAM_COMPANY_KPI_FALLBACK_PROXY",
        }
    profile = CONTRACT_PROFILES[ticker]
    company_volume = float(np.clip(np.median(values), -50.0, 50.0))
    lag_macro_volume = (
        profile["gas_volume_share"] * float(row["lag_us_dry_gas_production_log_yoy"])
        + (1.0 - profile["gas_volume_share"])
        * float(row["lag_us_crude_production_log_yoy"])
    )
    effect = profile["fee_share"] * (company_volume - lag_macro_volume)
    return {
        **base,
        "candidate_prediction": float(base["candidate_prediction"]) + effect,
        "fee_volume_contribution_log_points": (
            float(base["fee_volume_contribution_log_points"]) + effect
        ),
        "company_volume_effect_log_points": effect,
        "company_activity_log_yoy": company_volume,
        "company_kpi_used": ",".join(used),
        "company_kpi_feature_count": len(used),
        "structural_model": "P3.1_MIDSTREAM_COMPANY_KPI",
    }

