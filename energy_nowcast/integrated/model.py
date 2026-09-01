from __future__ import annotations

import pandas as pd


SEGMENT_WEIGHTS = {
    "XOM": {"upstream": 0.35, "downstream": 0.45, "chemicals": 0.15, "other": 0.05},
    "CVX": {"upstream": 0.50, "downstream": 0.35, "chemicals": 0.10, "other": 0.05},
}


def predict_integrated(row: pd.Series) -> dict[str, float | str]:
    weights = SEGMENT_WEIGHTS[str(row["ticker"])]
    upstream_price = (
        0.75 * float(row["wti_log_yoy"])
        + 0.25 * float(row["henry_log_yoy"])
    )
    upstream_volume = (
        0.70 * float(row["us_crude_production_log_yoy"])
        + 0.30 * float(row["us_dry_gas_production_log_yoy"])
    )
    upstream = upstream_price + upstream_volume
    downstream = (
        float(row["product_price_basket_log_yoy"])
        + float(row["refinery_crude_input_log_yoy"])
    )
    # A consistent petrochemical-margin vintage is not available across the
    # free archive. Use the product-price versus refiner-feedstock spread as a
    # transparent, free STEO chemical-margin proxy.
    chemicals = (
        float(row["product_price_basket_log_yoy"])
        - float(row["refiner_crude_cost_log_yoy"])
    )
    other = float(row["lag_revenue_log_yoy"])
    prediction = (
        weights["upstream"] * upstream
        + weights["downstream"] * downstream
        + weights["chemicals"] * chemicals
        + weights["other"] * other
    )
    return {
        "candidate_prediction": prediction,
        "upstream_contribution_log_points": weights["upstream"] * upstream,
        "downstream_contribution_log_points": weights["downstream"] * downstream,
        "chemicals_contribution_log_points": weights["chemicals"] * chemicals,
        "other_contribution_log_points": weights["other"] * other,
        "structural_model": "INTEGRATED_SEGMENT_SOTP_V1",
    }
