from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np
import pandas as pd


SCENARIO_VARIABLES = (
    "growth",
    "operating_margin",
    "reinvestment_rate",
    "roic",
    "wacc",
    "terminal_growth",
)


def _clean(values: pd.Series) -> pd.Series:
    return (
        pd.to_numeric(values, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )


def _quantile(values: pd.Series, q: float, fallback: float) -> float:
    clean = _clean(values)
    return float(clean.quantile(q)) if len(clean) else float(fallback)


def _shrunken_quantile(
    company: pd.Series,
    peers: pd.Series,
    q: float,
    fallback: float,
    prior_strength: float,
) -> float:
    clean = _clean(company)
    company_value = _quantile(clean, q, fallback)
    peer_value = _quantile(peers, q, fallback)
    weight = len(clean) / (len(clean) + prior_strength)
    return float(weight * company_value + (1.0 - weight) * peer_value)


def _bounded(value: float, lower: float, upper: float) -> dict[str, object]:
    final = float(np.clip(value, lower, upper))
    return {
        "raw": float(value),
        "final": final,
        "lower": float(lower),
        "upper": float(upper),
        "hit_lower": bool(value <= lower or np.isclose(final, lower)),
        "hit_upper": bool(value >= upper or np.isclose(final, upper)),
    }


def _story_class(
    values: tuple[float, float, float],
    histories: tuple[pd.Series, pd.Series, pd.Series],
) -> str:
    bounds = []
    for history in histories:
        clean = _clean(history)
        bounds.append({
            "q10": float(clean.quantile(0.10)),
            "q25": float(clean.quantile(0.25)),
            "q75": float(clean.quantile(0.75)),
            "q90": float(clean.quantile(0.90)),
        })
    if all(bound["q25"] <= value <= bound["q75"] for value, bound in zip(values, bounds)):
        return "PROBABLE"
    if all(bound["q10"] <= value <= bound["q90"] for value, bound in zip(values, bounds)):
        return "PLAUSIBLE"
    return "POSSIBLE"


def _boundary_columns(prefix: str, bounded: dict[str, object]) -> dict[str, object]:
    return {
        f"{prefix}_raw": bounded["raw"],
        f"{prefix}_lower_bound": bounded["lower"],
        f"{prefix}_upper_bound": bounded["upper"],
        f"{prefix}_hit_lower_bound": bounded["hit_lower"],
        f"{prefix}_hit_upper_bound": bounded["hit_upper"],
    }


def build_scenario_assumptions_v11(
    ttm: pd.DataFrame,
    market: pd.DataFrame,
    config: Mapping[str, object],
    anchor_growth: pd.DataFrame | None = None,
) -> pd.DataFrame:
    window = int(config["historical_distribution_quarters"])
    minimum = int(config["minimum_distribution_observations"])
    construction = config["scenario_construction"]
    prior_strength = float(construction["historical_prior_strength"])
    anchor_weight = float(construction["anchor_reliability_weight"])
    spread_scale = float(construction["scenario_spread_scale"])
    buffer_fraction = float(construction["guardrail_interior_buffer_fraction"])
    anchor_lookup = (
        anchor_growth.set_index("ticker").to_dict("index")
        if anchor_growth is not None and len(anchor_growth)
        else {}
    )
    eligible_ttm = ttm.loc[ttm["ttm_complete"]].copy()
    peer_histories = {
        subindustry: group.sort_values("quarter_ordinal").groupby(
            "ticker", group_keys=False
        ).tail(window)
        for subindustry, group in eligible_ttm.groupby("subindustry")
    }
    market_lookup = market.set_index("ticker")
    rows: list[dict[str, object]] = []
    for ticker, all_history in eligible_ttm.groupby("ticker", sort=True):
        history = all_history.sort_values("quarter_ordinal").tail(window)
        latest = history.iloc[-1]
        subindustry = str(latest["subindustry"])
        peers = peer_histories[subindustry]
        current = market_lookup.loc[ticker]
        guardrail = config["guardrails"][subindustry]
        growth_history = history["revenue_growth_pct"]
        margin_history = history["operating_margin_pct"]
        roic_history = history["roic_pct"]
        median_growth = _quantile(growth_history, 0.50, 2.0)
        growth_range = (
            float(guardrail["growth_max_pct"])
            - float(guardrail["growth_min_pct"])
        )
        interior_low = float(guardrail["growth_min_pct"]) + growth_range * buffer_fraction
        interior_high = float(guardrail["growth_max_pct"]) - growth_range * buffer_fraction
        regularized_median_growth = float(
            np.clip(median_growth, interior_low, interior_high)
        )
        historical_low = _quantile(growth_history, 0.10, interior_low)
        historical_high = _quantile(growth_history, 0.90, interior_high)
        anchor = anchor_lookup.get(ticker, {})
        anchor_raw = pd.to_numeric(anchor.get("anchor_growth_pct"), errors="coerce")
        anchor_available = bool(np.isfinite(anchor_raw))
        if anchor_available:
            anchor_lower = max(interior_low, min(historical_low, interior_high))
            anchor_upper = min(interior_high, max(historical_high, interior_low))
            if anchor_lower > anchor_upper:
                anchor_lower, anchor_upper = interior_low, interior_high
            anchor_winsorized = float(np.clip(anchor_raw, anchor_lower, anchor_upper))
            growth_center = (
                (1.0 - anchor_weight) * regularized_median_growth
                + anchor_weight * anchor_winsorized
            )
        else:
            anchor_lower, anchor_upper = np.nan, np.nan
            anchor_winsorized = np.nan
            growth_center = regularized_median_growth
        for scenario in config["scenarios"]:
            q = float(scenario["growth_quantile"])
            growth_quantile = _shrunken_quantile(
                growth_history,
                peers["revenue_growth_pct"],
                q,
                median_growth,
                prior_strength,
            )
            growth_raw = growth_center + spread_scale * (growth_quantile - median_growth)
            growth = _bounded(
                growth_raw,
                float(guardrail["growth_min_pct"]),
                float(guardrail["growth_max_pct"]),
            )
            margin_raw = _shrunken_quantile(
                margin_history,
                peers["operating_margin_pct"],
                float(scenario["margin_quantile"]),
                float(latest["operating_margin_pct"]),
                prior_strength,
            )
            margin = _bounded(
                margin_raw,
                float(guardrail["margin_min_pct"]),
                float(guardrail["margin_max_pct"]),
            )
            wacc_raw = float(current["wacc_adjusted_pct"]) + float(
                scenario["wacc_shift_pct"]
            )
            wacc = _bounded(
                wacc_raw,
                float(construction["wacc_min_pct"]),
                float(construction["wacc_max_pct"]),
            )
            terminal_upper = min(
                float(config["terminal_growth_cap_pct"]),
                float(wacc["final"]) - 1.0,
            )
            terminal = _bounded(
                float(scenario["terminal_growth_pct"]),
                0.0,
                terminal_upper,
            )
            roic_raw = _shrunken_quantile(
                roic_history,
                peers["roic_pct"],
                float(scenario["roic_quantile"]),
                max(float(latest["roic_pct"]), 5.0),
                prior_strength,
            )
            roic_lower = max(
                float(guardrail["roic_min_pct"]),
                float(terminal["final"])
                + float(construction["minimum_roic_spread_over_terminal_growth_pct"]),
            )
            roic = _bounded(roic_raw, roic_lower, float(guardrail["roic_max_pct"]))
            normalized_growth = (
                float(growth["final"]) + float(terminal["final"])
            ) / 2.0
            reinvestment_raw = normalized_growth / float(roic["final"]) * 100.0
            reinvestment = _bounded(
                reinvestment_raw,
                float(construction["reinvestment_min_pct"]),
                float(construction["reinvestment_max_pct"]),
            )
            story_class = _story_class(
                (
                    float(growth["final"]),
                    float(margin["final"]),
                    float(roic["final"]),
                ),
                (growth_history, margin_history, roic_history),
            )
            row = {
                "ticker": ticker,
                "subindustry": subindustry,
                "base_financial_quarter": latest["quarter"],
                "primary_anchor": latest["primary_anchor"],
                "anchor_route": latest["anchor_route"],
                "scenario": scenario["name"],
                "scenario_weight": float(scenario["default_scenario_weight"]),
                "scenario_weight_source": "DEFAULT_SCENARIO_WEIGHT_NOT_EMPIRICAL_PROBABILITY",
                "probability": float(scenario["default_scenario_weight"]),
                "story_validation_class": story_class,
                "probability_class": story_class,
                "assumption_validation": "PASS",
                "growth_pct": growth["final"],
                "operating_margin_pct": margin["final"],
                "forecast_normalized_roic_pct": roic["final"],
                "roic_pct": roic["final"],
                "normalized_growth_for_reinvestment_pct": normalized_growth,
                "reinvestment_rate_pct": reinvestment["final"],
                "wacc_pct": wacc["final"],
                "terminal_growth_pct": terminal["final"],
                "tax_rate_pct": float(latest["effective_tax_rate"]) * 100.0,
                "historical_incremental_roic_pct": latest["incremental_roic_pct"],
                "historical_growth_median_raw_pct": median_growth,
                "historical_growth_median_regularized_pct": regularized_median_growth,
                "historical_growth_median_regularized": bool(
                    not np.isclose(median_growth, regularized_median_growth)
                ),
                "historical_observations": len(history),
                "minimum_history_pass": len(history) >= minimum,
                "anchor_growth_override_used": anchor_available,
                "anchor_growth_raw_pct": float(anchor_raw) if anchor_available else np.nan,
                "anchor_growth_winsorized_pct": anchor_winsorized,
                "anchor_growth_lower_bound_pct": anchor_lower,
                "anchor_growth_upper_bound_pct": anchor_upper,
                "anchor_growth_winsorized": bool(
                    anchor_available and not np.isclose(anchor_raw, anchor_winsorized)
                ),
                "anchor_growth_source": anchor.get(
                    "anchor_growth_source", "HISTORICAL_PIT_DISTRIBUTION"
                ),
                "fundamental_growth_from_raw_reinvestment_pct": (
                    reinvestment_raw * float(roic["final"]) / 100.0
                ),
                "fixed_ratio_used": False,
                "production_eligible": False,
                **_boundary_columns("growth", growth),
                **_boundary_columns("operating_margin", margin),
                **_boundary_columns("roic", roic),
                **_boundary_columns("reinvestment_rate", reinvestment),
                **_boundary_columns("wacc", wacc),
                **_boundary_columns("terminal_growth", terminal),
            }
            rows.append(row)
    return pd.DataFrame(rows)


def project_dcf_v11(
    *,
    base_revenue: float,
    growth_pct: float,
    margin_pct: float,
    roic_pct: float,
    tax_rate_pct: float,
    wacc_pct: float,
    terminal_growth_pct: float,
    years: int,
) -> tuple[list[dict[str, float | str]], float]:
    revenue = float(base_revenue)
    projections: list[dict[str, float | str]] = []
    wacc = wacc_pct / 100.0
    terminal_growth = terminal_growth_pct / 100.0
    if wacc <= terminal_growth:
        raise ValueError("WACC must exceed terminal growth")
    for year in range(1, years + 1):
        fade = (year - 1) / max(years - 1, 1)
        year_growth_pct = growth_pct * (1.0 - fade) + terminal_growth_pct * fade
        revenue *= 1.0 + year_growth_pct / 100.0
        ebit = revenue * margin_pct / 100.0
        nopat = ebit * (1.0 - tax_rate_pct / 100.0)
        reinvestment_rate_pct = year_growth_pct / roic_pct * 100.0
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
            "forecast_normalized_roic_pct": roic_pct,
            "reinvestment_rate_pct": reinvestment_rate_pct,
            "reinvestment_usd": reinvestment,
            "fcff_usd": fcff,
            "fundamental_growth_reconstructed_pct": (
                reinvestment_rate_pct * roic_pct / 100.0
            ),
            "reinvestment_plausibility_status": (
                "WITHIN_REFERENCE_RANGE"
                if -50.0 <= reinvestment_rate_pct <= 150.0
                else "OUTSIDE_REFERENCE_RANGE_NOT_CLIPPED"
            ),
            "wacc_pct": wacc_pct,
            "discount_factor": discount_factor,
            "pv_fcff_usd": fcff / discount_factor,
        })
    last = projections[-1]
    terminal_nopat = (
        float(last["revenue_usd"]) * (1.0 + terminal_growth)
        * margin_pct / 100.0 * (1.0 - tax_rate_pct / 100.0)
    )
    terminal_reinvestment_rate_pct = terminal_growth_pct / roic_pct * 100.0
    terminal_fcff = terminal_nopat * (1.0 - terminal_reinvestment_rate_pct / 100.0)
    terminal_value = terminal_fcff / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1.0 + wacc) ** years)
    enterprise_value = sum(float(row["pv_fcff_usd"]) for row in projections) + pv_terminal
    projections[-1].update({
        "terminal_reinvestment_rate_pct": terminal_reinvestment_rate_pct,
        "terminal_fcff_usd": terminal_fcff,
        "terminal_value_usd": terminal_value,
        "pv_terminal_value_usd": pv_terminal,
    })
    return projections, float(enterprise_value)


