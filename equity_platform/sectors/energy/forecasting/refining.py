from __future__ import annotations

import pandas as pd


def predict_refiner(row: pd.Series) -> dict[str, float | str]:
    price = float(row["product_price_basket_log_yoy"])
    throughput = float(row["refinery_crude_input_log_yoy"])
    crack = float(row["crack_321_per_bbl"])
    crude_input = float(row["refinery_crude_input"])
    return {
        "candidate_prediction": price + throughput,
        "product_price_contribution_log_points": price,
        "throughput_contribution_log_points": throughput,
        "forecast_crack_321_per_bbl": crack,
        # $/bbl times million bbl/day = $ million/day before capture rate and opex.
        "refining_margin_driver_usd_million_per_day": crack * crude_input,
        "margin_signal_only": True,
        "structural_model": "REFINER_PRODUCT_PRICE_X_THROUGHPUT_V1",
    }



import numpy as np
import pandas as pd


def predict_refiner_company_kpi(row: pd.Series) -> dict[str, object]:
    base = predict_refiner(row)
    throughput = pd.to_numeric(row.get("company_throughput_log_yoy"), errors="coerce")
    if not np.isfinite(throughput):
        return {
            **base,
            "company_kpi_used": "",
            "company_kpi_feature_count": 0,
            "company_throughput_effect_log_points": 0.0,
            "structural_model": "P2.1_REFINING_COMPANY_KPI_FALLBACK_PROXY",
        }
    throughput = float(np.clip(throughput, -50.0, 50.0))
    lag_macro_throughput = float(row["lag_refinery_crude_input_log_yoy"])
    effect = throughput - lag_macro_throughput
    return {
        **base,
        "candidate_prediction": float(base["candidate_prediction"]) + effect,
        "throughput_contribution_log_points": throughput,
        "company_throughput_effect_log_points": effect,
        "company_kpi_used": "company_throughput",
        "company_kpi_feature_count": 1,
        "structural_model": "P2.1_REFINING_COMPANY_KPI",
    }

