from __future__ import annotations

"""Backward-compatible facade over the shared FCFF valuation kernel.

This module deliberately keeps the original public API used by the frozen
Industrials experiments. All calculations, including reverse solving, are
delegated to :mod:`equity_platform.valuation_kernel` so forward and reverse
DCF cannot drift into separate implementations.
"""

from dataclasses import dataclass
from math import isfinite

from equity_platform.valuation_kernel import DcfAssumptions as KernelDcfAssumptions
from equity_platform.valuation_kernel import enterprise_value as kernel_enterprise_value
from equity_platform.valuation_kernel import solve_parameter


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
        _as_kernel_assumptions(self).validate()


def _as_kernel_assumptions(assumptions: DcfAssumptions) -> KernelDcfAssumptions:
    return KernelDcfAssumptions(
        ticker="LEGACY_COMPATIBILITY",
        scenario="LEGACY_COMPATIBILITY",
        base_revenue_usd=assumptions.base_revenue_usd,
        near_term_growth_pct=assumptions.near_term_growth_pct,
        terminal_growth_pct=assumptions.terminal_growth_pct,
        initial_margin_pct=assumptions.operating_margin_pct,
        terminal_margin_pct=assumptions.operating_margin_pct,
        tax_rate_pct=assumptions.tax_rate_pct,
        initial_roic_pct=assumptions.roic_pct,
        terminal_roic_pct=assumptions.roic_pct,
        wacc_pct=assumptions.wacc_pct,
        first_discount_years=1.0,
        horizon_years=assumptions.horizon_years,
    )


def enterprise_value(assumptions: DcfAssumptions) -> tuple[list[dict[str, float]], float]:
    """Return the historical row schema while using the shared evaluator."""

    frame, summary = kernel_enterprise_value(_as_kernel_assumptions(assumptions))
    projections: list[dict[str, float]] = []
    for row in frame.to_dict(orient="records"):
        legacy_row = {
            "forecast_year": row["forecast_year_index"],
            "revenue_usd": row["revenue_usd"],
            "growth_pct": row["revenue_growth_pct"],
            "ebit_usd": row["ebit_usd"],
            "nopat_usd": row["nopat_usd"],
            "reinvestment_rate": row["revenue_growth_pct"] / assumptions.roic_pct,
            "reinvestment_usd": row["reinvestment_usd"],
            "fcff_usd": row["fcff_usd"],
            "discount_factor": row["discount_factor"],
            "pv_fcff_usd": row["pv_fcff_usd"],
        }
        terminal_value = row.get("terminal_value_usd")
        if terminal_value is not None and isfinite(float(terminal_value)):
            legacy_row.update(
                {
                    "terminal_reinvestment_rate": (
                        assumptions.terminal_growth_pct / assumptions.roic_pct
                    ),
                    "terminal_fcff_usd": row["terminal_fcff_usd"],
                    "terminal_value_usd": row["terminal_value_usd"],
                    "pv_terminal_value_usd": row["pv_terminal_value_usd"],
                }
            )
        projections.append(legacy_row)
    return projections, float(summary["enterprise_value_usd"])


def solve_implied_growth(
    assumptions: DcfAssumptions,
    target_enterprise_value_usd: float,
    lower_pct: float = -10.0,
    upper_pct: float = 15.0,
    tolerance_usd: float = 1.0,
    maximum_iterations: int = 200,
) -> dict[str, float | str]:
    solved = solve_parameter(
        _as_kernel_assumptions(assumptions),
        target_ev_usd=target_enterprise_value_usd,
        field="near_term_growth_pct",
        lower=lower_pct,
        upper=upper_pct,
        tolerance_usd=tolerance_usd,
        maximum_iterations=maximum_iterations,
    )
    return {
        "status": solved["status"],
        "implied_growth_pct": solved["value"],
        "residual_usd": solved["residual_usd"],
    }
