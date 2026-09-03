from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.sec import CompanyFactsReader


def build_market_inputs(
    *,
    companyfacts_path: Path,
    price_path: Path,
    benchmark_path: Path,
    risk_free_path: Path,
    annual_financials: pd.DataFrame,
    cutoff: pd.Timestamp,
    equity_risk_premium_pct: float,
    fallback_credit_spread_pct: float,
    beta_weeks: int,
) -> pd.DataFrame:
    cutoff = pd.Timestamp(cutoff).normalize()
    price = pd.read_csv(price_path)
    price["Date"] = pd.to_datetime(price["Date"], errors="coerce")
    price = price.loc[price["Date"].le(cutoff)].sort_values("Date")
    benchmark = pd.read_csv(benchmark_path)
    benchmark["trade_date"] = pd.to_datetime(
        benchmark["trade_date"], errors="coerce"
    )
    benchmark = benchmark.loc[benchmark["trade_date"].le(cutoff)].sort_values(
        "trade_date"
    )
    weekly_stock = (
        price.set_index("Date")["Adj Close"]
        .resample("W-FRI")
        .last()
        .pct_change(fill_method=None)
    )
    weekly_market = (
        benchmark.set_index("trade_date")["close"]
        .resample("W-FRI")
        .last()
        .pct_change(fill_method=None)
    )
    returns = pd.concat(
        [weekly_stock.rename("stock"), weekly_market.rename("market")], axis=1
    ).dropna().tail(beta_weeks)
    if len(returns) < 52 or float(returns["market"].var()) <= 0:
        raise ValueError("At least 52 aligned weekly observations are required for beta")
    beta = float(returns["stock"].cov(returns["market"]) / returns["market"].var())
    rates = pd.read_csv(risk_free_path)
    rates["DATE"] = pd.to_datetime(rates["DATE"], errors="coerce")
    rates["DGS10"] = pd.to_numeric(rates["DGS10"], errors="coerce")
    risk_free = rates.loc[
        rates["DATE"].le(cutoff) & rates["DGS10"].notna()
    ].sort_values("DATE").iloc[-1]
    reader = CompanyFactsReader(companyfacts_path)
    shares = reader.annual_instant(
        ("EntityCommonStockSharesOutstanding",),
        "shares_outstanding",
        cutoff,
        namespace="dei",
        unit="shares",
    )
    if shares.empty:
        raise ValueError("No point-in-time CAT shares outstanding fact")
    latest = annual_financials.loc[annual_financials["financial_complete"]].iloc[-1]
    latest_shares = float(shares.sort_values("fiscal_year").iloc[-1]["shares_outstanding"])
    market_price = float(price.iloc[-1]["Adj Close"])
    equity_value = market_price * latest_shares
    debt = float(latest["total_debt_usd"])
    cash = float(latest["cash_usd"])
    interest = pd.to_numeric(latest["interest_expense_usd"], errors="coerce")
    direct_cost_of_debt = float(interest) / debt * 100.0 if debt > 0 and np.isfinite(interest) else np.nan
    cost_of_debt_pct = (
        direct_cost_of_debt
        if np.isfinite(direct_cost_of_debt) and direct_cost_of_debt > 0
        else float(risk_free["DGS10"]) + fallback_credit_spread_pct
    )
    cost_of_debt_method = (
        "DIRECT_ANNUAL_INTEREST_OVER_PERIOD_END_DEBT"
        if np.isfinite(direct_cost_of_debt) and direct_cost_of_debt > 0
        else "RISK_FREE_PLUS_PREDECLARED_CREDIT_SPREAD_FALLBACK"
    )
    tax_rate_pct = float(latest["effective_tax_rate"]) * 100.0
    cost_of_equity_pct = float(risk_free["DGS10"]) + beta * equity_risk_premium_pct
    total_capital = equity_value + debt
    wacc_pct = (
        equity_value / total_capital * cost_of_equity_pct
        + debt / total_capital * cost_of_debt_pct * (1.0 - tax_rate_pct / 100.0)
    )
    return pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "market_date": price.iloc[-1]["Date"].date().isoformat(),
                "market_price": market_price,
                "shares_outstanding": latest_shares,
                "equity_market_value_usd": equity_value,
                "total_debt_usd": debt,
                "cash_usd": cash,
                "market_enterprise_value_usd": equity_value + debt - cash,
                "beta": beta,
                "beta_observations": len(returns),
                "risk_free_rate_pct": float(risk_free["DGS10"]),
                "risk_free_date": risk_free["DATE"].date().isoformat(),
                "equity_risk_premium_pct": equity_risk_premium_pct,
                "cost_of_equity_pct": cost_of_equity_pct,
                "cost_of_debt_pct": cost_of_debt_pct,
                "cost_of_debt_method": cost_of_debt_method,
                "wacc_pct": wacc_pct,
                "market_data_point_in_time": True,
            }
        ]
    )
