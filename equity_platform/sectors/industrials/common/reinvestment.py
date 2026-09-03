from __future__ import annotations

import pandas as pd


BRIDGE_RATE_COLUMNS = ("capex_rate", "da_rate", "change_nwc_rate", "tax_rate")


def trailing_origin_available_rates(
    quarterly_actuals: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    window: int = 8,
) -> pd.Series | None:
    """Select only financial-statement ratios available at a forecast origin."""
    trailing = quarterly_actuals.loc[
        quarterly_actuals["filing_date"].le(cutoff)
        & quarterly_actuals["quarterly_statement_chain_complete"]
    ].tail(window)
    if trailing.empty:
        return None
    return trailing[list(BRIDGE_RATE_COLUMNS)].median()
