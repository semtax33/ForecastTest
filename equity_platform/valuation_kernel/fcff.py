from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from equity_platform.economics import FormulaId, evaluate_formula


@dataclass(frozen=True)
class DcfAssumptions:
    ticker: str
    scenario: str
    base_revenue_usd: float
    near_term_growth_pct: float
    terminal_growth_pct: float
    initial_margin_pct: float
    terminal_margin_pct: float
    tax_rate_pct: float
    initial_roic_pct: float
    terminal_roic_pct: float
    wacc_pct: float
    first_discount_years: float = 1.0
    horizon_years: int = 5

    def validate(self) -> None:
        material = (
            self.base_revenue_usd,
            self.near_term_growth_pct,
            self.terminal_growth_pct,
            self.initial_margin_pct,
            self.terminal_margin_pct,
            self.tax_rate_pct,
            self.initial_roic_pct,
            self.terminal_roic_pct,
            self.wacc_pct,
            self.first_discount_years,
        )
        if not all(np.isfinite(material)):
            raise ValueError("DCF assumptions must be finite")
        if self.base_revenue_usd <= 0:
            raise ValueError("Base revenue must be positive")
        if min(self.initial_roic_pct, self.terminal_roic_pct) <= 0:
            raise ValueError("ROIC must be positive")
        if self.wacc_pct <= self.terminal_growth_pct:
            raise ValueError("WACC must exceed terminal growth")
        if self.first_discount_years <= 0 or self.horizon_years < 1:
            raise ValueError("DCF timing must be positive")


def _fade(start: float, end: float, year: int, horizon: int) -> float:
    weight = (year - 1) / max(horizon - 1, 1)
    return start * (1.0 - weight) + end * weight


def enterprise_value(
    assumptions: DcfAssumptions,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """The single evaluator used by both forward valuation and reverse solving."""

    assumptions.validate()
    revenue = assumptions.base_revenue_usd
    wacc = assumptions.wacc_pct / 100.0
    rows: list[dict[str, object]] = []
    for year in range(1, assumptions.horizon_years + 1):
        growth = _fade(
            assumptions.near_term_growth_pct,
            assumptions.terminal_growth_pct,
            year,
            assumptions.horizon_years,
        )
        margin = _fade(
            assumptions.initial_margin_pct,
            assumptions.terminal_margin_pct,
            year,
            assumptions.horizon_years,
        )
        roic = _fade(
            assumptions.initial_roic_pct,
            assumptions.terminal_roic_pct,
            year,
            assumptions.horizon_years,
        )
        revenue *= 1.0 + growth / 100.0
        ebit = evaluate_formula(
            FormulaId.EBIT_REVENUE_MARGIN,
            {"revenue": revenue, "operating_margin_pct": margin},
        )
        nopat = evaluate_formula(
            FormulaId.NOPAT_IDENTITY,
            {"ebit": ebit, "tax_rate_pct": assumptions.tax_rate_pct},
        )
        reinvestment_rate = evaluate_formula(
            FormulaId.GROWTH_REINVESTMENT_IDENTITY,
            {"growth": growth, "roic": roic},
        )
        reinvestment = nopat * reinvestment_rate
        fcff = evaluate_formula(
            FormulaId.FCFF_IDENTITY,
            {"nopat": nopat, "reinvestment": reinvestment},
        )
        exponent = assumptions.first_discount_years + year - 1
        discount_factor = (1.0 + wacc) ** exponent
        rows.append(
            {
                "ticker": assumptions.ticker,
                "scenario": assumptions.scenario,
                "forecast_year_index": year,
                "revenue_usd": revenue,
                "revenue_growth_pct": growth,
                "operating_margin_pct": margin,
                "ebit_usd": ebit,
                "tax_rate_pct": assumptions.tax_rate_pct,
                "nopat_usd": nopat,
                "roic_pct": roic,
                "reinvestment_rate_pct": reinvestment_rate * 100.0,
                "reinvestment_usd": reinvestment,
                "fcff_usd": fcff,
                "discount_exponent_years": exponent,
                "discount_factor": discount_factor,
                "pv_fcff_usd": fcff / discount_factor,
            }
        )
    terminal_growth = assumptions.terminal_growth_pct / 100.0
    terminal_revenue = revenue * (1.0 + terminal_growth)
    terminal_ebit = evaluate_formula(
        FormulaId.EBIT_REVENUE_MARGIN,
        {
            "revenue": terminal_revenue,
            "operating_margin_pct": assumptions.terminal_margin_pct,
        },
    )
    terminal_nopat = evaluate_formula(
        FormulaId.NOPAT_IDENTITY,
        {"ebit": terminal_ebit, "tax_rate_pct": assumptions.tax_rate_pct},
    )
    terminal_reinvestment_rate = evaluate_formula(
        FormulaId.GROWTH_REINVESTMENT_IDENTITY,
        {
            "growth": assumptions.terminal_growth_pct,
            "roic": assumptions.terminal_roic_pct,
        },
    )
    terminal_fcff = terminal_nopat * (1.0 - terminal_reinvestment_rate)
    terminal_value = terminal_fcff / (wacc - terminal_growth)
    terminal_exponent = assumptions.first_discount_years + assumptions.horizon_years - 1
    pv_terminal = terminal_value / ((1.0 + wacc) ** terminal_exponent)
    explicit_pv = float(sum(float(row["pv_fcff_usd"]) for row in rows))
    value = explicit_pv + pv_terminal
    rows[-1].update(
        {
            "terminal_reinvestment_rate_pct": terminal_reinvestment_rate * 100.0,
            "terminal_fcff_usd": terminal_fcff,
            "terminal_value_usd": terminal_value,
            "pv_terminal_value_usd": pv_terminal,
        }
    )
    return pd.DataFrame(rows), {
        "explicit_period_pv_usd": explicit_pv,
        "pv_terminal_value_usd": pv_terminal,
        "enterprise_value_usd": value,
        "terminal_value_share_pct": pv_terminal / value * 100.0,
    }


def solve_parameter(
    assumptions: DcfAssumptions,
    *,
    target_ev_usd: float,
    field: str,
    lower: float,
    upper: float,
    tolerance_usd: float = 100.0,
    maximum_iterations: int = 240,
) -> dict[str, object]:
    if field not in DcfAssumptions.__dataclass_fields__:
        raise ValueError(f"Unknown DCF field: {field}")

    def residual(value: float) -> float:
        candidate = replace(assumptions, **{field: value})
        return enterprise_value(candidate)[1]["enterprise_value_usd"] - target_ev_usd

    low_error, high_error = residual(lower), residual(upper)
    if low_error == 0:
        return {"status": "SOLVED", "value": lower, "residual_usd": 0.0}
    if high_error == 0:
        return {"status": "SOLVED", "value": upper, "residual_usd": 0.0}
    if low_error * high_error > 0:
        return {
            "status": "UNBRACKETED_NO_SOLUTION_IN_DOMAIN",
            "value": np.nan,
            "residual_usd": min(abs(low_error), abs(high_error)),
        }
    low, high = lower, upper
    middle = (low + high) / 2.0
    error = np.inf
    for _ in range(maximum_iterations):
        middle = (low + high) / 2.0
        error = residual(middle)
        if abs(error) <= tolerance_usd:
            break
        if low_error * error <= 0:
            high = middle
        else:
            low = middle
            low_error = error
    return {"status": "SOLVED", "value": middle, "residual_usd": error}
