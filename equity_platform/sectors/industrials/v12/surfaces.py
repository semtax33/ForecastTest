from __future__ import annotations

from dataclasses import replace

import pandas as pd

from equity_platform.valuation import DcfAssumptions, enterprise_value


def _point(
    assumptions: DcfAssumptions,
    *,
    target_ev: float,
    debt: float,
    cash: float,
    fp_value: float,
    shares: float,
    tolerance_pct: float,
) -> dict[str, object]:
    _, value = enterprise_value(assumptions)
    gap = value / target_ev * 100.0 - 100.0
    return {
        "growth_pct": assumptions.near_term_growth_pct,
        "margin_pct": assumptions.operating_margin_pct,
        "roic_pct": assumptions.roic_pct,
        "wacc_pct": assumptions.wacc_pct,
        "mpe_enterprise_value_usd": value,
        "market_target_mpe_enterprise_value_usd": target_ev,
        "market_value_gap_pct": gap,
        "market_match": abs(gap) <= tolerance_pct,
        "sotp_value_per_share": (value - debt + cash + fp_value) / shares,
    }


def _solve(
    base: DcfAssumptions,
    field: str,
    low: float,
    high: float,
    target_ev: float,
    tolerance_usd: float,
) -> dict[str, object]:
    def residual(value: float) -> float:
        return enterprise_value(replace(base, **{field: value}))[1] - target_ev

    low_error, high_error = residual(low), residual(high)
    if low_error * high_error > 0:
        return {"status": "UNBRACKETED_NO_SOLUTION_IN_DOMAIN", "solution_pct": float("nan"), "residual_usd": min(abs(low_error), abs(high_error))}
    middle, error = (low + high) / 2.0, float("nan")
    for _ in range(200):
        middle = (low + high) / 2.0
        error = residual(middle)
        if abs(error) <= tolerance_usd:
            break
        if low_error * error <= 0:
            high = middle
        else:
            low, low_error = middle, error
    return {"status": "SOLVED", "solution_pct": middle, "residual_usd": error}


def build_expectations_surfaces(
    *,
    baseline: DcfAssumptions,
    target_mpe_ev_usd: float,
    debt_usd: float,
    cash_usd: float,
    fp_value_usd: float,
    shares: float,
    margin_grid_pct: list[float],
    wacc_grid_pct: list[float],
    growth_grid_pct: list[float],
    roic_grid_pct: list[float],
    match_tolerance_pct: float,
    iso_margin_bounds_pct: tuple[float, float],
    iso_wacc_bounds_pct: tuple[float, float],
    solver_tolerance_usd: float,
) -> dict[str, pd.DataFrame]:
    common = {
        "target_ev": target_mpe_ev_usd,
        "debt": debt_usd,
        "cash": cash_usd,
        "fp_value": fp_value_usd,
        "shares": shares,
        "tolerance_pct": match_tolerance_pct,
    }
    margin_wacc = pd.DataFrame(
        [
            {"surface": "MARGIN_X_WACC", **_point(replace(baseline, operating_margin_pct=margin, wacc_pct=wacc), **common)}
            for margin in margin_grid_pct
            for wacc in wacc_grid_pct
        ]
    )
    growth_margin = pd.DataFrame(
        [
            {"surface": "GROWTH_X_MARGIN", **_point(replace(baseline, near_term_growth_pct=growth, operating_margin_pct=margin), **common)}
            for growth in growth_grid_pct
            for margin in margin_grid_pct
        ]
    )
    growth_roic = pd.DataFrame(
        [
            {"surface": "GROWTH_X_ROIC", **_point(replace(baseline, near_term_growth_pct=growth, roic_pct=roic), **common)}
            for growth in growth_grid_pct
            for roic in roic_grid_pct
        ]
    )
    iso_rows: list[dict[str, object]] = []
    for wacc in wacc_grid_pct:
        solved = _solve(replace(baseline, wacc_pct=wacc), "operating_margin_pct", *iso_margin_bounds_pct, target_mpe_ev_usd, solver_tolerance_usd)
        iso_rows.append({"condition": "WACC_FIXED_SOLVE_MARGIN", "fixed_wacc_pct": wacc, "fixed_margin_pct": float("nan"), "solved_parameter": "operating_margin_pct", **solved})
    for margin in margin_grid_pct:
        solved = _solve(replace(baseline, operating_margin_pct=margin), "wacc_pct", *iso_wacc_bounds_pct, target_mpe_ev_usd, solver_tolerance_usd)
        iso_rows.append({"condition": "MARGIN_FIXED_SOLVE_WACC", "fixed_wacc_pct": float("nan"), "fixed_margin_pct": margin, "solved_parameter": "wacc_pct", **solved})
    iso = pd.DataFrame(iso_rows)
    all_points = pd.concat([margin_wacc, growth_margin, growth_roic], ignore_index=True)
    summary = pd.DataFrame(
        [
            {
                "surface_points": len(all_points),
                "market_match_points": int(all_points["market_match"].sum()),
                "iso_conditions": len(iso),
                "iso_solved_conditions": int(iso["status"].eq("SOLVED").sum()),
                "iso_unbracketed_conditions": int(iso["status"].ne("SOLVED").sum()),
                "non_identification_preserved": True,
                "appropriate_parameter_claim_allowed": False,
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return {
        "expectations_surface_margin_wacc": margin_wacc,
        "expectations_surface_growth_margin": growth_margin,
        "expectations_surface_growth_roic": growth_roic,
        "expectations_iso_value_curve": iso,
        "expectations_surface_summary": summary,
    }
