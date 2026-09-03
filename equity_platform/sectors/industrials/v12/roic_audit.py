from __future__ import annotations

import numpy as np
import pandas as pd


def build_mpe_roic_audit(segment_history: pd.DataFrame) -> dict[str, pd.DataFrame]:
    history = segment_history.sort_values("fiscal_year").copy()
    history["delta_nopat_usd"] = history["mpe_nopat_usd"].diff()
    history["delta_invested_capital_usd"] = history["mpe_invested_capital_usd"].diff()
    history["incremental_roic_pct"] = np.where(
        history["delta_invested_capital_usd"].abs().gt(1.0),
        history["delta_nopat_usd"] / history["delta_invested_capital_usd"] * 100.0,
        np.nan,
    )
    history["roic_measure"] = "ANNUAL_INCREMENTAL_DELTA_NOPAT_OVER_DELTA_INVESTED_CAPITAL"
    history["terminal_input_allowed"] = False
    usable = history.dropna(subset=["mpe_roic_pct", "incremental_roic_pct"])
    first = history.iloc[0]
    latest = history.iloc[-1]
    delta_capital = float(latest["mpe_invested_capital_usd"] - first["mpe_invested_capital_usd"])
    endpoint_incremental = (
        float((latest["mpe_nopat_usd"] - first["mpe_nopat_usd"]) / delta_capital * 100.0)
        if abs(delta_capital) > 1.0
        else np.nan
    )
    cycle_rows = history.dropna(subset=["mpe_average_invested_capital_usd"])
    through_cycle = float(cycle_rows["mpe_nopat_usd"].sum() / cycle_rows["mpe_average_invested_capital_usd"].sum() * 100.0)
    summary = pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "measurement_years": len(history),
                "historical_roic_median_pct": history["mpe_roic_pct"].median(),
                "historical_roic_latest_pct": latest["mpe_roic_pct"],
                "annual_incremental_roic_median_pct": usable["incremental_roic_pct"].median(),
                "endpoint_incremental_roic_pct": endpoint_incremental,
                "through_cycle_aggregate_roic_pct": through_cycle,
                "roic_perimeter": "MPE_EQUITY_PLUS_MPE_DEBT_MINUS_MPE_CASH",
                "nopat_perimeter": "MPE_OPERATING_PROFIT_AFTER_EFFECTIVE_TAX",
                "financial_products_excluded": True,
                "goodwill_separately_identified": False,
                "intercompany_adjustments_embedded": True,
                "historical_equals_incremental": False,
                "incremental_equals_terminal": False,
                "terminal_roic_identified": False,
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    perimeter = pd.DataFrame(
        [
            {"component": "MP&E equity", "included": True, "latest_usd": latest["mpe_equity_usd"], "limitation": "Supplemental allocated equity"},
            {"component": "MP&E debt", "included": True, "latest_usd": latest["mpe_total_debt_usd"], "limitation": "Direct supplemental debt"},
            {"component": "MP&E cash", "included": True, "latest_usd": -latest["mpe_cash_usd"], "limitation": "Subtracted as non-operating cash"},
            {"component": "Financial Products", "included": False, "latest_usd": latest["financial_products_equity_usd"], "limitation": "Valued separately"},
            {"component": "Goodwill/intangibles", "included": True, "latest_usd": np.nan, "limitation": "Embedded; not separately observable in supplemental perimeter"},
        ]
    )
    return {"mpe_incremental_roic_history": history, "mpe_roic_perimeter_audit": perimeter, "mpe_roic_measure_summary": summary}
