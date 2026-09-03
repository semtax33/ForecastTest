from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    HiiDcfAssumptions,
    hii_enterprise_value,
)


def _base_assumptions(row: pd.Series) -> HiiDcfAssumptions:
    return HiiDcfAssumptions(
        scenario="base",
        base_revenue_usd=float(row["base_revenue_usd"]),
        near_term_growth_pct=float(row["near_term_growth_pct"]),
        terminal_growth_pct=float(row["terminal_growth_pct"]),
        initial_margin_pct=float(row["initial_margin_pct"]),
        terminal_margin_pct=float(row["terminal_margin_pct"]),
        tax_rate_pct=float(row["tax_rate_pct"]),
        initial_roic_pct=float(row["initial_roic_pct"]),
        terminal_roic_pct=float(row["terminal_roic_pct"]),
        wacc_pct=float(row["wacc_pct"]),
        first_discount_years=float(row["first_discount_years"]),
        horizon_years=int(row["horizon_years"]),
    )


def _solve_wacc(
    assumptions: HiiDcfAssumptions, target_ev_usd: float, lower: float, upper: float
) -> tuple[str, float, float]:
    def residual(wacc_pct: float) -> float:
        candidate = replace(assumptions, wacc_pct=wacc_pct)
        return hii_enterprise_value(candidate)[1]["enterprise_value_usd"] - target_ev_usd

    low_error, high_error = residual(lower), residual(upper)
    if low_error * high_error > 0:
        return "UNBRACKETED_NO_SOLUTION_IN_DOMAIN", float("nan"), min(
            abs(low_error), abs(high_error)
        )
    low, high = lower, upper
    middle, error = (low + high) / 2.0, float("inf")
    for _ in range(240):
        middle = (low + high) / 2.0
        error = residual(middle)
        if abs(error) <= 1.0:
            break
        if low_error * error <= 0:
            high = middle
        else:
            low = middle
            low_error = error
    return "SOLVED", middle, error


def build_operational_margin_valuation_crosscheck(
    *, root: Path, config: dict[str, Any], margin_cases: pd.DataFrame
) -> pd.DataFrame:
    output = root / Path(config["v52_output"])
    scenarios = pd.read_csv(output / "hii_dcf_scenario_assumptions_and_values.csv")
    market = pd.read_csv(output / "hii_market_capitalization_bridge.csv").iloc[0]
    wacc = pd.read_csv(output / "hii_wacc_range.csv").iloc[0]
    base = _base_assumptions(scenarios.loc[scenarios["scenario"].eq("base")].iloc[0])
    target_ev = float(market["market_enterprise_value_usd"])
    midpoint_wacc = float(wacc["midpoint_wacc_pct"])
    rows: list[dict[str, object]] = []
    for case in margin_cases.itertuples():
        margin = float(case.terminal_margin_pct)
        assumptions = replace(base, terminal_margin_pct=margin)
        status, implied_wacc, residual = _solve_wacc(
            assumptions,
            target_ev,
            max(assumptions.terminal_growth_pct + 0.25, 3.0),
            20.0,
        )
        value = hii_enterprise_value(replace(assumptions, wacc_pct=midpoint_wacc))[1]
        equity = (
            value["enterprise_value_usd"]
            - float(market["total_debt_usd"])
            + float(market["cash_usd"])
        )
        price = equity / float(market["shares_outstanding"])
        rows.append(
            {
                "margin_case": case.margin_case,
                "terminal_margin_pct": margin,
                "operational_evidence_class": case.operational_evidence_class,
                "market_implied_wacc_status": status,
                "market_implied_wacc_pct": implied_wacc,
                "solver_residual_usd": residual,
                "independent_wacc_low_pct": float(wacc["symmetric_wacc_pct"]),
                "independent_wacc_midpoint_pct": midpoint_wacc,
                "independent_wacc_high_pct": float(wacc["downside_wacc_pct"]),
                "implied_wacc_inside_independent_range": bool(
                    np.isfinite(implied_wacc)
                    and float(wacc["symmetric_wacc_pct"])
                    <= implied_wacc
                    <= float(wacc["downside_wacc_pct"])
                ),
                "conditional_value_at_independent_midpoint_wacc_per_share": price,
                "market_price": float(market["market_price"]),
                "conditional_value_gap_vs_market_pct": (
                    price / float(market["market_price"]) - 1.0
                )
                * 100.0,
                "terminal_value_share_pct": value["terminal_value_share_pct"],
                "high_terminal_dependence": bool(
                    value["terminal_value_share_pct"]
                    >= float(config["terminal_value_dependence_threshold_pct"])
                ),
                "valuation_upgrade_allowed": False,
                "fair_value_claim_allowed": False,
                "terminal_input_allowed": False,
            }
        )
    return pd.DataFrame(rows)
