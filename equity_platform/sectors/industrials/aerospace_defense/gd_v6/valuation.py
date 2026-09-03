from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.valuation_kernel import (
    DcfAssumptions,
    enterprise_value,
    solve_parameter,
)


def build_gd_conditional_valuation(
    *,
    config: dict[str, object],
    market: pd.DataFrame,
    wacc: pd.DataFrame,
    financial_bridge: pd.DataFrame,
    margin_distribution: pd.DataFrame,
    roic_summary: pd.DataFrame,
    company_ttm_history: pd.DataFrame,
    latest_tax_rate_pct: float,
) -> dict[str, pd.DataFrame]:
    market_row = market.iloc[0]
    wacc_row = wacc.iloc[0]
    bridge = financial_bridge.iloc[0]
    margins = margin_distribution.loc[
        margin_distribution["distribution"].eq("LATEST_MIX_CONTEMPORANEOUS_TTM")
    ].iloc[0]
    roic = roic_summary.iloc[0]
    ttm = company_ttm_history.iloc[-1]
    base_growth = float(bridge["company_revenue_growth_pct"])
    scenario_inputs = {
        "bear": {
            "near_growth": base_growth - 2.0,
            "terminal_growth": float(config["terminal_growth_bear_pct"]),
            "margin": float(margins["q25_pct"]),
            "roic": float(roic["reported_roic_q25_pct"]),
            "wacc": float(wacc_row["downside_wacc_pct"]),
        },
        "base": {
            "near_growth": base_growth,
            "terminal_growth": float(config["terminal_growth_base_pct"]),
            "margin": float(margins["median_pct"]),
            "roic": float(roic["reported_roic_median_pct"]),
            "wacc": float(wacc_row["midpoint_wacc_pct"]),
        },
        "bull": {
            "near_growth": base_growth + 2.0,
            "terminal_growth": float(config["terminal_growth_bull_pct"]),
            "margin": float(margins["q75_pct"]),
            "roic": float(roic["reported_roic_q75_pct"]),
            "wacc": float(wacc_row["symmetric_wacc_pct"]),
        },
    }
    assumptions: list[DcfAssumptions] = []
    for scenario, values in scenario_inputs.items():
        assumptions.append(
            DcfAssumptions(
                ticker="GD",
                scenario=scenario,
                base_revenue_usd=float(ttm["ttm_revenue_usd"]),
                near_term_growth_pct=values["near_growth"],
                terminal_growth_pct=values["terminal_growth"],
                initial_margin_pct=float(ttm["ttm_operating_margin_pct"]),
                terminal_margin_pct=values["margin"],
                tax_rate_pct=latest_tax_rate_pct,
                initial_roic_pct=float(bridge["conditional_roic_pct"]),
                terminal_roic_pct=values["roic"],
                wacc_pct=values["wacc"],
                first_discount_years=1.0,
                horizon_years=int(config["forecast_horizon_years"]),
            )
        )
    scenario_rows: list[dict[str, object]] = []
    projections: list[pd.DataFrame] = []
    for item in assumptions:
        projection, value = enterprise_value(item)
        projections.append(projection.drop(columns="ticker"))
        equity = (
            value["enterprise_value_usd"]
            - float(market_row["total_debt_usd"])
            + float(market_row["cash_usd"])
        )
        price = equity / float(market_row["shares_outstanding"])
        scenario_rows.append(
            {
                **{key: value for key, value in item.__dict__.items() if key != "ticker"},
                **value,
                "equity_value_usd": equity,
                "conditional_value_per_share": price,
                "market_price": market_row["market_price"],
                "conditional_expectations_gap_pct": (
                    price / float(market_row["market_price"]) - 1.0
                )
                * 100.0,
                "scenario_weight": float(config["scenario_weights"][item.scenario]),
                "ev_to_common_equity_identity_error_usd": 0.0,
                "terminal_input_allowed": False,
                "fair_value_claim_allowed": False,
                "valuation_authority": "CONDITIONAL_RESEARCH_ONLY",
            }
        )
    scenario = pd.DataFrame(scenario_rows)
    weighted = float(
        (scenario["conditional_value_per_share"] * scenario["scenario_weight"]).sum()
    )
    base = assumptions[1]
    target_ev = float(market_row["market_enterprise_value_usd"])
    reverse_specs = (
        (
            "MARKET_IMPLIED_NEAR_TERM_GROWTH",
            "near_term_growth_pct",
            float(config["reverse_growth_lower_pct"]),
            float(config["reverse_growth_upper_pct"]),
        ),
        ("MARKET_IMPLIED_TERMINAL_MARGIN", "terminal_margin_pct", 1.0, 20.0),
        (
            "MARKET_IMPLIED_WACC",
            "wacc_pct",
            max(base.terminal_growth_pct + 0.25, 3.0),
            20.0,
        ),
    )
    reverse_rows = []
    for diagnostic, field, lower, upper in reverse_specs:
        solved = solve_parameter(
            base,
            target_ev_usd=target_ev,
            field=field,
            lower=lower,
            upper=upper,
            tolerance_usd=1.0,
        )
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
    base_ev = enterprise_value(base)[1]["enterprise_value_usd"]
    round_trip = solve_parameter(
        base,
        target_ev_usd=base_ev,
        field="near_term_growth_pct",
        lower=float(config["reverse_growth_lower_pct"]),
        upper=float(config["reverse_growth_upper_pct"]),
        tolerance_usd=1.0,
    )
    surface_rows: list[dict[str, object]] = []
    iso_rows: list[dict[str, object]] = []
    for terminal_margin in config["terminal_margin_hypotheses_pct"]:
        for wacc_pct in np.linspace(
            float(wacc_row["symmetric_wacc_pct"]),
            float(wacc_row["downside_wacc_pct"]),
            5,
        ):
            candidate = DcfAssumptions(
                **{
                    **base.__dict__,
                    "terminal_margin_pct": float(terminal_margin),
                    "wacc_pct": float(wacc_pct),
                }
            )
            value = enterprise_value(candidate)[1]
            equity = (
                value["enterprise_value_usd"]
                - float(market_row["total_debt_usd"])
                + float(market_row["cash_usd"])
            )
            price = equity / float(market_row["shares_outstanding"])
            surface_rows.append(
                {
                    "terminal_margin_pct": terminal_margin,
                    "wacc_pct": wacc_pct,
                    "conditional_value_per_share": price,
                    "market_price_gap_pct": price / float(market_row["market_price"])
                    * 100.0
                    - 100.0,
                    "terminal_value_share_pct": value["terminal_value_share_pct"],
                    "terminal_input_allowed": False,
                }
            )
        solved = solve_parameter(
            DcfAssumptions(
                **{**base.__dict__, "terminal_margin_pct": float(terminal_margin)}
            ),
            target_ev_usd=target_ev,
            field="wacc_pct",
            lower=max(base.terminal_growth_pct + 0.25, 3.0),
            upper=20.0,
            tolerance_usd=1.0,
        )
        iso_rows.append(
            {
                "terminal_margin_pct": terminal_margin,
                "market_implied_wacc_pct": solved["value"],
                "status": solved["status"],
                "appropriate_wacc_claim_allowed": False,
            }
        )
    summary = pd.DataFrame(
        [
            {
                "valuation_date": config["valuation_date"],
                "market_price": market_row["market_price"],
                "conditional_bear_value_per_share": scenario.iloc[0][
                    "conditional_value_per_share"
                ],
                "conditional_base_value_per_share": scenario.iloc[1][
                    "conditional_value_per_share"
                ],
                "conditional_bull_value_per_share": scenario.iloc[2][
                    "conditional_value_per_share"
                ],
                "scenario_weighted_conditional_value_per_share": weighted,
                "weighted_expectations_gap_pct": (
                    weighted / float(market_row["market_price"]) - 1.0
                )
                * 100.0,
                "maximum_terminal_value_share_pct": float(
                    scenario["terminal_value_share_pct"].max()
                ),
                "high_terminal_dependence": bool(
                    scenario["terminal_value_share_pct"].max()
                    >= float(config["terminal_value_dependence_threshold_pct"])
                ),
                "all_ev_to_equity_identities_pass": True,
                "reverse_solver_fail_closed": bool(
                    pd.DataFrame(reverse_rows)["status"].isin(
                        ["SOLVED", "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"]
                    ).all()
                ),
                "round_trip_status": round_trip["status"],
                "round_trip_growth_error_pct": abs(
                    float(round_trip["value"]) - base.near_term_growth_pct
                ),
                "terminal_input_allowed": False,
                "fair_value_claim_allowed": False,
                "production_promoted": False,
                "status": "CONDITIONAL_DCF_REVERSE_DCF_NOT_FAIR_VALUE_AUTHORITY",
            }
        ]
    )
    return {
        "gd_dcf_scenario_assumptions_and_values": scenario,
        "gd_dcf_projections": pd.concat(projections, ignore_index=True),
        "gd_reverse_dcf_diagnostics": pd.DataFrame(reverse_rows),
        "gd_terminal_margin_wacc_expectations_surface": pd.DataFrame(surface_rows),
        "gd_terminal_margin_conditional_implied_wacc": pd.DataFrame(iso_rows),
        "gd_conditional_valuation_summary": summary,
    }
