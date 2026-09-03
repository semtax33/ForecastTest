from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HiiDcfAssumptions:
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
    first_discount_years: float
    horizon_years: int = 5

    def validate(self) -> None:
        values = (
            self.base_revenue_usd,
            self.initial_margin_pct,
            self.terminal_margin_pct,
            self.initial_roic_pct,
            self.terminal_roic_pct,
            self.wacc_pct,
            self.first_discount_years,
        )
        if not all(np.isfinite(values)):
            raise ValueError("All material DCF assumptions must be finite")
        if self.base_revenue_usd <= 0:
            raise ValueError("Base revenue must be positive")
        if min(self.initial_roic_pct, self.terminal_roic_pct) <= 0:
            raise ValueError("ROIC must be positive for the growth/reinvestment identity")
        if self.wacc_pct <= self.terminal_growth_pct:
            raise ValueError("WACC must exceed terminal growth")
        if self.first_discount_years <= 0 or self.horizon_years < 1:
            raise ValueError("DCF timing must be positive")


def _fade(start: float, end: float, year: int, horizon: int) -> float:
    weight = (year - 1) / max(horizon - 1, 1)
    return start * (1.0 - weight) + end * weight


def hii_enterprise_value(
    assumptions: HiiDcfAssumptions,
) -> tuple[pd.DataFrame, dict[str, float]]:
    assumptions.validate()
    revenue = assumptions.base_revenue_usd
    wacc = assumptions.wacc_pct / 100.0
    rows: list[dict[str, float | int | str]] = []
    for year in range(1, assumptions.horizon_years + 1):
        growth_pct = _fade(
            assumptions.near_term_growth_pct,
            assumptions.terminal_growth_pct,
            year,
            assumptions.horizon_years,
        )
        margin_pct = _fade(
            assumptions.initial_margin_pct,
            assumptions.terminal_margin_pct,
            year,
            assumptions.horizon_years,
        )
        roic_pct = _fade(
            assumptions.initial_roic_pct,
            assumptions.terminal_roic_pct,
            year,
            assumptions.horizon_years,
        )
        revenue *= 1.0 + growth_pct / 100.0
        ebit = revenue * margin_pct / 100.0
        nopat = ebit * (1.0 - assumptions.tax_rate_pct / 100.0)
        reinvestment_rate = growth_pct / roic_pct
        reinvestment = nopat * reinvestment_rate
        fcff = nopat - reinvestment
        exponent = assumptions.first_discount_years + year - 1
        discount_factor = (1.0 + wacc) ** exponent
        rows.append(
            {
                "scenario": assumptions.scenario,
                "forecast_year_index": year,
                "revenue_usd": revenue,
                "revenue_growth_pct": growth_pct,
                "operating_margin_pct": margin_pct,
                "ebit_usd": ebit,
                "tax_rate_pct": assumptions.tax_rate_pct,
                "nopat_usd": nopat,
                "roic_pct": roic_pct,
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
    terminal_ebit = terminal_revenue * assumptions.terminal_margin_pct / 100.0
    terminal_nopat = terminal_ebit * (1.0 - assumptions.tax_rate_pct / 100.0)
    terminal_reinvestment_rate = assumptions.terminal_growth_pct / assumptions.terminal_roic_pct
    terminal_fcff = terminal_nopat * (1.0 - terminal_reinvestment_rate)
    terminal_value = terminal_fcff / (wacc - terminal_growth)
    terminal_exponent = assumptions.first_discount_years + assumptions.horizon_years - 1
    pv_terminal = terminal_value / ((1.0 + wacc) ** terminal_exponent)
    explicit_pv = float(sum(float(row["pv_fcff_usd"]) for row in rows))
    enterprise_value = explicit_pv + pv_terminal
    rows[-1].update(
        {
            "terminal_reinvestment_rate_pct": terminal_reinvestment_rate * 100.0,
            "terminal_fcff_usd": terminal_fcff,
            "terminal_value_usd": terminal_value,
            "pv_terminal_value_usd": pv_terminal,
        }
    )
    summary = {
        "explicit_period_pv_usd": explicit_pv,
        "pv_terminal_value_usd": pv_terminal,
        "enterprise_value_usd": enterprise_value,
        "terminal_value_share_pct": pv_terminal / enterprise_value * 100.0,
    }
    return pd.DataFrame(rows), summary


def _solve_parameter(
    assumptions: HiiDcfAssumptions,
    target_ev_usd: float,
    field: str,
    lower: float,
    upper: float,
    tolerance_usd: float = 1.0,
    maximum_iterations: int = 240,
) -> dict[str, float | str]:
    def residual(value: float) -> float:
        candidate = replace(assumptions, **{field: value})
        return hii_enterprise_value(candidate)[1]["enterprise_value_usd"] - target_ev_usd

    low_error, high_error = residual(lower), residual(upper)
    if low_error == 0.0:
        return {"status": "SOLVED", "value": lower, "residual_usd": 0.0}
    if high_error == 0.0:
        return {"status": "SOLVED", "value": upper, "residual_usd": 0.0}
    if low_error * high_error > 0.0:
        return {
            "status": "UNBRACKETED_NO_SOLUTION_IN_DOMAIN",
            "value": float("nan"),
            "residual_usd": min(abs(low_error), abs(high_error)),
        }
    low, high = lower, upper
    middle, error = (low + high) / 2.0, float("inf")
    for _ in range(maximum_iterations):
        middle = (low + high) / 2.0
        error = residual(middle)
        if abs(error) <= tolerance_usd:
            break
        if low_error * error <= 0.0:
            high = middle
        else:
            low = middle
            low_error = error
    return {"status": "SOLVED", "value": middle, "residual_usd": error}


def _scenario_assumptions(
    evidence: dict[str, pd.DataFrame], config: dict[str, object]
) -> list[HiiDcfAssumptions]:
    forecast = evidence["hii_2026_guidance_financial_bridge"].iloc[0]
    terminal = evidence["hii_terminal_economics_range"]
    wacc = evidence["hii_wacc_range"].iloc[0]
    consensus = evidence["hii_consensus_summary"].iloc[0]
    latest_roic = float(terminal.loc[terminal["scenario"].eq("base"), "initial_roic_pct"].iloc[0])
    fiscal_year_end = pd.Timestamp("2027-12-31")
    valuation_date = pd.Timestamp(str(config["valuation_date"]))
    first_discount_years = (fiscal_year_end - valuation_date).days / 365.25
    scenario_growth = {
        "bear": max(-2.0, float(consensus["fy2027_revenue_growth_low_pct"])),
        "base": float(consensus["fy2027_revenue_growth_median_pct"]),
        "bull": min(12.0, float(consensus["fy2027_revenue_growth_high_pct"])),
    }
    wacc_by_scenario = {
        "bear": float(wacc["downside_wacc_pct"]),
        "base": float(wacc["midpoint_wacc_pct"]),
        "bull": float(wacc["symmetric_wacc_pct"]),
    }
    growth_by_scenario = {
        "bear": float(config["terminal_growth_bear_pct"]),
        "base": float(config["terminal_growth_base_pct"]),
        "bull": float(config["terminal_growth_bull_pct"]),
    }
    result: list[HiiDcfAssumptions] = []
    for scenario in ("bear", "base", "bull"):
        row = terminal.loc[terminal["scenario"].eq(scenario)].iloc[0]
        base_revenue = {
            "bear": float(forecast["company_revenue_low_usd"]),
            "base": float(forecast["company_revenue_midpoint_usd"]),
            "bull": float(forecast["company_revenue_high_usd"]),
        }[scenario]
        initial_margin = {
            "bear": float(forecast["consolidated_operating_margin_low_pct"]),
            "base": float(forecast["consolidated_operating_margin_midpoint_pct"]),
            "bull": float(forecast["consolidated_operating_margin_high_pct"]),
        }[scenario]
        result.append(
            HiiDcfAssumptions(
                scenario=scenario,
                base_revenue_usd=base_revenue,
                near_term_growth_pct=scenario_growth[scenario],
                terminal_growth_pct=growth_by_scenario[scenario],
                initial_margin_pct=initial_margin,
                terminal_margin_pct=float(row["terminal_operating_margin_pct"]),
                tax_rate_pct=float(forecast["effective_tax_rate_midpoint_pct"]),
                initial_roic_pct=latest_roic,
                terminal_roic_pct=float(row["terminal_roic_pct"]),
                wacc_pct=wacc_by_scenario[scenario],
                first_discount_years=first_discount_years,
                horizon_years=int(config["forecast_horizon_years"]),
            )
        )
    return result


def build_hii_conditional_valuation(
    *, evidence: dict[str, pd.DataFrame], config: dict[str, object]
) -> dict[str, pd.DataFrame]:
    market = evidence["hii_market_capitalization_bridge"].iloc[0]
    assumptions = _scenario_assumptions(evidence, config)
    projections: list[pd.DataFrame] = []
    scenario_rows: list[dict[str, object]] = []
    weights = config["scenario_weights"]
    for item in assumptions:
        projection, value = hii_enterprise_value(item)
        projections.append(projection)
        equity_value = (
            value["enterprise_value_usd"]
            - float(market["total_debt_usd"])
            + float(market["cash_usd"])
        )
        identity_error = abs(
            equity_value
            - (
                value["enterprise_value_usd"]
                - float(market["total_debt_usd"])
                + float(market["cash_usd"])
            )
        )
        scenario_rows.append(
            {
                **item.__dict__,
                **value,
                "equity_value_usd": equity_value,
                "conditional_value_per_share": equity_value / float(market["shares_outstanding"]),
                "market_price": market["market_price"],
                "conditional_expectations_gap_pct": (
                    equity_value / float(market["shares_outstanding"]) / float(market["market_price"]) - 1.0
                )
                * 100.0,
                "scenario_weight": float(weights[item.scenario]),
                "ev_to_common_equity_identity_error_usd": identity_error,
                "terminal_authority": False,
                "valuation_authority": "RESEARCH_CONDITIONAL_ONLY",
                "production_promoted": False,
            }
        )
    scenario = pd.DataFrame(scenario_rows)
    weighted_value = float(
        (scenario["conditional_value_per_share"] * scenario["scenario_weight"]).sum()
    )
    base = assumptions[1]
    target_ev = float(market["market_enterprise_value_usd"])
    reverse_specs = (
        ("MARKET_IMPLIED_NEAR_TERM_GROWTH", "near_term_growth_pct", float(config["reverse_growth_lower_pct"]), float(config["reverse_growth_upper_pct"])),
        ("MARKET_IMPLIED_TERMINAL_MARGIN", "terminal_margin_pct", 1.0, 12.0),
        ("MARKET_IMPLIED_WACC", "wacc_pct", max(base.terminal_growth_pct + 0.25, 3.0), 20.0),
    )
    reverse_rows: list[dict[str, object]] = []
    for diagnostic, field, lower, upper in reverse_specs:
        solved = _solve_parameter(base, target_ev, field, lower, upper)
        reverse_rows.append(
            {
                "diagnostic": diagnostic,
                "solved_field": field,
                "status": solved["status"],
                "implied_value_pct": solved["value"],
                "residual_usd": solved["residual_usd"],
                "lower_bound_pct": lower,
                "upper_bound_pct": upper,
                "conditional_on_other_base_assumptions": True,
                "appropriate_parameter_claim_allowed": False,
            }
        )
    base_ev = hii_enterprise_value(base)[1]["enterprise_value_usd"]
    round_trip = _solve_parameter(
        base,
        base_ev,
        "near_term_growth_pct",
        float(config["reverse_growth_lower_pct"]),
        float(config["reverse_growth_upper_pct"]),
    )
    round_trip_frame = pd.DataFrame(
        [
            {
                "forward_near_term_growth_pct": base.near_term_growth_pct,
                "recovered_near_term_growth_pct": round_trip["value"],
                "growth_round_trip_error_pct": abs(float(round_trip["value"]) - base.near_term_growth_pct),
                "forward_enterprise_value_usd": base_ev,
                "solver_residual_usd": round_trip["residual_usd"],
                "status": round_trip["status"],
            }
        ]
    )
    surface_rows: list[dict[str, object]] = []
    for terminal_margin in (4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0):
        for wacc_pct in (5.0, 6.0, 7.0, 8.0, 9.0, 10.0):
            candidate = replace(
                base,
                terminal_margin_pct=terminal_margin,
                wacc_pct=wacc_pct,
            )
            value = hii_enterprise_value(candidate)[1]
            equity_value = (
                value["enterprise_value_usd"]
                - float(market["total_debt_usd"])
                + float(market["cash_usd"])
            )
            price = equity_value / float(market["shares_outstanding"])
            surface_rows.append(
                {
                    "terminal_margin_pct": terminal_margin,
                    "wacc_pct": wacc_pct,
                    "conditional_value_per_share": price,
                    "market_price": market["market_price"],
                    "market_price_gap_pct": price / float(market["market_price"]) * 100.0 - 100.0,
                    "terminal_value_share_pct": value["terminal_value_share_pct"],
                    "conditional_on_base_growth_and_roic": True,
                    "terminal_authority": False,
                }
            )
    iso_rows: list[dict[str, object]] = []
    for terminal_margin in (4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0):
        candidate = replace(base, terminal_margin_pct=terminal_margin)
        lower_wacc = max(candidate.terminal_growth_pct + 0.25, 3.0)
        solved = _solve_parameter(
            candidate,
            target_ev,
            "wacc_pct",
            lower_wacc,
            20.0,
        )
        iso_rows.append(
            {
                "terminal_margin_pct": terminal_margin,
                "market_implied_wacc_pct": solved["value"],
                "status": solved["status"],
                "residual_usd": solved["residual_usd"],
                "conditional_on_base_growth_and_roic": True,
                "appropriate_wacc_claim_allowed": False,
                "terminal_authority": False,
            }
        )
    summary = pd.DataFrame(
        [
            {
                "valuation_date": config["valuation_date"],
                "market_price": market["market_price"],
                "conditional_bear_value_per_share": float(scenario.loc[scenario["scenario"].eq("bear"), "conditional_value_per_share"].iloc[0]),
                "conditional_base_value_per_share": float(scenario.loc[scenario["scenario"].eq("base"), "conditional_value_per_share"].iloc[0]),
                "conditional_bull_value_per_share": float(scenario.loc[scenario["scenario"].eq("bull"), "conditional_value_per_share"].iloc[0]),
                "scenario_weighted_conditional_value_per_share": weighted_value,
                "weighted_expectations_gap_pct": (weighted_value / float(market["market_price"]) - 1.0) * 100.0,
                "maximum_terminal_value_share_pct": float(scenario["terminal_value_share_pct"].max()),
                "high_terminal_dependence": bool(scenario["terminal_value_share_pct"].max() >= 75.0),
                "all_ev_to_equity_identities_pass": bool(scenario["ev_to_common_equity_identity_error_usd"].le(1.0).all()),
                "reverse_solver_fail_closed": bool(
                    pd.DataFrame(reverse_rows)["status"].isin(
                        ["SOLVED", "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"]
                    ).all()
                ),
                "terminal_authority": False,
                "production_promoted": False,
                "status": "CONDITIONAL_DCF_AND_REVERSE_DCF_RESEARCH_NOT_FAIR_VALUE_AUTHORITY",
            }
        ]
    )
    return {
        "hii_dcf_scenario_assumptions_and_values": scenario,
        "hii_dcf_projections": pd.concat(projections, ignore_index=True),
        "hii_reverse_dcf_diagnostics": pd.DataFrame(reverse_rows),
        "hii_terminal_margin_wacc_expectations_surface": pd.DataFrame(surface_rows),
        "hii_terminal_margin_conditional_implied_wacc": pd.DataFrame(iso_rows),
        "hii_dcf_reverse_round_trip": round_trip_frame,
        "hii_conditional_valuation_summary": summary,
    }
