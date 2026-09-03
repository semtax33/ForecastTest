from __future__ import annotations

import pandas as pd


def leave_one_company_out(backtester: object, panel: pd.DataFrame) -> pd.DataFrame:
    """Public LOCO entry point; the backtester owns the fixed modeling rules."""
    return backtester.run_loco(panel)  # type: ignore[attr-defined]


