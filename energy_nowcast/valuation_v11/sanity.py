from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from equity_platform.sectors.energy.valuation.v11.engine import SCENARIO_VARIABLES


FINAL_COLUMNS = {
    "growth": "growth_pct",
    "operating_margin": "operating_margin_pct",
    "reinvestment_rate": "reinvestment_rate_pct",
    "roic": "roic_pct",
    "wacc": "wacc_pct",
    "terminal_growth": "terminal_growth_pct",
}


def scenario_boundary_detail(assumptions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for assumption in assumptions.itertuples(index=False):
        payload = assumption._asdict()
        for variable in SCENARIO_VARIABLES:
            hit_lower = bool(payload[f"{variable}_hit_lower_bound"])
            hit_upper = bool(payload[f"{variable}_hit_upper_bound"])
            rows.append({
                "ticker": assumption.ticker,
                "subindustry": assumption.subindustry,
                "scenario": assumption.scenario,
                "variable": variable,
                "raw_value": payload[f"{variable}_raw"],
                "clipped_value": payload[FINAL_COLUMNS[variable]],
                "lower_bound": payload[f"{variable}_lower_bound"],
                "upper_bound": payload[f"{variable}_upper_bound"],
                "hit_lower_bound": hit_lower,
                "hit_upper_bound": hit_upper,
                "boundary_hit": hit_lower or hit_upper,
                "boundary_side": (
                    "LOWER" if hit_lower else "UPPER" if hit_upper else "NONE"
                ),
            })
    detail = pd.DataFrame(rows)
    same = (
        detail.loc[detail["boundary_hit"]]
        .groupby(["ticker", "variable", "boundary_side"], as_index=False)
        .agg(hit_scenarios=("scenario", "nunique"))
    )
    same["same_boundary_all_three_scenarios"] = same["hit_scenarios"].eq(3)
    detail = detail.merge(
        same[[
            "ticker", "variable", "boundary_side",
            "same_boundary_all_three_scenarios",
        ]],
        on=["ticker", "variable", "boundary_side"],
        how="left",
    )
    detail["same_boundary_all_three_scenarios"] = detail[
        "same_boundary_all_three_scenarios"
    ].eq(True)
    return detail


def scenario_boundary_summary(
    detail: pd.DataFrame,
    config: Mapping[str, object],
) -> pd.DataFrame:
    green = float(config["sanity_gates"]["boundary_green_below_pct"])
    red = float(config["sanity_gates"]["boundary_red_above_pct"])
    summary = (
        detail.groupby(["subindustry", "variable"], as_index=False)
        .agg(
            assumptions=("boundary_hit", "size"),
            boundary_hits=("boundary_hit", "sum"),
            lower_hits=("hit_lower_bound", "sum"),
            upper_hits=("hit_upper_bound", "sum"),
            all_scenarios_same_boundary_tickers=(
                "same_boundary_all_three_scenarios", "sum"
            ),
        )
    )
    # The detail flag repeats over three scenario rows.
    summary["all_scenarios_same_boundary_tickers"] = (
        summary["all_scenarios_same_boundary_tickers"] / 3
    ).astype(int)
    summary["boundary_hit_pct"] = (
        summary["boundary_hits"] / summary["assumptions"] * 100.0
    )
    summary["boundary_status"] = np.select(
        [
            summary["boundary_hit_pct"].gt(red)
            | summary["all_scenarios_same_boundary_tickers"].gt(0),
            summary["boundary_hit_pct"].ge(green),
        ],
        ["RED_FREEZE_PROHIBITED", "YELLOW_INVESTIGATE"],
        default="GREEN",
    )
    summary["freeze_eligible"] = summary["boundary_status"].ne(
        "RED_FREEZE_PROHIBITED"
    )
    return summary


def parent_boundary_audit(
    assumptions: pd.DataFrame,
    parent_config: Mapping[str, object],
    audit_config: Mapping[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    for row in assumptions.itertuples(index=False):
        guardrail = parent_config["guardrails"][row.subindustry]
        bounds = {
            "growth": (
                guardrail["growth_min_pct"], guardrail["growth_max_pct"]
            ),
            "operating_margin": (
                guardrail["margin_min_pct"], guardrail["margin_max_pct"]
            ),
            "reinvestment_rate": (-50.0, 150.0),
            "roic": (guardrail["roic_min_pct"], guardrail["roic_max_pct"]),
            "wacc": (3.0, 20.0),
            "terminal_growth": (0.0, parent_config["terminal_growth_cap_pct"]),
        }
        for variable, (lower, upper) in bounds.items():
            value = float(getattr(row, FINAL_COLUMNS[variable]))
            hit_lower = bool(np.isclose(value, float(lower)))
            hit_upper = bool(np.isclose(value, float(upper)))
            rows.append({
                "ticker": row.ticker,
                "subindustry": row.subindustry,
                "scenario": row.scenario,
                "variable": variable,
                "raw_value": np.nan,
                "clipped_value": value,
                "lower_bound": float(lower),
                "upper_bound": float(upper),
                "hit_lower_bound": hit_lower,
                "hit_upper_bound": hit_upper,
                "boundary_hit": hit_lower or hit_upper,
                "boundary_side": (
                    "LOWER" if hit_lower else "UPPER" if hit_upper else "NONE"
                ),
            })
    detail = pd.DataFrame(rows)
    same = (
        detail.loc[detail["boundary_hit"]]
        .groupby(["ticker", "variable", "boundary_side"], as_index=False)
        .agg(hit_scenarios=("scenario", "nunique"))
    )
    same["same_boundary_all_three_scenarios"] = same["hit_scenarios"].eq(3)
    detail = detail.merge(
        same[[
            "ticker", "variable", "boundary_side",
            "same_boundary_all_three_scenarios",
        ]],
        on=["ticker", "variable", "boundary_side"],
        how="left",
    )
    detail["same_boundary_all_three_scenarios"] = detail[
        "same_boundary_all_three_scenarios"
    ].eq(True)
    return detail, scenario_boundary_summary(detail, audit_config)


def _terminal_audit(
    scenario_values: pd.DataFrame,
    config: Mapping[str, object],
) -> pd.DataFrame:
    warning = float(config["sanity_gates"]["terminal_warning_share_pct"])
    high = float(config["sanity_gates"]["terminal_high_share_pct"])
    result = scenario_values[[
        "ticker", "subindustry", "scenario", "enterprise_value_usd",
        "pv_explicit_fcff_usd", "pv_terminal_value_usd", "terminal_value_share",
    ]].copy()
    result["terminal_value_share_pct"] = result["terminal_value_share"] * 100.0
    unstable = (
        result["enterprise_value_usd"].le(0)
        | result["terminal_value_share_pct"].lt(0)
        | result["terminal_value_share_pct"].gt(100)
    )
    result["terminal_dependence_status"] = np.select(
        [
            unstable,
            result["terminal_value_share_pct"].gt(high),
            result["terminal_value_share_pct"].ge(warning),
        ],
        [
            "UNSTABLE_OR_NONPOSITIVE_ENTERPRISE_VALUE",
            "HIGH_TERMINAL_DEPENDENCE",
            "TERMINAL_DEPENDENCE_WARNING",
        ],
        default="NORMAL",
    )
    return result


def _terminal_summary(terminal: pd.DataFrame) -> pd.DataFrame:
    result = terminal.copy()
    result["high_terminal_dependence"] = result[
        "terminal_dependence_status"
    ].eq("HIGH_TERMINAL_DEPENDENCE")
    result["unstable_terminal_value"] = result[
        "terminal_dependence_status"
    ].eq("UNSTABLE_OR_NONPOSITIVE_ENTERPRISE_VALUE")
    return (
        result.groupby(["subindustry", "scenario"], as_index=False)
        .agg(
            tickers=("ticker", "nunique"),
            median_terminal_value_share_pct=("terminal_value_share_pct", "median"),
            high_terminal_dependence_tickers=("high_terminal_dependence", "sum"),
            unstable_terminal_value_tickers=("unstable_terminal_value", "sum"),
        )
    )


def _fcff_sanity(
    ttm: pd.DataFrame,
    projections: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    latest = (
        ttm.loc[ttm["ttm_complete"]]
        .sort_values(["ticker", "quarter_ordinal"])
        .groupby("ticker", as_index=False, group_keys=False)
        .tail(1)
        .copy()
    )
    latest["after_tax_interest_usd"] = (
        latest["ttm_interest_expense_usd"]
        * (1.0 - latest["effective_tax_rate"])
    )
    latest["cash_conversion_adjustment_usd"] = (
        latest["ttm_cfo_usd"] + latest["after_tax_interest_usd"]
        - latest["ttm_nopat_usd"]
    )
    latest["fcff_less_nopat_usd"] = (
        latest["ttm_fcff_usd"] - latest["ttm_nopat_usd"]
    )
    latest["fcff_less_operating_margin_pct_points"] = (
        latest["fcff_margin_pct"] - latest["operating_margin_pct"]
    )
    latest["fcff_margin_above_operating_margin"] = latest[
        "fcff_less_operating_margin_pct_points"
    ].gt(0)
    latest["cash_capex_sign_status"] = np.where(
        latest["ttm_cash_capex_usd"].ge(0), "PASS_NONNEGATIVE", "FAIL_NEGATIVE_CAPEX"
    )
    historical = latest[[
        "ticker", "subindustry", "quarter", "operating_margin_pct",
        "fcff_margin_pct", "fcff_less_operating_margin_pct_points",
        "fcff_margin_above_operating_margin", "ttm_nopat_usd", "ttm_cfo_usd",
        "after_tax_interest_usd", "cash_conversion_adjustment_usd",
        "ttm_cash_capex_usd", "fcff_less_nopat_usd", "ttm_fcff_usd",
        "cash_capex_sign_status", "incremental_roic_pct",
    ]].copy()
    forward = projections[[
        "ticker", "subindustry", "scenario", "forecast_year", "growth_pct",
        "forecast_normalized_roic_pct", "reinvestment_rate_pct", "nopat_usd",
        "reinvestment_usd", "fcff_usd", "fundamental_growth_reconstructed_pct",
        "reinvestment_plausibility_status",
    ]].copy()
    forward["fcff_identity_error_usd"] = (
        forward["nopat_usd"] - forward["reinvestment_usd"] - forward["fcff_usd"]
    )
    forward["growth_reinvestment_roic_gap_pct_points"] = (
        forward["growth_pct"] - forward["fundamental_growth_reconstructed_pct"]
    )
    return historical, forward


def _historical_fcff_summary(historical: pd.DataFrame) -> pd.DataFrame:
    return (
        historical.groupby("subindustry", as_index=False)
        .agg(
            tickers=("ticker", "nunique"),
            median_operating_margin_pct=("operating_margin_pct", "median"),
            median_fcff_margin_pct=("fcff_margin_pct", "median"),
            median_fcff_less_operating_margin_pct_points=(
                "fcff_less_operating_margin_pct_points", "median"
            ),
            median_cash_conversion_adjustment_usd=(
                "cash_conversion_adjustment_usd", "median"
            ),
            median_cash_capex_usd=("ttm_cash_capex_usd", "median"),
            fcff_margin_above_operating_margin_tickers=(
                "fcff_margin_above_operating_margin", "sum"
            ),
        )
    )


def _reverse_roundtrip_summary(roundtrip: pd.DataFrame) -> pd.DataFrame:
    detail = roundtrip.copy()
    detail["solved"] = detail["solver_status"].eq("SOLVED")
    detail["unbracketed"] = detail["solver_status"].eq(
        "UNBRACKETED_NO_SOLUTION_IN_DOMAIN"
    )
    detail["solved_assumption_error"] = detail["assumption_error"].where(
        detail["solved"]
    )
    detail["solved_forward_roundtrip_error_pct"] = detail[
        "forward_roundtrip_error_pct"
    ].where(detail["solved"])

    def absolute_stat(values: pd.Series, statistic: str) -> float:
        finite = values.dropna().abs()
        if finite.empty:
            return np.nan
        return float(getattr(finite, statistic)())

    return (
        detail.groupby(["test", "subindustry", "variable"], as_index=False)
        .agg(
            tickers=("ticker", "nunique"),
            solved_tickers=("solved", "sum"),
            unbracketed_tickers=("unbracketed", "sum"),
            solved_median_abs_assumption_error=(
                "solved_assumption_error",
                lambda values: absolute_stat(values, "median"),
            ),
            solved_maximum_abs_assumption_error=(
                "solved_assumption_error",
                lambda values: absolute_stat(values, "max"),
            ),
            solved_median_abs_forward_roundtrip_error_pct=(
                "solved_forward_roundtrip_error_pct",
                lambda values: absolute_stat(values, "median"),
            ),
            solved_maximum_abs_forward_roundtrip_error_pct=(
                "solved_forward_roundtrip_error_pct",
                lambda values: absolute_stat(values, "max"),
            ),
        )
    )


def _expectations_outliers(
    weighted: pd.DataFrame,
    config: Mapping[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    threshold = float(config["sanity_gates"]["expectations_gap_outlier_abs_pct"])
    skew = float(config["sanity_gates"]["subindustry_value_skew_abs_pct"])
    detail = weighted.copy()
    detail["expectations_gap_outlier"] = detail[
        "probability_weighted_value_gap_pct"
    ].abs().gt(threshold)
    detail["expectations_gap_status"] = np.where(
        detail["expectations_gap_outlier"], "OUTLIER_REQUIRES_REVIEW", "WITHIN_REVIEW_RANGE"
    )
    summary = (
        detail.groupby("subindustry", as_index=False)
        .agg(
            tickers=("ticker", "nunique"),
            median_probability_weighted_value_gap_pct=(
                "probability_weighted_value_gap_pct", "median"
            ),
            outlier_tickers=("expectations_gap_outlier", "sum"),
        )
    )
    summary["systematic_sector_skew_flag"] = summary[
        "median_probability_weighted_value_gap_pct"
    ].abs().gt(skew)
    summary["systematic_skew_status"] = np.where(
        summary["systematic_sector_skew_flag"],
        "SYSTEMATIC_SKEW_REQUIRES_REVIEW",
        "WITHIN_REVIEW_RANGE",
    )
    return detail, summary


def run_sanity_audit(
    *,
    ttm: pd.DataFrame,
    adjusted_market: pd.DataFrame,
    assumptions: pd.DataFrame,
    projections: pd.DataFrame,
    scenario_values: pd.DataFrame,
    weighted: pd.DataFrame,
    reverse: pd.DataFrame,
    roundtrip: pd.DataFrame,
    config: Mapping[str, object],
) -> dict[str, pd.DataFrame]:
    boundary_detail = scenario_boundary_detail(assumptions)
    boundary_summary = scenario_boundary_summary(boundary_detail, config)
    terminal = _terminal_audit(scenario_values, config)
    terminal_summary = _terminal_summary(terminal)
    historical_fcff, forward_fcff = _fcff_sanity(ttm, projections)
    historical_fcff_summary = _historical_fcff_summary(historical_fcff)
    reverse_roundtrip_summary = _reverse_roundtrip_summary(roundtrip)
    outliers, sector_skew = _expectations_outliers(weighted, config)
    gates = config["sanity_gates"]
    test_a = roundtrip.loc[roundtrip["test"].eq("A_FORWARD_BASE_TO_REVERSE")]
    test_b_solved = roundtrip.loc[
        roundtrip["test"].eq("B_MARKET_REVERSE_TO_FORWARD")
        & roundtrip["solver_status"].eq("SOLVED")
    ]
    ev_error_pct = (
        adjusted_market["ev_equity_reconciliation_error_usd"].abs()
        / adjusted_market["market_cap_usd"].abs().clip(lower=1.0) * 100.0
    )
    cap_error_pct = (
        adjusted_market["market_cap_reconciliation_error_usd"].abs()
        / adjusted_market["market_cap_usd"].abs().clip(lower=1.0) * 100.0
    )
    checks = {
        "scenario_boundary_saturation_gate": boundary_summary["freeze_eligible"].all(),
        "no_ticker_has_all_scenarios_on_same_boundary": (
            not boundary_detail["same_boundary_all_three_scenarios"].any()
        ),
        "reverse_dcf_roundtrip_test_a_solved": test_a["solver_status"].eq("SOLVED").all(),
        "reverse_dcf_roundtrip_test_a_value": test_a[
            "forward_roundtrip_error_pct"
        ].abs().le(float(gates["roundtrip_value_tolerance_pct"])).all(),
        "reverse_dcf_roundtrip_test_a_assumption": test_a[
            "assumption_error"
        ].abs().le(float(gates["roundtrip_assumption_tolerance"])).all(),
        "reverse_dcf_roundtrip_test_b_solved_values_reprice_market": (
            len(test_b_solved) > 0
            and test_b_solved["forward_roundtrip_error_pct"].abs().le(
                float(gates["roundtrip_value_tolerance_pct"])
            ).all()
        ),
        "unbracketed_reverse_dcf_is_explicit_not_fake_boundary_solution": (
            reverse.filter(regex="_solver_status$")
            .apply(lambda column: column.isin([
                "SOLVED", "UNBRACKETED_NO_SOLUTION_IN_DOMAIN", "DISCRETE_NEAREST"
            ]).all())
            .all()
        ),
        "ev_to_common_equity_reconciliation": ev_error_pct.le(
            float(gates["ev_equity_reconciliation_tolerance_pct"])
        ).all(),
        "market_price_times_shares_reconciliation": cap_error_pct.le(
            float(gates["ev_equity_reconciliation_tolerance_pct"])
        ).all(),
        "forward_fcff_identity": forward_fcff["fcff_identity_error_usd"].abs().le(
            float(gates["forward_fcff_identity_tolerance_usd"])
        ).all(),
        "growth_reinvestment_roic_consistency": forward_fcff[
            "growth_reinvestment_roic_gap_pct_points"
        ].abs().le(float(gates["growth_reinvestment_roic_tolerance_pct_points"])).all(),
        "scenario_weights_are_labeled_defaults": assumptions[
            "scenario_weight_source"
        ].eq("DEFAULT_SCENARIO_WEIGHT_NOT_EMPIRICAL_PROBABILITY").all(),
        "scenario_weights_sum_to_one": np.allclose(
            assumptions.groupby("ticker")["scenario_weight"].sum(), 1.0
        ),
        "historical_and_forecast_roic_are_distinctly_labeled": {
            "historical_incremental_roic_pct", "forecast_normalized_roic_pct"
        }.issubset(assumptions.columns),
        "terminal_dependence_is_computed_and_flagged": (
            terminal["terminal_value_share_pct"].notna().all()
            and terminal["terminal_dependence_status"].notna().all()
        ),
        "expectations_gap_outliers_are_flagged": (
            outliers["expectations_gap_status"].notna().all()
            and sector_skew["systematic_skew_status"].notna().all()
        ),
        "fixed_ratio_reverse_calculation_absent": (
            not bool(config["fixed_ratio_reverse_calculation_allowed"])
            and not assumptions["fixed_ratio_used"].any()
        ),
        "production_live_gate_not_met": int(config["live_matched_observations"])
        < int(config["production_live_minimum"]),
    }
    requirement = pd.DataFrame([
        {"requirement": name, "passed": bool(passed)}
        for name, passed in checks.items()
    ])
    code_checks = [
        name for name in checks
        if name not in {"production_live_gate_not_met"}
    ]
    code_complete = all(checks[name] for name in code_checks)
    research_complete = code_complete
    status = pd.DataFrame([
        {
            "status_dimension": "V1_1_CODE",
            "status": "COMPLETE" if code_complete else "RC_AUDIT_FAILED",
            "passed": code_complete,
        },
        {
            "status_dimension": "V1_1_RESEARCH",
            "status": "COMPLETE" if research_complete else "RC_AUDIT_FAILED",
            "passed": research_complete,
        },
        {
            "status_dimension": "V1_1_PRODUCTION",
            "status": "NOT_PROMOTED_LIVE_0_OF_20",
            "passed": False,
        },
    ])
    return {
        "scenario_boundary_detail": boundary_detail,
        "scenario_boundary_summary": boundary_summary,
        "terminal_value_audit": terminal,
        "terminal_value_summary": terminal_summary,
        "historical_fcff_sanity": historical_fcff,
        "historical_fcff_subindustry_summary": historical_fcff_summary,
        "forward_fcff_sanity": forward_fcff,
        "reverse_dcf_roundtrip_summary": reverse_roundtrip_summary,
        "expectations_gap_outliers": outliers,
        "subindustry_expectations_skew": sector_skew,
        "v1_1_requirement_audit": requirement,
        "v1_1_completion_status": status,
    }
