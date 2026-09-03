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



import numpy as np
import pandas as pd


def _value(row: pd.Series, column: str) -> float | None:
    value = pd.to_numeric(row.get(column), errors="coerce")
    return float(np.clip(value, -50.0, 50.0)) if np.isfinite(value) else None


def predict_integrated_company_kpi(row: pd.Series) -> dict[str, object]:
    base = predict_integrated(row)
    weights = SEGMENT_WEIGHTS[str(row["ticker"])]
    prediction = float(base["candidate_prediction"])
    effects: dict[str, float] = {
        "upstream_company_kpi_effect_log_points": 0.0,
        "downstream_company_kpi_effect_log_points": 0.0,
        "chemicals_company_kpi_effect_log_points": 0.0,
    }
    used: list[str] = []

    upstream = _value(row, "upstream_total_boe_log_yoy")
    if upstream is not None:
        lag_macro_volume = (
            0.70 * float(row["lag_us_crude_production_log_yoy"])
            + 0.30 * float(row["lag_us_dry_gas_production_log_yoy"])
        )
        effect = weights["upstream"] * (upstream - lag_macro_volume)
        prediction += effect
        effects["upstream_company_kpi_effect_log_points"] = effect
        used.append("upstream_total_boe")

    downstream_values = [
        value
        for column in (
            "downstream_throughput_log_yoy",
            "downstream_product_sales_log_yoy",
        )
        if (value := _value(row, column)) is not None
    ]
    if downstream_values:
        company_volume = float(np.median(downstream_values))
        effect = weights["downstream"] * (
            company_volume - float(row["lag_refinery_crude_input_log_yoy"])
        )
        prediction += effect
        effects["downstream_company_kpi_effect_log_points"] = effect
        used.extend(
            column.removesuffix("_log_yoy")
            for column in (
                "downstream_throughput_log_yoy",
                "downstream_product_sales_log_yoy",
            )
            if _value(row, column) is not None
        )

    chemicals = _value(row, "chemicals_product_sales_log_yoy")
    if chemicals is not None:
        effect = weights["chemicals"] * chemicals
        prediction += effect
        effects["chemicals_company_kpi_effect_log_points"] = effect
        used.append("chemicals_product_sales")

    return {
        **base,
        **effects,
        "candidate_prediction": prediction,
        "company_kpi_used": ",".join(used),
        "company_kpi_feature_count": len(used),
        "structural_model": "P2.1_INTEGRATED_COMPANY_KPI",
    }

