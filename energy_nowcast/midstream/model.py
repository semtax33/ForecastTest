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
