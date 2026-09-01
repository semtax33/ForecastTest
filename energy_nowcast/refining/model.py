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
