from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DcfAssumptions:
    base_revenue_usd: float
    near_term_growth_pct: float
    operating_margin_pct: float
    tax_rate_pct: float
    roic_pct: float
    wacc_pct: float
    terminal_growth_pct: float
    horizon_years: int = 5

    def validate(self) -> None:
        if self.base_revenue_usd <= 0:
            raise ValueError("Base revenue must be positive")
        if self.roic_pct <= 0:
            raise ValueError("ROIC must be positive for the reinvestment identity")
        if self.wacc_pct <= self.terminal_growth_pct:
            raise ValueError("WACC must exceed terminal growth")
        if self.horizon_years < 1:
            raise ValueError("DCF horizon must be positive")


def enterprise_value(assumptions: DcfAssumptions) -> tuple[list[dict[str, float]], float]:
    assumptions.validate()
    revenue = assumptions.base_revenue_usd
    wacc = assumptions.wacc_pct / 100.0
    terminal_growth = assumptions.terminal_growth_pct / 100.0
    projections: list[dict[str, float]] = []
    for year in range(1, assumptions.horizon_years + 1):
        fade = (year - 1) / max(assumptions.horizon_years - 1, 1)
        growth_pct = (
            assumptions.near_term_growth_pct * (1.0 - fade)
            + assumptions.terminal_growth_pct * fade
        )
        revenue *= 1.0 + growth_pct / 100.0
        ebit = revenue * assumptions.operating_margin_pct / 100.0
        nopat = ebit * (1.0 - assumptions.tax_rate_pct / 100.0)
        reinvestment_rate = growth_pct / assumptions.roic_pct
        reinvestment = nopat * reinvestment_rate
        fcff = nopat - reinvestment
        discount_factor = (1.0 + wacc) ** year
        projections.append(
            {
                "forecast_year": year,
                "revenue_usd": revenue,
                "growth_pct": growth_pct,
                "ebit_usd": ebit,
                "nopat_usd": nopat,
                "reinvestment_rate": reinvestment_rate,
                "reinvestment_usd": reinvestment,
                "fcff_usd": fcff,
                "discount_factor": discount_factor,
                "pv_fcff_usd": fcff / discount_factor,
            }
        )
    terminal_revenue = revenue * (1.0 + terminal_growth)
    terminal_nopat = (
        terminal_revenue
        * assumptions.operating_margin_pct
        / 100.0
        * (1.0 - assumptions.tax_rate_pct / 100.0)
    )
    terminal_reinvestment_rate = (
        assumptions.terminal_growth_pct / assumptions.roic_pct
    )
    terminal_fcff = terminal_nopat * (1.0 - terminal_reinvestment_rate)
    terminal_value = terminal_fcff / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1.0 + wacc) ** assumptions.horizon_years)
    value = sum(row["pv_fcff_usd"] for row in projections) + pv_terminal
    projections[-1].update(
        {
            "terminal_reinvestment_rate": terminal_reinvestment_rate,
            "terminal_fcff_usd": terminal_fcff,
            "terminal_value_usd": terminal_value,
            "pv_terminal_value_usd": pv_terminal,
        }
    )
    return projections, float(value)


def solve_implied_growth(
    assumptions: DcfAssumptions,
    target_enterprise_value_usd: float,
    lower_pct: float = -10.0,
    upper_pct: float = 15.0,
    tolerance_usd: float = 1.0,
    maximum_iterations: int = 200,
) -> dict[str, float | str]:
    def residual(growth: float) -> float:
        candidate = DcfAssumptions(
            **{
                **assumptions.__dict__,
                "near_term_growth_pct": growth,
            }
        )
        return enterprise_value(candidate)[1] - target_enterprise_value_usd

    low_error = residual(lower_pct)
    high_error = residual(upper_pct)
    if low_error == 0:
        return {"status": "SOLVED", "implied_growth_pct": lower_pct, "residual_usd": 0.0}
    if high_error == 0:
        return {"status": "SOLVED", "implied_growth_pct": upper_pct, "residual_usd": 0.0}
    if low_error * high_error > 0:
        return {
            "status": "UNBRACKETED_NO_SOLUTION_IN_DOMAIN",
            "implied_growth_pct": float("nan"),
            "residual_usd": min(abs(low_error), abs(high_error)),
        }
    low, high = lower_pct, upper_pct
    middle = (low + high) / 2.0
    middle_error = residual(middle)
    for _ in range(maximum_iterations):
        middle = (low + high) / 2.0
        middle_error = residual(middle)
        if abs(middle_error) <= tolerance_usd:
            break
        if low_error * middle_error <= 0:
            high = middle
        else:
            low = middle
            low_error = middle_error
    return {
        "status": "SOLVED",
        "implied_growth_pct": middle,
        "residual_usd": middle_error,
    }
