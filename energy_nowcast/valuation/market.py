from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .financials import ENERGY_TICKERS, _fact_frame


PARTNERSHIP_SHARE_TAGS = (
    "LimitedPartnersCapitalAccountUnitsOutstanding",
    "PartnersCapitalAccountUnits",
)


def _latest_partnership_units(
    companyfacts_root: Path,
    ticker: str,
    market_date: pd.Timestamp,
) -> tuple[float, pd.Timestamp, str]:
    for tag in PARTNERSHIP_SHARE_TAGS:
        facts = _fact_frame(companyfacts_root, ticker, tag, unit="shares")
        if facts.empty:
            continue
        eligible = facts.loc[
            facts["end"].le(market_date)
            & facts["form"].isin(["10-Q", "10-K"])
        ].sort_values(["end", "filed"])
        if len(eligible):
            row = eligible.iloc[-1]
            return float(row["val"]), pd.Timestamp(row["end"]), f"us-gaap:{tag}"
    return np.nan, pd.NaT, "UNAVAILABLE"


def _beta(
    ticker_price: pd.DataFrame,
    benchmark: pd.DataFrame,
    observations: int = 104,
) -> tuple[float, int]:
    stock = ticker_price[["Date", "Close"]].copy()
    stock["Date"] = pd.to_datetime(stock["Date"], errors="coerce")
    stock = (
        stock.dropna()
        .set_index("Date")["Close"]
        .resample("W-FRI").last()
        .pct_change(fill_method=None)
    )
    market = benchmark[["trade_date", "close"]].copy()
    market["trade_date"] = pd.to_datetime(market["trade_date"], errors="coerce")
    market = (
        market.dropna()
        .set_index("trade_date")["close"]
        .resample("W-FRI").last()
        .pct_change(fill_method=None)
    )
    joined = pd.concat([stock.rename("stock"), market.rename("market")], axis=1).dropna().tail(observations)
    variance = float(joined["market"].var(ddof=1)) if len(joined) >= 26 else np.nan
    if not np.isfinite(variance) or variance <= 0:
        return 1.0, len(joined)
    beta = float(joined.cov().loc["stock", "market"] / variance)
    return float(np.clip(beta, 0.5, 2.0)), len(joined)


