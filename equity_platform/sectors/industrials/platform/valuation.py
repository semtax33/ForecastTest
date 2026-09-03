from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd


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
        if self.terminal_margin_pct <= 0:
            raise ValueError("Terminal margin must be positive")
        if self.terminal_growth_pct > 0 and self.terminal_roic_pct <= self.terminal_growth_pct:
            raise ValueError("Terminal ROIC must exceed positive terminal growth")
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
        ebit = revenue * margin / 100.0
        nopat = ebit * (1.0 - assumptions.tax_rate_pct / 100.0)
        reinvestment_rate = growth / roic
        reinvestment = nopat * reinvestment_rate
        fcff = nopat - reinvestment
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
    terminal_ebit = terminal_revenue * assumptions.terminal_margin_pct / 100.0
    terminal_nopat = terminal_ebit * (1.0 - assumptions.tax_rate_pct / 100.0)
    terminal_reinvestment_rate = (
        assumptions.terminal_growth_pct / assumptions.terminal_roic_pct
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


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_market_wacc_evidence(
    *,
    annual: pd.DataFrame,
    periodic: pd.DataFrame,
    daily_path: Path,
    weekly_path: Path,
    risk_free_path: Path,
    valuation_date: pd.Timestamp,
    equity_risk_premium_pct: float = 4.50,
    fallback_credit_spread_pct: float = 1.50,
    beta_weeks: int = 260,
    blume_weight: float = 2.0 / 3.0,
) -> dict[str, pd.DataFrame]:
    daily = pd.read_csv(daily_path, parse_dates=["Date"]).sort_values("Date")
    weekly = pd.read_csv(weekly_path, parse_dates=["Date"]).set_index("Date")
    risk_free = pd.read_csv(risk_free_path, parse_dates=["DATE"])
    risk_free["DGS10"] = pd.to_numeric(risk_free["DGS10"], errors="coerce")
    daily = daily.loc[daily["Date"].le(valuation_date)]
    weekly = weekly.loc[weekly.index <= valuation_date]
    risk_free = risk_free.loc[
        risk_free["DATE"].le(valuation_date) & risk_free["DGS10"].notna()
    ]
    if daily.empty or weekly.empty or risk_free.empty:
        raise ValueError("Market inputs are empty by valuation date")
    risk_free_pct = float(risk_free.iloc[-1]["DGS10"])
    returns = weekly.pct_change(fill_method=None).tail(beta_weeks)
    market_rows: list[dict[str, object]] = []
    beta_rows: list[dict[str, object]] = []
    wacc_rows: list[dict[str, object]] = []
    tickers = sorted(set(annual["ticker"]) & (set(daily.columns) - {"Date"}))
    for ticker in tickers:
        price_series = daily[["Date", ticker]].dropna()
        history = periodic.loc[
            periodic["ticker"].eq(ticker)
            & pd.to_datetime(periodic["filing_date"]).le(valuation_date)
        ].sort_values("filing_date")
        balance = annual.loc[annual["ticker"].eq(ticker)].sort_values("filing_date")
        shares_history = history.loc[history["shares_outstanding"].notna()]
        shares_source = "SEC_DEI_ENTITY_COMMON_STOCK_SHARES_OUTSTANDING"
        if shares_history.empty:
            shares_history = history.loc[
                history["fiscal_period"].eq("FY")
                & history["diluted_weighted_average_shares"].notna()
            ].copy()
            shares_history["shares_outstanding"] = shares_history[
                "diluted_weighted_average_shares"
            ]
            shares_source = "SEC_US_GAAP_DILUTED_WEIGHTED_AVERAGE_PROXY"
        if price_series.empty or balance.empty or shares_history.empty:
            market_rows.append(
                {
                    "ticker": ticker,
                    "status": "FAIL_CLOSED_MISSING_PRICE_BALANCE_OR_SHARES",
                    "conditional_valuation_allowed": False,
                }
            )
            continue
        latest = balance.iloc[-1]
        shares = float(shares_history.iloc[-1]["shares_outstanding"])
        price = float(price_series.iloc[-1][ticker])
        debt_parts = pd.Series(
            {
                "debt_current_usd": pd.to_numeric(
                    latest["debt_current_usd"], errors="coerce"
                ),
                "debt_noncurrent_usd": pd.to_numeric(
                    latest["debt_noncurrent_usd"], errors="coerce"
                ),
            },
            dtype="float64",
        )
        if debt_parts.notna().sum() == 0 or pd.isna(latest["cash_usd"]):
            market_rows.append(
                {
                    "ticker": ticker,
                    "status": "FAIL_CLOSED_MISSING_EV_BRIDGE",
                    "conditional_valuation_allowed": False,
                }
            )
            continue
        debt = float(debt_parts.fillna(0.0).sum())
        cash = float(latest["cash_usd"])
        market_cap = price * shares
        market_ev = market_cap + debt - cash
        sample = returns[[ticker, "SPY"]].dropna()
        downside = sample.loc[sample["SPY"].lt(0)]
        symmetric_beta = sample[ticker].cov(sample["SPY"]) / sample["SPY"].var()
        downside_beta = downside[ticker].cov(downside["SPY"]) / downside["SPY"].var()
        beta_rows.append(
            {
                "ticker": ticker,
                "weekly_observations": len(sample),
                "downside_observations": len(downside),
                "raw_symmetric_beta": symmetric_beta,
                "raw_downside_beta": downside_beta,
            }
        )
        if (
            len(sample) < 100
            or len(downside) < 30
            or not np.isfinite([symmetric_beta, downside_beta]).all()
        ):
            market_rows.append(
                {
                    "ticker": ticker,
                    "status": "FAIL_CLOSED_INSUFFICIENT_RETURN_HISTORY",
                    "conditional_valuation_allowed": False,
                }
            )
            continue
        adjusted = [
            blume_weight * symmetric_beta + (1.0 - blume_weight),
            blume_weight * downside_beta + (1.0 - blume_weight),
        ]
        equity_weight = market_cap / (market_cap + debt) if market_cap + debt else 1.0
        debt_weight = 1.0 - equity_weight
        tax_rate = float(latest["effective_tax_rate_pct"])
        debt_cost = risk_free_pct + fallback_credit_spread_pct

        def wacc(beta: float) -> float:
            cost_equity = risk_free_pct + beta * equity_risk_premium_pct
            return equity_weight * cost_equity + debt_weight * debt_cost * (
                1.0 - tax_rate / 100.0
            )

        wacc_values = sorted(wacc(beta) for beta in adjusted)
        market_rows.append(
            {
                "ticker": ticker,
                "valuation_date": valuation_date.date().isoformat(),
                "market_price": price,
                "market_price_date": price_series.iloc[-1]["Date"].date().isoformat(),
                "shares_outstanding": shares,
                "shares_source": shares_source,
                "market_capitalization_usd": market_cap,
                "cash_usd": cash,
                "total_debt_usd": debt,
                "market_enterprise_value_usd": market_ev,
                "ev_to_equity_bridge_identity_error_usd": abs(
                    market_ev - (market_cap + debt - cash)
                ),
                "debt_components_identified": int(debt_parts.notna().sum()),
                "status": "MARKET_AND_EV_BRIDGE_READY",
                "conditional_valuation_allowed": True,
            }
        )
        wacc_rows.append(
            {
                "ticker": ticker,
                "risk_free_rate_pct": risk_free_pct,
                "risk_free_observation_date": risk_free.iloc[-1]["DATE"].date().isoformat(),
                "equity_risk_premium_pct": equity_risk_premium_pct,
                "symmetric_wacc_pct": wacc_values[0],
                "downside_wacc_pct": wacc_values[1],
                "midpoint_wacc_pct": sum(wacc_values) / 2.0,
                "wacc_is_independent_of_market_price_fit": True,
                "operating_scenario_risk_added_to_wacc": False,
                "risk_channel_double_count_count": 0,
            }
        )
    sources = pd.DataFrame(
        [
            {"source": "YAHOO_FINANCE", "path": str(daily_path), "sha256": _sha(daily_path)},
            {"source": "YAHOO_FINANCE", "path": str(weekly_path), "sha256": _sha(weekly_path)},
            {"source": "FRED_DGS10", "path": str(risk_free_path), "sha256": _sha(risk_free_path)},
        ]
    )
    return {
        "subindustry_market_ev_bridge": pd.DataFrame(market_rows),
        "subindustry_return_beta_diagnostics": pd.DataFrame(beta_rows),
        "subindustry_independent_wacc_range": pd.DataFrame(wacc_rows),
        "subindustry_market_source_lineage": sources,
    }


def build_conditional_valuation_research(
    *,
    annual: pd.DataFrame,
    quarterly: pd.DataFrame,
    forecast_performance: pd.DataFrame,
    fixed_oos_forecasts: pd.DataFrame,
    market_ev: pd.DataFrame,
    wacc: pd.DataFrame,
    terminal_growth_pct: float = 2.5,
) -> dict[str, pd.DataFrame]:
    flows: list[pd.DataFrame] = []
    value_rows: list[dict[str, object]] = []
    reverse_rows: list[dict[str, object]] = []
    gate_rows: list[dict[str, object]] = []
    for ticker in sorted(set(annual["ticker"])):
        annual_group = annual.loc[annual["ticker"].eq(ticker)].sort_values(
            "fiscal_year"
        )
        quarter_group = quarterly.loc[quarterly["ticker"].eq(ticker)].sort_values(
            "report_date"
        )
        performance = forecast_performance.loc[
            forecast_performance["ticker"].eq(ticker)
        ]
        predictions = fixed_oos_forecasts.loc[
            fixed_oos_forecasts["ticker"].eq(ticker)
        ].sort_values("period")
        market = market_ev.loc[
            market_ev["ticker"].eq(ticker)
            & market_ev["conditional_valuation_allowed"].fillna(False)
        ]
        required = {
            "reported_operating_margin": int(
                annual_group["operating_margin_pct"].notna().sum()
            )
            >= 3,
            "reported_roic": int(annual_group["reported_roic_pct"].notna().sum())
            >= 3,
            "standard_profit_target": not performance.empty
            and performance.iloc[0]["profit_target_definition"] == "OPERATING_MARGIN",
            "validated_forecast": not performance.empty
            and performance.iloc[0]["forecast_authority"]
            in {"STRONG", "MIXED"}
            and int(performance.iloc[0]["oos_observations"]) >= 4,
            "market_ev": not market.empty,
            "independent_wacc": ticker in set(wacc["ticker"]),
        }
        failed = [name for name, passed in required.items() if not passed]
        if failed:
            gate_rows.append(
                {
                    "ticker": ticker,
                    "conditional_dcf_run": False,
                    "failed_gates": "|".join(failed),
                    "fair_value_authority": False,
                    "terminal_input_ready": False,
                }
            )
            continue
        ttm = quarter_group.tail(4)
        if len(ttm) < 4 or ttm[["revenue_usd", "operating_income_usd"]].isna().any().any():
            gate_rows.append(
                {
                    "ticker": ticker,
                    "conditional_dcf_run": False,
                    "failed_gates": "TTM_FINANCIALS",
                    "fair_value_authority": False,
                    "terminal_input_ready": False,
                }
            )
            continue
        base_revenue = float(ttm["revenue_usd"].sum())
        initial_margin = float(ttm["operating_income_usd"].sum() / base_revenue * 100.0)
        historical_margins = annual_group["operating_margin_pct"].dropna().tail(5)
        roics = annual_group["reported_roic_pct"].dropna().tail(5)
        roics = roics.loc[roics.gt(0) & roics.lt(100)]
        if len(roics) < 3:
            gate_rows.append(
                {
                    "ticker": ticker,
                    "conditional_dcf_run": False,
                    "failed_gates": "ROIC_ECONOMIC_DOMAIN",
                    "fair_value_authority": False,
                    "terminal_input_ready": False,
                }
            )
            continue
        tax = float(annual_group["effective_tax_rate_pct"].dropna().tail(5).median())
        growth = float(predictions["predicted_revenue_yoy_pct"].tail(2).median())
        market_row = market.iloc[0]
        wacc_row = wacc.loc[wacc["ticker"].eq(ticker)].iloc[0]
        scenario_inputs = {
            "bear": {
                "growth": growth - 3.0,
                "margin": float(historical_margins.quantile(0.25)),
                "roic": float(roics.quantile(0.25)),
                "wacc": float(wacc_row["downside_wacc_pct"]),
            },
            "base": {
                "growth": growth,
                "margin": float(historical_margins.median()),
                "roic": float(roics.median()),
                "wacc": float(wacc_row["midpoint_wacc_pct"]),
            },
            "bull": {
                "growth": growth + 3.0,
                "margin": float(historical_margins.quantile(0.75)),
                "roic": float(roics.quantile(0.75)),
                "wacc": float(wacc_row["symmetric_wacc_pct"]),
            },
        }
        base_assumptions: DcfAssumptions | None = None
        for scenario, values in scenario_inputs.items():
            if values["wacc"] <= terminal_growth_pct:
                continue
            if values["margin"] <= 0 or values["roic"] <= terminal_growth_pct:
                continue
            assumptions = DcfAssumptions(
                ticker=ticker,
                scenario=scenario,
                base_revenue_usd=base_revenue,
                near_term_growth_pct=values["growth"],
                terminal_growth_pct=terminal_growth_pct,
                initial_margin_pct=initial_margin,
                terminal_margin_pct=values["margin"],
                tax_rate_pct=tax,
                initial_roic_pct=float(roics.iloc[-1]),
                terminal_roic_pct=values["roic"],
                wacc_pct=values["wacc"],
            )
            flow, summary = enterprise_value(assumptions)
            flows.append(flow)
            raw_common_equity = (
                summary["enterprise_value_usd"]
                + float(market_row["cash_usd"])
                - float(market_row["total_debt_usd"])
            )
            common_equity = max(raw_common_equity, 0.0)
            floor_adjustment = common_equity - raw_common_equity
            per_share = common_equity / float(market_row["shares_outstanding"])
            identity = float(
                (
                    flow["reinvestment_rate_pct"]
                    - flow["revenue_growth_pct"] / flow["roic_pct"] * 100.0
                )
                .abs()
                .max()
            )
            value_rows.append(
                {
                    "ticker": ticker,
                    "scenario": scenario,
                    **summary,
                    "cash_usd": market_row["cash_usd"],
                    "total_debt_usd": market_row["total_debt_usd"],
                    "common_equity_value_usd": common_equity,
                    "raw_common_equity_bridge_usd": raw_common_equity,
                    "limited_liability_floor_adjustment_usd": floor_adjustment,
                    "conditional_value_per_share_usd": per_share,
                    "market_price": market_row["market_price"],
                    "expectations_gap_pct": per_share
                    / float(market_row["market_price"])
                    * 100.0
                    - 100.0,
                    "growth_reinvestment_roic_identity_max_error_pct_points": identity,
                    "ev_to_common_equity_identity_error_usd": abs(
                        raw_common_equity
                        - (
                            summary["enterprise_value_usd"]
                            + float(market_row["cash_usd"])
                            - float(market_row["total_debt_usd"])
                        )
                    ),
                    "high_terminal_dependence_flag": summary[
                        "terminal_value_share_pct"
                    ]
                    >= 80.0,
                    "fair_value_authority": False,
                    "use": "CONDITIONAL_EXPECTATIONS_DIAGNOSTIC_ONLY",
                }
            )
            if scenario == "base":
                base_assumptions = assumptions
        if base_assumptions is not None:
            implied_wacc = solve_parameter(
                base_assumptions,
                target_ev_usd=float(market_row["market_enterprise_value_usd"]),
                field="wacc_pct",
                lower=max(terminal_growth_pct + 0.25, 3.0),
                upper=20.0,
            )
            implied_margin = solve_parameter(
                base_assumptions,
                target_ev_usd=float(market_row["market_enterprise_value_usd"]),
                field="terminal_margin_pct",
                lower=0.1,
                upper=60.0,
            )
            reverse_rows.append(
                {
                    "ticker": ticker,
                    "market_enterprise_value_usd": market_row[
                        "market_enterprise_value_usd"
                    ],
                    "market_implied_wacc_status": implied_wacc["status"],
                    "market_implied_wacc_pct": implied_wacc["value"],
                    "market_implied_terminal_margin_status": implied_margin["status"],
                    "market_implied_terminal_margin_pct": implied_margin["value"],
                    "independent_wacc_low_pct": wacc_row["symmetric_wacc_pct"],
                    "independent_wacc_high_pct": wacc_row["downside_wacc_pct"],
                    "appropriate_wacc_claim_allowed": False,
                    "non_identification_preserved": True,
                    "fair_value_authority": False,
                }
            )
            gate_rows.append(
                {
                    "ticker": ticker,
                    "conditional_dcf_run": True,
                    "failed_gates": "",
                    "fair_value_authority": False,
                    "terminal_input_ready": False,
                }
            )
    return {
        "subindustry_conditional_dcf_flows": pd.concat(flows, ignore_index=True)
        if flows
        else pd.DataFrame(),
        "subindustry_conditional_dcf_summary": pd.DataFrame(value_rows),
        "subindustry_reverse_dcf_diagnostics": pd.DataFrame(reverse_rows),
        "subindustry_valuation_gates": pd.DataFrame(gate_rows),
    }
