from __future__ import annotations

import numpy as np
import pandas as pd

from .model import predict_refiner


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
