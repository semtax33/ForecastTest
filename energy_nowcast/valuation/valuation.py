from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd


def _finite_quantile(values: pd.Series, quantile: float, fallback: float) -> float:
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(clean.quantile(quantile)) if len(clean) else fallback


def _clip(value: float, low: float, high: float) -> float:
    return float(np.clip(value, low, high))


def _probability_class(
    values: tuple[float, float, float],
    histories: tuple[pd.Series, pd.Series, pd.Series],
    guardrails: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
) -> tuple[str, str]:
    possible = all(low <= value <= high for value, (low, high) in zip(values, guardrails))
    if not possible:
        return "OUTSIDE_POSSIBLE", "FAIL_GUARDRAIL"
    ranges = []
    for history in histories:
        clean = pd.to_numeric(history, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        ranges.append({
            "q10": float(clean.quantile(0.10)),
            "q25": float(clean.quantile(0.25)),
            "q75": float(clean.quantile(0.75)),
            "q90": float(clean.quantile(0.90)),
        } if len(clean) else {"q10": -np.inf, "q25": -np.inf, "q75": np.inf, "q90": np.inf})
    probable = all(bounds["q25"] <= value <= bounds["q75"] for value, bounds in zip(values, ranges))
    plausible = all(bounds["q10"] <= value <= bounds["q90"] for value, bounds in zip(values, ranges))
    if probable:
        return "PROBABLE", "PASS"
    if plausible:
        return "PLAUSIBLE", "PASS"
    return "POSSIBLE", "PASS"


def build_scenario_assumptions(
    ttm: pd.DataFrame,
    market: pd.DataFrame,
    config: Mapping[str, object],
    anchor_growth: pd.DataFrame | None = None,
) -> pd.DataFrame:
    window = int(config["historical_distribution_quarters"])
    minimum = int(config["minimum_distribution_observations"])
    anchor_lookup: dict[str, dict[str, object]] = {}
    if anchor_growth is not None and len(anchor_growth):
        anchor_lookup = anchor_growth.set_index("ticker").to_dict("index")
    rows: list[dict[str, object]] = []
    for ticker, all_history in ttm.loc[ttm["ttm_complete"]].groupby("ticker", sort=True):
        history = all_history.sort_values("quarter_ordinal").tail(window)
        latest = history.iloc[-1]
        market_row = market.loc[market["ticker"].eq(ticker)].iloc[0]
        subindustry = str(latest["subindustry"])
        guardrail = config["guardrails"][subindustry]
        growth_history = history["revenue_growth_pct"]
        margin_history = history["operating_margin_pct"]
        roic_history = history["roic_pct"]
        median_growth = _finite_quantile(growth_history, 0.50, 2.0)
        anchor = anchor_lookup.get(ticker, {})
        anchor_value = pd.to_numeric(anchor.get("anchor_growth_pct"), errors="coerce")
        anchor_available = bool(np.isfinite(anchor_value))
        anchor_shift = float(anchor_value - median_growth) if anchor_available else 0.0
        for scenario in config["scenarios"]:
            growth = _finite_quantile(
                growth_history, float(scenario["growth_quantile"]), median_growth
            ) + anchor_shift
            margin = _finite_quantile(
                margin_history,
                float(scenario["margin_quantile"]),
                float(latest["operating_margin_pct"]),
            )
            roic = _finite_quantile(
                roic_history,
                float(scenario["roic_quantile"]),
                max(float(latest["roic_pct"]), 5.0),
            )
            growth = _clip(growth, guardrail["growth_min_pct"], guardrail["growth_max_pct"])
            margin = _clip(margin, guardrail["margin_min_pct"], guardrail["margin_max_pct"])
            roic = _clip(roic, guardrail["roic_min_pct"], guardrail["roic_max_pct"])
            wacc = max(
                3.0,
                float(market_row["wacc_pct"]) + float(scenario["wacc_shift_pct"]),
            )
            terminal_growth = min(
                float(scenario["terminal_growth_pct"]),
                float(config["terminal_growth_cap_pct"]),
                wacc - 1.0,
            )
            reinvestment_rate = _clip(growth / max(roic, 1.0) * 100.0, -50.0, 150.0)
            probability_class, validation = _probability_class(
                (growth, margin, roic),
                (growth_history, margin_history, roic_history),
                (
                    (guardrail["growth_min_pct"], guardrail["growth_max_pct"]),
                    (guardrail["margin_min_pct"], guardrail["margin_max_pct"]),
                    (guardrail["roic_min_pct"], guardrail["roic_max_pct"]),
                ),
            )
            rows.append({
                "ticker": ticker,
                "subindustry": subindustry,
                "base_financial_quarter": latest["quarter"],
                "primary_anchor": latest["primary_anchor"],
                "anchor_route": latest["anchor_route"],
                "scenario": scenario["name"],
                "probability": float(scenario["probability"]),
                "probability_class": probability_class,
                "assumption_validation": validation,
                "growth_pct": growth,
                "operating_margin_pct": margin,
                "roic_pct": roic,
                "reinvestment_rate_pct": reinvestment_rate,
                "wacc_pct": wacc,
                "terminal_growth_pct": terminal_growth,
                "tax_rate_pct": float(latest["effective_tax_rate"]) * 100.0,
                "historical_observations": len(history),
                "minimum_history_pass": len(history) >= minimum,
                "anchor_growth_override_used": anchor_available,
                "anchor_growth_pct": float(anchor_value) if anchor_available else np.nan,
                "anchor_growth_source": anchor.get("anchor_growth_source", "HISTORICAL_PIT_DISTRIBUTION"),
                "fixed_ratio_used": False,
                "production_eligible": False,
            })
    return pd.DataFrame(rows)


def _project_dcf(
    *,
    base_revenue: float,
    growth_pct: float,
    margin_pct: float,
    roic_pct: float,
    tax_rate_pct: float,
    wacc_pct: float,
    terminal_growth_pct: float,
    years: int,
) -> tuple[list[dict[str, float]], float]:
    revenue = float(base_revenue)
    projections: list[dict[str, float]] = []
    wacc = wacc_pct / 100.0
    terminal_growth = terminal_growth_pct / 100.0
    for year in range(1, years + 1):
        fade = (year - 1) / max(years - 1, 1)
        year_growth_pct = growth_pct * (1.0 - fade) + terminal_growth_pct * fade
        revenue *= 1.0 + year_growth_pct / 100.0
        ebit = revenue * margin_pct / 100.0
        nopat = ebit * (1.0 - tax_rate_pct / 100.0)
        reinvestment_rate_pct = _clip(
            year_growth_pct / max(roic_pct, 1.0) * 100.0, -50.0, 150.0
        )
        reinvestment = nopat * reinvestment_rate_pct / 100.0
        fcff = nopat - reinvestment
        discount_factor = (1.0 + wacc) ** year
        projections.append({
            "forecast_year": year,
            "revenue_usd": revenue,
            "growth_pct": year_growth_pct,
            "operating_margin_pct": margin_pct,
            "ebit_usd": ebit,
            "nopat_usd": nopat,
            "roic_pct": roic_pct,
            "reinvestment_rate_pct": reinvestment_rate_pct,
            "reinvestment_usd": reinvestment,
            "fcff_usd": fcff,
            "wacc_pct": wacc_pct,
            "discount_factor": discount_factor,
            "pv_fcff_usd": fcff / discount_factor,
        })
    last = projections[-1]
    terminal_nopat = (
        last["revenue_usd"] * (1.0 + terminal_growth)
        * margin_pct / 100.0 * (1.0 - tax_rate_pct / 100.0)
    )
    terminal_reinvestment_rate = _clip(
        terminal_growth_pct / max(roic_pct, 1.0) * 100.0, -50.0, 150.0
    )
    terminal_fcff = terminal_nopat * (1.0 - terminal_reinvestment_rate / 100.0)
    denominator = max(wacc - terminal_growth, 0.01)
    terminal_value = terminal_fcff / denominator
    enterprise_value = sum(row["pv_fcff_usd"] for row in projections) + (
        terminal_value / ((1.0 + wacc) ** years)
    )
    projections[-1].update({
        "terminal_reinvestment_rate_pct": terminal_reinvestment_rate,
        "terminal_fcff_usd": terminal_fcff,
        "terminal_value_usd": terminal_value,
        "pv_terminal_value_usd": terminal_value / ((1.0 + wacc) ** years),
    })
    return projections, float(enterprise_value)


def forward_dcf(
    assumptions: pd.DataFrame,
    market: pd.DataFrame,
    horizon_years: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    projection_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    market_lookup = market.set_index("ticker")
    for assumption in assumptions.itertuples(index=False):
        current = market_lookup.loc[assumption.ticker]
        projections, enterprise_value = _project_dcf(
            base_revenue=float(current["ttm_revenue"]),
            growth_pct=float(assumption.growth_pct),
            margin_pct=float(assumption.operating_margin_pct),
            roic_pct=float(assumption.roic_pct),
            tax_rate_pct=float(assumption.tax_rate_pct),
            wacc_pct=float(assumption.wacc_pct),
            terminal_growth_pct=float(assumption.terminal_growth_pct),
            years=horizon_years,
        )
        for row in projections:
            projection_rows.append({
                "ticker": assumption.ticker,
                "subindustry": assumption.subindustry,
                "scenario": assumption.scenario,
                **row,
            })
        equity_value = enterprise_value - float(current["total_debt_usd"]) + float(current["cash_usd"])
        fair_value = equity_value / float(current["shares_outstanding"])
        summary_rows.append({
            "ticker": assumption.ticker,
            "subindustry": assumption.subindustry,
            "scenario": assumption.scenario,
            "probability": assumption.probability,
            "probability_class": assumption.probability_class,
            "enterprise_value_usd": enterprise_value,
            "equity_value_usd": equity_value,
            "fair_value_per_share": fair_value,
            "market_price": current["market_price"],
            "value_gap_pct": (fair_value / float(current["market_price"]) - 1.0) * 100.0,
            "terminal_value_share": (
                projections[-1].get("pv_terminal_value_usd", np.nan) / enterprise_value
                if enterprise_value != 0 else np.nan
            ),
            "production_eligible": False,
        })
    summary = pd.DataFrame(summary_rows)
    weighted = (
        summary.assign(weighted_value=lambda frame: frame["fair_value_per_share"] * frame["probability"])
        .groupby(["ticker", "subindustry"], as_index=False)
        .agg(
            probability_weighted_fair_value=("weighted_value", "sum"),
            scenario_probability_sum=("probability", "sum"),
            market_price=("market_price", "first"),
        )
    )
    weighted["probability_weighted_value_gap_pct"] = (
        weighted["probability_weighted_fair_value"] / weighted["market_price"] - 1.0
    ) * 100.0
    weighted["production_eligible"] = False
    return pd.DataFrame(projection_rows), summary, weighted


def _enterprise_value_for_assumption(
    current: pd.Series,
    base: pd.Series,
    *,
    growth_pct: float | None = None,
    margin_pct: float | None = None,
    roic_pct: float | None = None,
    years: int = 5,
) -> float:
    _, value = _project_dcf(
        base_revenue=float(current["ttm_revenue"]),
        growth_pct=float(base["growth_pct"] if growth_pct is None else growth_pct),
        margin_pct=float(base["operating_margin_pct"] if margin_pct is None else margin_pct),
        roic_pct=float(base["roic_pct"] if roic_pct is None else roic_pct),
        tax_rate_pct=float(base["tax_rate_pct"]),
        wacc_pct=float(base["wacc_pct"]),
        terminal_growth_pct=float(base["terminal_growth_pct"]),
        years=years,
    )
    return value


def _grid_implied(
    grid: np.ndarray,
    evaluator,
    target: float,
) -> tuple[float, float]:
    values = np.array([evaluator(float(candidate)) for candidate in grid], dtype=float)
    errors = np.abs(values - target)
    index = int(np.nanargmin(errors))
    return float(grid[index]), float(values[index] - target)


def reverse_dcf(
    assumptions: pd.DataFrame,
    market: pd.DataFrame,
    horizon_years: int,
    maximum_cap_years: int,
) -> pd.DataFrame:
    market_lookup = market.set_index("ticker")
    base_lookup = assumptions.loc[assumptions["scenario"].eq("BASE")].set_index("ticker")
    rows: list[dict[str, object]] = []
    for ticker, base in base_lookup.iterrows():
        current = market_lookup.loc[ticker]
        target = float(current["market_enterprise_value_usd"])
        implied_growth, growth_residual = _grid_implied(
            np.linspace(-30.0, 50.0, 801),
            lambda value: _enterprise_value_for_assumption(
                current, base, growth_pct=value, years=horizon_years
            ),
            target,
        )
        implied_margin, margin_residual = _grid_implied(
            np.linspace(-20.0, 60.0, 801),
            lambda value: _enterprise_value_for_assumption(
                current, base, margin_pct=value, years=horizon_years
            ),
            target,
        )
        implied_roic, roic_residual = _grid_implied(
            np.linspace(1.0, 60.0, 591),
            lambda value: _enterprise_value_for_assumption(
                current, base, roic_pct=value, years=horizon_years
            ),
            target,
        )
        cap_grid = np.arange(1, maximum_cap_years + 1)
        implied_cap, cap_residual = _grid_implied(
            cap_grid,
            lambda value: _enterprise_value_for_assumption(
                current, base, years=int(value)
            ),
            target,
        )
        rows.append({
            "ticker": ticker,
            "subindustry": base["subindustry"],
            "market_enterprise_value_usd": target,
            "our_base_growth_pct": base["growth_pct"],
            "market_implied_growth_pct": implied_growth,
            "growth_expectations_gap_pct_points": base["growth_pct"] - implied_growth,
            "growth_solver_residual_pct_of_market_ev": growth_residual / target * 100.0,
            "our_base_operating_margin_pct": base["operating_margin_pct"],
            "market_implied_operating_margin_pct": implied_margin,
            "margin_expectations_gap_pct_points": base["operating_margin_pct"] - implied_margin,
            "margin_solver_residual_pct_of_market_ev": margin_residual / target * 100.0,
            "our_base_roic_pct": base["roic_pct"],
            "market_implied_roic_pct": implied_roic,
            "roic_expectations_gap_pct_points": base["roic_pct"] - implied_roic,
            "roic_solver_residual_pct_of_market_ev": roic_residual / target * 100.0,
            "our_competitive_advantage_period_years": horizon_years,
            "market_implied_competitive_advantage_period_years": int(implied_cap),
            "cap_expectations_gap_years": horizon_years - int(implied_cap),
            "cap_solver_residual_pct_of_market_ev": cap_residual / target * 100.0,
            "reverse_dcf_method": "ONE_VARIABLE_AT_A_TIME_GRID_HOLDING_BASE_ASSUMPTIONS",
            "production_eligible": False,
        })
    return pd.DataFrame(rows)


def run_valuation(
    ttm: pd.DataFrame,
    market: pd.DataFrame,
    config: Mapping[str, object],
    anchor_growth: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    assumptions = build_scenario_assumptions(ttm, market, config, anchor_growth)
    projections, scenario_values, weighted = forward_dcf(
        assumptions, market, int(config["forecast_horizon_years"])
    )
    reverse = reverse_dcf(
        assumptions,
        market,
        int(config["forecast_horizon_years"]),
        int(config["maximum_reverse_dcf_cap_years"]),
    )
    expectations = reverse.merge(
        weighted,
        on=["ticker", "subindustry"],
        how="left",
        validate="one_to_one",
    )
    return {
        "scenario_assumptions": assumptions,
        "dcf_projections": projections,
        "forward_dcf_scenario_values": scenario_values,
        "forward_dcf_probability_weighted": weighted,
        "reverse_dcf_expectations": reverse,
        "expectations_gap": expectations,
    }

