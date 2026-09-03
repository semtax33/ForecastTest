from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.metrics import absolute_percentage_error, mean_absolute_scaled_error
from equity_platform.valuation import DcfAssumptions, enterprise_value, solve_implied_growth


def _fit_ols(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    matrix = np.column_stack([np.ones(len(x)), x.to_numpy(dtype=float)])
    intercept, slope = np.linalg.lstsq(matrix, y.to_numpy(dtype=float), rcond=None)[0]
    return float(intercept), float(slope)


def build_anchor_validation(
    financials: pd.DataFrame,
    minimum_training_observations: int,
    minimum_validation_observations: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = financials.loc[financials["financial_complete"]].copy()
    frame = frame.sort_values("fiscal_year").reset_index(drop=True)
    frame["anchor_signal_pct"] = frame["backlog_growth_pct"].shift(1)
    frame["naive_revenue_forecast_usd"] = frame["revenue_usd"].shift(1)
    frame["anchor_revenue_forecast_usd"] = np.nan
    frame["training_observations"] = 0
    for index in frame.index:
        training = frame.loc[: index - 1].dropna(
            subset=["anchor_signal_pct", "revenue_growth_pct"]
        )
        signal = frame.at[index, "anchor_signal_pct"]
        prior_revenue = frame.at[index - 1, "revenue_usd"] if index > 0 else np.nan
        if len(training) < minimum_training_observations or not np.isfinite(signal):
            continue
        intercept, slope = _fit_ols(
            training["anchor_signal_pct"], training["revenue_growth_pct"]
        )
        predicted_growth = intercept + slope * float(signal)
        frame.at[index, "anchor_revenue_forecast_usd"] = prior_revenue * (
            1.0 + predicted_growth / 100.0
        )
        frame.at[index, "training_observations"] = len(training)
    validation = frame.loc[
        frame["anchor_revenue_forecast_usd"].notna()
        & frame["naive_revenue_forecast_usd"].notna()
    ].copy()
    validation["anchor_revenue_ape_pct"] = absolute_percentage_error(
        validation["revenue_usd"], validation["anchor_revenue_forecast_usd"]
    )
    validation["naive_revenue_ape_pct"] = absolute_percentage_error(
        validation["revenue_usd"], validation["naive_revenue_forecast_usd"]
    )
    mase = mean_absolute_scaled_error(
        validation["revenue_usd"],
        validation["anchor_revenue_forecast_usd"],
        validation["naive_revenue_forecast_usd"],
    )
    promoted = bool(
        len(validation) >= minimum_validation_observations
        and np.isfinite(mase)
        and mase < 1.0
    )
    gate = pd.DataFrame(
        [
            {
                "anchor": "ORDERS_BACKLOG_SHIPMENTS",
                "available_backlog_years": int(frame["backlog_usd"].notna().sum()),
                "walk_forward_validation_observations": len(validation),
                "minimum_validation_observations": minimum_validation_observations,
                "anchor_revenue_mase_vs_prior_year_naive": mase,
                "anchor_promoted": promoted,
                "selected_forecast_route": (
                    "BACKLOG_OLS_ANCHOR"
                    if promoted
                    else "PRIOR_YEAR_REVENUE_NAIVE_BASELINE"
                ),
                "promotion_reason": (
                    "PROMOTED_STRICT_MASE_IMPROVEMENT"
                    if promoted
                    else "LOCKED_INSUFFICIENT_OUT_OF_SAMPLE_EVIDENCE_OR_NO_MASE_IMPROVEMENT"
                ),
            }
        ]
    )
    return validation, gate


def build_industrials_research_baseline(
    *,
    financials: pd.DataFrame,
    market: pd.DataFrame,
    minimum_training_observations: int,
    minimum_validation_observations: int,
    bridge_history_years: int,
    terminal_growth_pct: float,
    horizon_years: int,
) -> dict[str, pd.DataFrame]:
    validation, anchor_gate = build_anchor_validation(
        financials,
        minimum_training_observations,
        minimum_validation_observations,
    )
    history = financials.loc[financials["financial_complete"]].sort_values(
        "fiscal_year"
    )
    latest = history.iloc[-1]
    training = history.assign(
        anchor_signal_pct=history["backlog_growth_pct"].shift(1)
    ).dropna(subset=["anchor_signal_pct", "revenue_growth_pct"])
    promoted = bool(anchor_gate.iloc[0]["anchor_promoted"])
    if promoted and len(training) >= minimum_training_observations:
        intercept, slope = _fit_ols(
            training["anchor_signal_pct"], training["revenue_growth_pct"]
        )
        growth_pct = intercept + slope * float(latest["backlog_growth_pct"])
    else:
        growth_pct = 0.0
    window = history.tail(bridge_history_years)
    margin_pct = float(window["operating_margin_pct"].median())
    roic_pct = float(window["roic_pct"].median())
    tax_rate_pct = float(window["effective_tax_rate"].median() * 100.0)
    forecast_revenue = float(latest["revenue_usd"]) * (1.0 + growth_pct / 100.0)
    forecast_ebit = forecast_revenue * margin_pct / 100.0
    forecast_nopat = forecast_ebit * (1.0 - tax_rate_pct / 100.0)
    forecast_reinvestment = forecast_nopat * growth_pct / roic_pct
    forecast_fcff = forecast_nopat - forecast_reinvestment
    current_market = market.iloc[0]
    assumptions = DcfAssumptions(
        base_revenue_usd=float(latest["revenue_usd"]),
        near_term_growth_pct=growth_pct,
        operating_margin_pct=margin_pct,
        tax_rate_pct=tax_rate_pct,
        roic_pct=roic_pct,
        wacc_pct=float(current_market["wacc_pct"]),
        terminal_growth_pct=terminal_growth_pct,
        horizon_years=horizon_years,
    )
    projections, enterprise = enterprise_value(assumptions)
    equity = (
        enterprise
        - float(current_market["total_debt_usd"])
        + float(current_market["cash_usd"])
    )
    fair_value = equity / float(current_market["shares_outstanding"])
    reverse = solve_implied_growth(
        assumptions,
        float(current_market["market_enterprise_value_usd"]),
    )
    forecast = pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "forecast_as_of_financial_year": int(latest["fiscal_year"]),
                "target_fiscal_year": int(latest["fiscal_year"]) + 1,
                "primary_anchor": "ORDERS_BACKLOG_SHIPMENTS",
                "selected_forecast_route": anchor_gate.iloc[0]["selected_forecast_route"],
                "revenue_growth_forecast_pct": growth_pct,
                "revenue_forecast_usd": forecast_revenue,
                "operating_margin_forecast_pct": margin_pct,
                "ebit_forecast_usd": forecast_ebit,
                "nopat_forecast_usd": forecast_nopat,
                "roic_forecast_pct": roic_pct,
                "reinvestment_forecast_usd": forecast_reinvestment,
                "fcff_forecast_usd": forecast_fcff,
                "wacc_pct": assumptions.wacc_pct,
                "terminal_growth_pct": terminal_growth_pct,
                "forward_dcf_enterprise_value_usd": enterprise,
                "forward_dcf_fair_value_per_share": fair_value,
                "market_price": current_market["market_price"],
                "expectations_gap_pct": fair_value / current_market["market_price"] * 100.0 - 100.0,
                "reverse_dcf_status": reverse["status"],
                "market_implied_near_term_growth_pct": reverse["implied_growth_pct"],
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    projection_frame = pd.DataFrame(projections)
    projection_frame.insert(0, "ticker", "CAT")
    dcf_identity_error = abs(float(projection_frame.iloc[0]["revenue_usd"]) - forecast_revenue)
    gate = anchor_gate.assign(
        annual_financial_history_years=int(history["financial_complete"].sum()),
        financial_bridge_complete=bool(len(history) >= 8),
        year_one_revenue_dcf_identity_error_usd=dcf_identity_error,
        year_one_revenue_dcf_identity_pass=dcf_identity_error <= 1.0,
        reverse_dcf_fail_closed=reverse["status"] in (
            "SOLVED",
            "UNBRACKETED_NO_SOLUTION_IN_DOMAIN",
        ),
        industrials_v1_research_complete=bool(
            len(history) >= 8 and dcf_identity_error <= 1.0
        ),
        normal_roic_claimed=False,
        terminal_input_allowed=False,
        production_promoted=False,
    )
    return {
        "anchor_validation": validation,
        "anchor_gate": anchor_gate,
        "forecast_financial_bridge": forecast,
        "dcf_projections": projection_frame,
        "industrials_v1_gate": gate,
    }
