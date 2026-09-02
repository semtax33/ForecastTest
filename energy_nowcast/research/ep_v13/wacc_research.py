from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from energy_nowcast.research.phase6.financial_targets import EP_TICKERS


def _weekly_stock_return(path: Path, as_of: pd.Timestamp) -> pd.Series:
    frame = pd.read_csv(path)
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    column = "Adj Close" if "Adj Close" in frame else "Close"
    frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return (
        frame.loc[frame["Date"].le(as_of)]
        .dropna(subset=["Date", column])
        .set_index("Date")[column]
        .resample("W-FRI")
        .last()
        .pct_change(fill_method=None)
    )


def _weekly_market_return(path: Path, as_of: pd.Timestamp) -> pd.Series:
    frame = pd.read_csv(path)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return (
        frame.loc[frame["trade_date"].le(as_of)]
        .dropna(subset=["trade_date", "close"])
        .set_index("trade_date")["close"]
        .resample("W-FRI")
        .last()
        .pct_change(fill_method=None)
    )


def _beta(frame: pd.DataFrame) -> float:
    variance = frame["market"].var(ddof=1)
    if len(frame) < 26 or not np.isfinite(variance) or variance <= 0:
        return np.nan
    return float(frame["stock"].cov(frame["market"]) / variance)


def build_beta_term_structure(
    *,
    price_root: Path,
    benchmark_path: Path,
    market_inputs: pd.DataFrame,
    tickers: Iterable[str] = EP_TICKERS,
) -> pd.DataFrame:
    market_dates = market_inputs.set_index("ticker")["market_date"]
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        as_of = pd.Timestamp(market_dates.loc[ticker])
        path = price_root / f"{ticker}.csv"
        if not path.exists():
            rows.append(
                {
                    "ticker": ticker,
                    "beta_status": "LOCKED_NO_LOCAL_RETURN_HISTORY",
                    "market_price_fit_used": False,
                    "expectations_surface_used": False,
                }
            )
            continue
        stock = _weekly_stock_return(path, as_of)
        market = _weekly_market_return(benchmark_path, as_of)
        joined = pd.concat(
            [stock.rename("stock"), market.rename("market")], axis=1
        ).dropna()
        row: dict[str, object] = {
            "ticker": ticker,
            "beta_status": "INDEPENDENT_LOCAL_TOTAL_RETURN_HISTORY",
            "weekly_observations_available": len(joined),
            "as_of_date": as_of,
            "stock_return_source": str(path),
            "benchmark_return_source": str(benchmark_path),
            "market_price_fit_used": False,
            "expectations_surface_used": False,
        }
        for years, observations in ((2, 104), (5, 260), (7.5, 390), (10, 520)):
            sample = joined.tail(observations)
            suffix = str(years).replace(".", "p")
            row[f"symmetric_beta_{suffix}y"] = (
                _beta(sample) if len(sample) >= int(observations * 0.8) else np.nan
            )
            downside = sample.loc[sample["market"].lt(0)]
            row[f"downside_beta_{suffix}y"] = _beta(downside)
            row[f"observations_{suffix}y"] = len(sample)
            row[f"downside_observations_{suffix}y"] = len(downside)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def _wacc(
    beta: float,
    row: pd.Series,
    tax_rate_pct: float,
    equity_risk_premium_pct: float,
) -> float:
    cost_equity = float(row["risk_free_rate_pct"]) + beta * equity_risk_premium_pct
    after_tax_debt = float(row["pre_tax_cost_of_debt_pct"]) * (
        1.0 - tax_rate_pct / 100.0
    )
    return (
        float(row["adjusted_equity_weight"]) * cost_equity
        + float(row["adjusted_debt_weight"]) * after_tax_debt
    )