def _enterprise_value(
    current: pd.Series,
    base: pd.Series,
    *,
    growth_pct: float | None = None,
    margin_pct: float | None = None,
    roic_pct: float | None = None,
    years: int,
) -> float:
    return project_dcf_v11(
        base_revenue=float(current["ttm_revenue"]),
        growth_pct=float(base["growth_pct"] if growth_pct is None else growth_pct),
        margin_pct=float(
            base["operating_margin_pct"] if margin_pct is None else margin_pct
        ),
        roic_pct=float(base["roic_pct"] if roic_pct is None else roic_pct),
        tax_rate_pct=float(base["tax_rate_pct"]),
        wacc_pct=float(base["wacc_pct"]),
        terminal_growth_pct=float(base["terminal_growth_pct"]),
        years=years,
    )[1]


def forward_dcf_v11(
    assumptions: pd.DataFrame,
    market: pd.DataFrame,
    horizon_years: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    market_lookup = market.set_index("ticker")
    projection_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for assumption in assumptions.itertuples(index=False):
        current = market_lookup.loc[assumption.ticker]
        projections, enterprise_value = project_dcf_v11(
            base_revenue=float(current["ttm_revenue"]),
            growth_pct=float(assumption.growth_pct),
            margin_pct=float(assumption.operating_margin_pct),
            roic_pct=float(assumption.roic_pct),
            tax_rate_pct=float(assumption.tax_rate_pct),
            wacc_pct=float(assumption.wacc_pct),
            terminal_growth_pct=float(assumption.terminal_growth_pct),
            years=horizon_years,
        )
        for projection in projections:
            projection_rows.append({
                "ticker": assumption.ticker,
                "subindustry": assumption.subindustry,
                "scenario": assumption.scenario,
                **projection,
            })
        common_equity_value = (
            enterprise_value
            - float(current["adjusted_total_debt_usd"])
            - float(current["noncontrolling_interest_usd"])
            - float(current["preferred_stock_usd"])
            + float(current["cash_usd"])
            + float(current["nonoperating_assets_usd"])
        )
        fair_value = common_equity_value / float(current["shares_outstanding"])
        pv_terminal = float(projections[-1]["pv_terminal_value_usd"])
        summary_rows.append({
            "ticker": assumption.ticker,
            "subindustry": assumption.subindustry,
            "scenario": assumption.scenario,
            "scenario_weight": assumption.scenario_weight,
            "scenario_weight_source": assumption.scenario_weight_source,
            "story_validation_class": assumption.story_validation_class,
            "enterprise_value_usd": enterprise_value,
            "adjusted_total_debt_usd": current["adjusted_total_debt_usd"],
            "noncontrolling_interest_usd": current["noncontrolling_interest_usd"],
            "preferred_stock_usd": current["preferred_stock_usd"],
            "cash_usd": current["cash_usd"],
            "nonoperating_assets_usd": current["nonoperating_assets_usd"],
            "common_equity_value_usd": common_equity_value,
            "shares_outstanding": current["shares_outstanding"],
            "fair_value_per_share": fair_value,
            "market_price": current["market_price"],
            "value_gap_pct": (
                fair_value / float(current["market_price"]) - 1.0
            ) * 100.0,
            "pv_explicit_fcff_usd": enterprise_value - pv_terminal,
            "pv_terminal_value_usd": pv_terminal,
            "terminal_value_share": (
                pv_terminal / enterprise_value if enterprise_value != 0 else np.nan
            ),
            "equity_reconciliation_error_usd": (
                common_equity_value
                - (
                    enterprise_value
                    - float(current["adjusted_total_debt_usd"])
                    - float(current["noncontrolling_interest_usd"])
                    - float(current["preferred_stock_usd"])
                    + float(current["cash_usd"])
                    + float(current["nonoperating_assets_usd"])
                )
            ),
            "production_eligible": False,
        })
    summary = pd.DataFrame(summary_rows)
    weighted = (
        summary.assign(
            weighted_value=lambda frame: (
                frame["fair_value_per_share"] * frame["scenario_weight"]
            )
        )
        .groupby(["ticker", "subindustry"], as_index=False)
        .agg(
            probability_weighted_fair_value=("weighted_value", "sum"),
            default_scenario_weight_sum=("scenario_weight", "sum"),
            market_price=("market_price", "first"),
        )
    )
    weighted["probability_weighted_value_gap_pct"] = (
        weighted["probability_weighted_fair_value"] / weighted["market_price"] - 1.0
    ) * 100.0
    weighted["scenario_weight_interpretation"] = (
        "DEFAULT_SCENARIO_WEIGHT_NOT_EMPIRICAL_PROBABILITY"
    )
    weighted["production_eligible"] = False
    return pd.DataFrame(projection_rows), summary, weighted


def _solve_continuous(
    evaluator: Callable[[float], float],
    target: float,
    lower: float,
    upper: float,
    reference: float,
) -> dict[str, object]:
    grid = np.linspace(lower, upper, 161)
    values = np.array([evaluator(float(value)) for value in grid], dtype=float)
    residuals = values - target
    finite = np.isfinite(residuals)
    if not finite.any():
        return {"solution": np.nan, "status": "NONFINITE_DOMAIN", "residual": np.nan}
    exact = np.flatnonzero(finite & np.isclose(residuals, 0.0, rtol=0.0, atol=max(abs(target), 1.0) * 1e-12))
    if len(exact):
        index = int(exact[np.argmin(np.abs(grid[exact] - reference))])
        return {"solution": float(grid[index]), "status": "SOLVED", "residual": float(residuals[index])}
    brackets: list[tuple[float, float]] = []
    for index in range(len(grid) - 1):
        if not (finite[index] and finite[index + 1]):
            continue
        if residuals[index] * residuals[index + 1] < 0:
            brackets.append((float(grid[index]), float(grid[index + 1])))
    if not brackets:
        nearest = int(np.nanargmin(np.abs(residuals)))
        return {
            "solution": np.nan,
            "status": "UNBRACKETED_NO_SOLUTION_IN_DOMAIN",
            "residual": float(residuals[nearest]),
            "nearest_domain_value": float(grid[nearest]),
        }
    low, high = min(brackets, key=lambda pair: abs((pair[0] + pair[1]) / 2.0 - reference))
    low_residual = evaluator(low) - target
    for _ in range(80):
        midpoint = (low + high) / 2.0
        middle_residual = evaluator(midpoint) - target
        if abs(middle_residual) <= max(abs(target), 1.0) * 1e-12:
            low = high = midpoint
            break
        if low_residual * middle_residual <= 0:
            high = midpoint
        else:
            low = midpoint
            low_residual = middle_residual
    solution = (low + high) / 2.0
    residual = evaluator(solution) - target
    return {"solution": float(solution), "status": "SOLVED", "residual": float(residual)}


def reverse_dcf_v11(
    assumptions: pd.DataFrame,
    market: pd.DataFrame,
    config: Mapping[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    years = int(config["forecast_horizon_years"])
    domains = config["reverse_domains"]
    market_lookup = market.set_index("ticker")
    base_lookup = assumptions.loc[assumptions["scenario"].eq("BASE")].set_index("ticker")
    rows: list[dict[str, object]] = []
    roundtrip_rows: list[dict[str, object]] = []
    specifications = (
        (
            "growth",
            "growth_pct",
            float(domains["growth_min_pct"]),
            float(domains["growth_max_pct"]),
        ),
        (
            "operating_margin",
            "operating_margin_pct",
            float(domains["margin_min_pct"]),
            float(domains["margin_max_pct"]),
        ),
        (
            "roic",
            "roic_pct",
            float(domains["roic_min_pct"]),
            float(domains["roic_max_pct"]),
        ),
    )
    for ticker, base in base_lookup.iterrows():
        current = market_lookup.loc[ticker]
        target = float(current["market_enterprise_value_adjusted_usd"])
        base_target = _enterprise_value(current, base, years=years)
        output: dict[str, object] = {
            "ticker": ticker,
            "subindustry": base["subindustry"],
            "market_enterprise_value_usd": target,
            "base_forward_enterprise_value_usd": base_target,
        }
        for variable, column, lower, upper in specifications:
            def evaluator(value: float, variable_name: str = variable) -> float:
                kwargs: dict[str, float] = {}
                if variable_name == "growth":
                    kwargs["growth_pct"] = value
                elif variable_name == "operating_margin":
                    kwargs["margin_pct"] = value
                else:
                    kwargs["roic_pct"] = value
                return _enterprise_value(current, base, years=years, **kwargs)

            reference = float(base[column])
            synthetic = _solve_continuous(
                evaluator, base_target, lower, upper, reference
            )
            market_solution = _solve_continuous(
                evaluator, target, lower, upper, reference
            )
            output[f"our_base_{variable}_pct"] = reference
            output[f"market_implied_{variable}_pct"] = market_solution["solution"]
            output[f"{variable}_solver_status"] = market_solution["status"]
            output[f"{variable}_solver_residual_pct_of_market_ev"] = (
                float(market_solution["residual"]) / target * 100.0
                if np.isfinite(market_solution["residual"]) and target != 0
                else np.nan
            )
            output[f"{variable}_expectations_gap_pct_points"] = (
                reference - float(market_solution["solution"])
                if np.isfinite(market_solution["solution"])
                else np.nan
            )
            roundtrip_rows.append({
                "ticker": ticker,
                "subindustry": base["subindustry"],
                "variable": variable,
                "test": "A_FORWARD_BASE_TO_REVERSE",
                "target_enterprise_value_usd": base_target,
                "solved_assumption": synthetic["solution"],
                "original_assumption": reference,
                "assumption_error": (
                    float(synthetic["solution"]) - reference
                    if np.isfinite(synthetic["solution"])
                    else np.nan
                ),
                "forward_roundtrip_error_pct": (
                    float(synthetic["residual"]) / base_target * 100.0
                    if base_target != 0 and np.isfinite(synthetic["residual"])
                    else np.nan
                ),
                "solver_status": synthetic["status"],
            })
            roundtrip_rows.append({
                "ticker": ticker,
                "subindustry": base["subindustry"],
                "variable": variable,
                "test": "B_MARKET_REVERSE_TO_FORWARD",
                "target_enterprise_value_usd": target,
                "solved_assumption": market_solution["solution"],
                "original_assumption": reference,
                "assumption_error": np.nan,
                "forward_roundtrip_error_pct": (
                    float(market_solution["residual"]) / target * 100.0
                    if target != 0 and np.isfinite(market_solution["residual"])
                    else np.nan
                ),
                "solver_status": market_solution["status"],
            })
        cap_values = []
        for cap_years in range(1, int(config["maximum_reverse_dcf_cap_years"]) + 1):
            cap_values.append((cap_years, _enterprise_value(current, base, years=cap_years)))
        cap_year, cap_value = min(cap_values, key=lambda pair: abs(pair[1] - target))
        output["our_competitive_advantage_period_years"] = years
        output["market_implied_competitive_advantage_period_years"] = cap_year
        output["cap_solver_status"] = "DISCRETE_NEAREST"
        output["cap_solver_residual_pct_of_market_ev"] = (
            (cap_value - target) / target * 100.0
        )
        output["cap_expectations_gap_years"] = years - cap_year
        output["reverse_dcf_method"] = (
            "BRACKETED_CONTINUOUS_ROOT_OR_EXPLICIT_UNBRACKETED_STATUS"
        )
        output["production_eligible"] = False
        rows.append(output)
    return pd.DataFrame(rows), pd.DataFrame(roundtrip_rows)


def run_valuation_v11(
    ttm: pd.DataFrame,
    market: pd.DataFrame,
    config: Mapping[str, object],
    anchor_growth: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    assumptions = build_scenario_assumptions_v11(
        ttm, market, config, anchor_growth
    )
    projections, scenario_values, weighted = forward_dcf_v11(
        assumptions, market, int(config["forecast_horizon_years"])
    )
    reverse, roundtrip = reverse_dcf_v11(assumptions, market, config)
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
        "reverse_dcf_roundtrip": roundtrip,
        "expectations_gap": expectations,
    }