def load_market_inputs(
    *,
    price_root: Path,
    benchmark_path: Path,
    shares_path: Path,
    risk_free_path: Path,
    companyfacts_root: Path,
    latest_financials: pd.DataFrame,
    tickers: Iterable[str] = ENERGY_TICKERS,
    as_of_date: pd.Timestamp,
    equity_risk_premium_pct: float,
    fallback_credit_spread_pct: float,
    maximum_price_age_days: int,
    price_overrides_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    benchmark = pd.read_csv(benchmark_path)
    shares = pd.read_csv(shares_path)
    shares["trade_date"] = pd.to_datetime(shares["trade_date"], errors="coerce")
    risk_free = pd.read_csv(risk_free_path)
    risk_free["DATE"] = pd.to_datetime(risk_free["DATE"], errors="coerce")
    risk_free["DGS10"] = pd.to_numeric(risk_free["DGS10"], errors="coerce")
    overrides = pd.DataFrame()
    if price_overrides_path is not None and price_overrides_path.exists():
        overrides = pd.read_csv(price_overrides_path)
        overrides["market_date"] = pd.to_datetime(
            overrides["market_date"], errors="coerce"
        )
        overrides["close"] = pd.to_numeric(overrides["close"], errors="coerce")
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        price_path = price_root / f"{ticker}.csv"
        fallback_price_used = not price_path.exists()
        if fallback_price_used:
            override = overrides.loc[overrides["ticker"].eq(ticker)].copy()
            if override.empty:
                raise FileNotFoundError(
                    f"Missing local price history and explicit override for {ticker}"
                )
            prices = override.rename(
                columns={"market_date": "Date", "close": "Close"}
            )[["Date", "Close"]]
            price_source = str(override.iloc[-1]["source_url"])
        else:
            prices = pd.read_csv(price_path)
            price_source = str(price_path)
        prices["Date"] = pd.to_datetime(prices["Date"], errors="coerce")
        prices["Close"] = pd.to_numeric(prices["Close"], errors="coerce")
        prices = prices.loc[
            prices["Date"].le(as_of_date) & prices["Close"].gt(0)
        ].sort_values("Date")
        latest_price = prices.iloc[-1]
        market_date = pd.Timestamp(latest_price["Date"])
        share_rows = shares.loc[
            shares["security_id"].eq(f"SEC_US_{ticker}")
            & shares["trade_date"].le(market_date)
            & shares["shares"].gt(0)
        ].sort_values("trade_date")
        if len(share_rows):
            latest_shares = share_rows.iloc[-1]
            share_count = float(latest_shares["shares"])
            share_date = pd.Timestamp(latest_shares["trade_date"])
            share_source = "ARCANA_SILVER_NORMALIZED_SHARES"
        else:
            share_count, share_date, share_source = _latest_partnership_units(
                companyfacts_root, ticker, market_date
            )
        beta, beta_n = _beta(prices, benchmark)
        rf_rows = risk_free.loc[
            risk_free["DATE"].le(market_date) & risk_free["DGS10"].notna()
        ].sort_values("DATE")
        risk_free_rate = float(rf_rows.iloc[-1]["DGS10"])
        rows.append({
            "ticker": ticker,
            "market_date": market_date,
            "market_price": float(latest_price["Close"]),
            "shares_outstanding": share_count,
            "shares_date": share_date,
            "shares_source": share_source,
            "market_cap_usd": float(latest_price["Close"]) * share_count,
            "levered_beta": beta,
            "beta_weekly_observations": beta_n,
            "beta_method": (
                "LOCAL_WEEKLY_RETURN_BETA"
                if beta_n >= 26
                else "CONSERVATIVE_BETA_1P0_INSUFFICIENT_LOCAL_HISTORY"
            ),
            "risk_free_rate_pct": risk_free_rate,
            "risk_free_date": pd.Timestamp(rf_rows.iloc[-1]["DATE"]),
            "price_age_days": int((as_of_date.normalize() - market_date.normalize()).days),
            "price_freshness_status": (
                "CURRENT_WITHIN_LIMIT"
                if (as_of_date.normalize() - market_date.normalize()).days <= maximum_price_age_days
                else "STALE_PRICE_INPUT"
            ),
            "price_source_path": price_source,
            "price_override_used": fallback_price_used,
            "benchmark_source_path": str(benchmark_path),
            "risk_free_source_path": str(risk_free_path),
        })
    market = pd.DataFrame(rows).merge(
        latest_financials,
        on="ticker",
        how="left",
        validate="one_to_one",
    )
    market["cost_of_equity_pct"] = (
        market["risk_free_rate_pct"]
        + market["levered_beta"] * equity_risk_premium_pct
    )
    # Current debt is used when a clean prior-year debt observation is not part
    # of the common V1 schema; the method is disclosed rather than imputed.
    average_debt = market["total_debt_usd"]
    observed_cost_debt = market["ttm_interest_expense_usd"].abs() / average_debt * 100.0
    fallback_cost_debt = market["risk_free_rate_pct"] + fallback_credit_spread_pct
    market["pre_tax_cost_of_debt_pct"] = observed_cost_debt.where(
        observed_cost_debt.between(0.5, 15.0), fallback_cost_debt
    )
    market["cost_of_debt_method"] = np.where(
        observed_cost_debt.between(0.5, 15.0),
        "TTM_INTEREST_OVER_AVERAGE_DEBT",
        "RISK_FREE_PLUS_CONFIGURED_CREDIT_SPREAD",
    )
    capital = market["market_cap_usd"] + market["total_debt_usd"]
    market["equity_weight"] = market["market_cap_usd"] / capital
    market["debt_weight"] = market["total_debt_usd"] / capital
    market["wacc_pct"] = (
        market["equity_weight"] * market["cost_of_equity_pct"]
        + market["debt_weight"] * market["pre_tax_cost_of_debt_pct"]
        * (1.0 - market["effective_tax_rate"])
    )
    market["market_enterprise_value_usd"] = (
        market["market_cap_usd"] + market["total_debt_usd"] - market["cash_usd"]
    )
    market["market_input_complete"] = market[[
        "market_price", "shares_outstanding", "market_cap_usd",
        "total_debt_usd", "cash_usd", "wacc_pct",
    ]].notna().all(axis=1)
    coverage = market[[
        "ticker", "subindustry", "market_date", "price_age_days",
        "price_freshness_status", "shares_date", "shares_source",
        "beta_weekly_observations", "beta_method", "price_override_used",
        "market_input_complete",
    ]].copy()
    return market, coverage