def build_wacc_reference_ranges(
    beta_terms: pd.DataFrame,
    market_inputs: pd.DataFrame,
    assumptions: pd.DataFrame,
    equity_risk_premium_pct: float = 4.5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    market = market_inputs.set_index("ticker")
    base = assumptions.loc[assumptions["scenario"].eq("BASE")].set_index("ticker")
    rows: list[dict[str, object]] = []
    for beta_row in beta_terms.itertuples(index=False):
        ticker = str(beta_row.ticker)
        row = market.loc[ticker]
        symmetric = float(getattr(beta_row, "symmetric_beta_10y", np.nan))
        downside = float(getattr(beta_row, "downside_beta_10y", np.nan))
        output: dict[str, object] = {
            "ticker": ticker,
            "v1_1_base_wacc_pct": float(row["wacc_adjusted_pct"]),
            "risk_free_rate_pct": float(row["risk_free_rate_pct"]),
            "equity_risk_premium_pct": equity_risk_premium_pct,
            "symmetric_beta_10y": symmetric,
            "downside_beta_10y": downside,
            "market_price_fit_used": False,
            "expectations_surface_used": False,
            "interpretation": "INDEPENDENT_RETURN_BASED_RANGE_NOT_APPROPRIATE_WACC_POINT_ESTIMATE",
        }
        if np.isfinite(symmetric) and np.isfinite(downside):
            symmetric_wacc = _wacc(
                symmetric,
                row,
                float(base.loc[ticker, "tax_rate_pct"]),
                equity_risk_premium_pct,
            )
            downside_wacc = _wacc(
                downside,
                row,
                float(base.loc[ticker, "tax_rate_pct"]),
                equity_risk_premium_pct,
            )
            output.update(
                {
                    "wacc_reference_status": "INDEPENDENT_RANGE_AVAILABLE",
                    "symmetric_return_wacc_pct": symmetric_wacc,
                    "downside_return_wacc_pct": downside_wacc,
                    "return_based_wacc_low_pct": min(symmetric_wacc, downside_wacc),
                    "return_based_wacc_high_pct": max(symmetric_wacc, downside_wacc),
                }
            )
        else:
            output["wacc_reference_status"] = "LOCKED_INSUFFICIENT_LOCAL_RETURN_HISTORY"
        rows.append(output)
    result = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    available = result.loc[result["wacc_reference_status"].eq("INDEPENDENT_RANGE_AVAILABLE")]
    summary = pd.DataFrame(
        [
            {
                "tickers": len(result),
                "range_available_tickers": len(available),
                "v1_1_base_wacc_median_pct": result["v1_1_base_wacc_pct"].median(),
                "symmetric_return_wacc_median_pct": available[
                    "symmetric_return_wacc_pct"
                ].median(),
                "downside_return_wacc_median_pct": available[
                    "downside_return_wacc_pct"
                ].median(),
                "return_based_low_median_pct": available[
                    "return_based_wacc_low_pct"
                ].median(),
                "return_based_high_median_pct": available[
                    "return_based_wacc_high_pct"
                ].median(),
                "single_appropriate_wacc_claim_allowed": False,
            }
        ]
    )
    return result, summary


def build_risk_allocation_policy() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("NORMALIZED_COMMODITY_PRICE", "CASH_FLOW_SCENARIO", False),
            ("PRODUCTION_DECLINE", "CASH_FLOW_SCENARIO", False),
            ("RESERVE_REPLACEMENT_COST", "CASH_FLOW_SCENARIO", False),
            ("OPERATING_TRANSPORT_PRODUCTION_TAX", "CASH_FLOW_SCENARIO", False),
            ("GEOPOLITICAL_OPERATING_DISRUPTION", "CASH_FLOW_SCENARIO", False),
            ("BROAD_MARKET_SYSTEMATIC_RETURN_RISK", "WACC", False),
            ("CAPITAL_STRUCTURE_AND_DEFAULT_RISK", "WACC", False),
            ("EXTREME_UNMODELED_RESIDUAL_UNCERTAINTY", "RESIDUAL_SEPARATE_UNAPPLIED", False),
            ("HORMUZ_PRICE_OR_VOLUME_REGIME", "CASH_FLOW_SCENARIO", False),
        ],
        columns=["risk", "allocated_channel", "dual_channel_allowed"],
    ).assign(
        policy="ONE_RISK_ONE_PRIMARY_CHANNEL_UNLESS_EXPLICIT_EMPIRICAL_JUSTIFICATION"
    )


def audit_v11_scenario_coupling(assumptions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker, group in assumptions.groupby("ticker", sort=True):
        base = group.loc[group["scenario"].eq("BASE")].iloc[0]
        for scenario in group.itertuples(index=False):
            cash_flow_changed = (
                not np.isclose(float(scenario.growth_pct), float(base["growth_pct"]))
                or not np.isclose(
                    float(scenario.operating_margin_pct),
                    float(base["operating_margin_pct"]),
                )
            )
            wacc_changed = not np.isclose(
                float(scenario.wacc_pct), float(base["wacc_pct"])
            )
            coupled = cash_flow_changed and wacc_changed
            rows.append(
                {
                    "ticker": ticker,
                    "scenario": scenario.scenario,
                    "cash_flow_scenario_changed": cash_flow_changed,
                    "wacc_changed": wacc_changed,
                    "coupled_channels": coupled,
                    "audit_status": (
                        "ATTRIBUTION_REQUIRED_COUPLED_CHANNELS"
                        if coupled
                        else "NO_COUPLED_CHANGE"
                    ),
                    "interpretation": (
                        "COUPLING_IS_NOT_PROOF_OF_DOUBLE_COUNTING_BUT_RISK_SOURCE_IS_UNATTRIBUTED"
                    ),
                    "v1_1_mutation_allowed": False,
                }
            )
    return pd.DataFrame(rows)


def build_double_count_gate(
    policy: pd.DataFrame, v11_audit: pd.DataFrame
) -> pd.DataFrame:
    duplicate_risks = policy.groupby("risk")["allocated_channel"].nunique().gt(1).sum()
    return pd.DataFrame(
        [
            {
                "proposed_policy_duplicate_risk_channels": int(duplicate_risks),
                "proposed_v1_3_double_count_gate": duplicate_risks == 0,
                "inherited_v1_1_coupled_nonbase_rows": int(
                    v11_audit["coupled_channels"].sum()
                ),
                "inherited_v1_1_action": "MONITOR_ONLY_FROZEN_NO_RETROACTIVE_CHANGE",
                "hormuz_wacc_premium_applied": False,
                "market_price_calibration_used": False,
                "production_eligible": False,
            }
        ]
    )


def build_wacc_research(
    *,
    price_root: Path,
    benchmark_path: Path,
    market_inputs_path: Path,
    assumptions_path: Path,
) -> dict[str, pd.DataFrame]:
    market = pd.read_csv(market_inputs_path)
    market = market.loc[market["subindustry"].eq("ep")].copy()
    assumptions = pd.read_csv(assumptions_path)
    assumptions = assumptions.loc[assumptions["subindustry"].eq("ep")].copy()
    beta = build_beta_term_structure(
        price_root=price_root,
        benchmark_path=benchmark_path,
        market_inputs=market,
    )
    ranges, summary = build_wacc_reference_ranges(beta, market, assumptions)
    policy = build_risk_allocation_policy()
    audit = audit_v11_scenario_coupling(assumptions)
    gate = build_double_count_gate(policy, audit)
    return {
        "beta_term_structure": beta,
        "wacc_reference_range": ranges,
        "wacc_reference_summary": summary,
        "risk_allocation_policy": policy,
        "v11_scenario_risk_coupling_audit": audit,
        "double_count_gate": gate,
    }
