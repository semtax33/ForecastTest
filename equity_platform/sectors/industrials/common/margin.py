from __future__ import annotations

import numpy as np
import pandas as pd


def attach_explicit_program_loss_normalization(
    history: pd.DataFrame,
    program_losses: pd.DataFrame,
) -> pd.DataFrame:
    """Keep reported actuals intact while creating a disclosed-loss-normalized research target."""
    if program_losses.empty:
        totals = pd.DataFrame(columns=["period", "segment", "pretax_program_loss_usd"])
    else:
        totals = program_losses.groupby(["period", "segment"], as_index=False)["pretax_program_loss_usd"].sum()
    frame = history.merge(totals, on=["period", "segment"], how="left", validate="one_to_one")
    frame["pretax_program_loss_usd"] = frame["pretax_program_loss_usd"].fillna(0.0)
    frame["model_operating_margin_pct"] = (
        (frame["operating_profit_usd"] + frame["pretax_program_loss_usd"])
        / frame["sales_usd"]
        * 100.0
    )
    return frame


def clip_prediction_to_training_range(
    prediction: float,
    training_values: pd.Series,
) -> tuple[float, float, float, bool]:
    lower = float(training_values.min())
    upper = float(training_values.max())
    clipped = float(np.clip(prediction, lower, upper))
    return clipped, lower, upper, bool(not np.isclose(clipped, prediction))
