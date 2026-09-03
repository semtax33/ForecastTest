from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_gd_market_evidence(
    *, root: Path, config: dict[str, Any], latest_balance: pd.Series, tax_rate_pct: float
) -> dict[str, pd.DataFrame]:
    valuation_date = pd.Timestamp(config["valuation_date"])
    daily_path = root / config["market_daily_snapshot"]
    weekly_path = root / config["market_weekly_snapshot"]
    risk_free_path = root / config["risk_free_snapshot"]
    metadata_path = root / config["market_metadata"]
    daily = pd.read_csv(daily_path, parse_dates=["Date"])
    weekly = pd.read_csv(weekly_path, parse_dates=["Date"]).set_index("Date")
    risk_free = pd.read_csv(risk_free_path, parse_dates=["DATE"])
    risk_free["DGS10"] = pd.to_numeric(risk_free["DGS10"], errors="coerce")
    daily = daily.loc[daily["Date"].le(valuation_date)].sort_values("Date")
    weekly = weekly.loc[weekly.index <= valuation_date]
    risk_free = risk_free.loc[
        risk_free["DATE"].le(valuation_date) & risk_free["DGS10"].notna()
    ].sort_values("DATE")
    if daily.empty or weekly.empty or risk_free.empty:
        raise ValueError("Market or risk-free snapshot has no observation by valuation date")
    market_price = float(daily.iloc[-1]["GD"])
    risk_free_pct = float(risk_free.iloc[-1]["DGS10"])
    returns = weekly.pct_change(fill_method=None).dropna(how="all").tail(
        int(config["beta_weeks"])
    )
    beta_rows: list[dict[str, object]] = []
    for ticker in ("GD", "LMT", "NOC", "RTX"):
        sample = returns[[ticker, "SPY"]].dropna()
        downside = sample.loc[sample["SPY"].lt(0.0)]
        beta_rows.append(
            {
                "ticker": ticker,
                "weekly_observations": len(sample),
                "symmetric_beta": sample[ticker].cov(sample["SPY"])
                / sample["SPY"].var(),
                "downside_observations": len(downside),
                "downside_beta": downside[ticker].cov(downside["SPY"])
                / downside["SPY"].var(),
                "return_window_end": valuation_date.date().isoformat(),
                "source_path": str(weekly_path),
                "source_sha256": _sha256(weekly_path),
            }
        )
    beta = pd.DataFrame(beta_rows)
    selected = beta.loc[beta["ticker"].eq("GD")].iloc[0]
    weight = float(config["beta_blume_weight"])
    symmetric = weight * float(selected["symmetric_beta"]) + (1.0 - weight)
    downside = weight * float(selected["downside_beta"]) + (1.0 - weight)
    shares = float(latest_balance["shares_outstanding"])
    debt = float(latest_balance["debt_current_usd"] + latest_balance["debt_noncurrent_usd"])
    cash = float(latest_balance["cash_usd"])
    market_cap = market_price * shares
    equity_weight = market_cap / (market_cap + debt)
    debt_weight = 1.0 - equity_weight
    erp = float(config["equity_risk_premium_pct"])
    debt_cost = risk_free_pct + float(config["fallback_credit_spread_pct"])

    def wacc(beta_value: float) -> float:
        cost_equity = risk_free_pct + beta_value * erp
        return equity_weight * cost_equity + debt_weight * debt_cost * (
            1.0 - tax_rate_pct / 100.0
        )

    low = wacc(symmetric)
    high = wacc(downside)
    wacc_frame = pd.DataFrame(
        [
            {
                "valuation_date": valuation_date.date().isoformat(),
                "risk_free_rate_pct": risk_free_pct,
                "risk_free_observation_date": risk_free.iloc[-1]["DATE"].date().isoformat(),
                "equity_risk_premium_pct": erp,
                "raw_symmetric_beta": selected["symmetric_beta"],
                "raw_downside_beta": selected["downside_beta"],
                "blume_symmetric_beta": symmetric,
                "blume_downside_beta": downside,
                "marginal_debt_cost_pct": debt_cost,
                "tax_rate_pct": tax_rate_pct,
                "equity_weight_pct": equity_weight * 100.0,
                "debt_weight_pct": debt_weight * 100.0,
                "symmetric_wacc_pct": min(low, high),
                "downside_wacc_pct": max(low, high),
                "midpoint_wacc_pct": (low + high) / 2.0,
                "wacc_is_independent_of_market_price_fit": True,
                "operating_scenario_risk_added_to_wacc": False,
                "risk_channel_double_count_count": 0,
            }
        ]
    )
    market = pd.DataFrame(
        [
            {
                "valuation_date": valuation_date.date().isoformat(),
                "market_price": market_price,
                "market_price_date": daily.iloc[-1]["Date"].date().isoformat(),
                "shares_outstanding": shares,
                "shares_source": "SEC_XBRL_ENTITY_COMMON_STOCK_SHARES_OUTSTANDING",
                "market_capitalization_usd": market_cap,
                "cash_usd": cash,
                "total_debt_usd": debt,
                "market_enterprise_value_usd": market_cap + debt - cash,
                "ev_to_equity_bridge_identity_error_usd": 0.0,
                "daily_price_source_sha256": _sha256(daily_path),
                "market_metadata_sha256": _sha256(metadata_path),
            }
        ]
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = pd.DataFrame(
        [
            {
                "source": "YAHOO_FINANCE_ADJUSTED_CLOSE",
                "as_of": daily.iloc[-1]["Date"].date().isoformat(),
                "source_path": str(daily_path),
                "source_sha256": _sha256(daily_path),
                "retrieved_at_utc": metadata["retrieved_at_utc"],
            },
            {
                "source": "FRED_DGS10",
                "as_of": risk_free.iloc[-1]["DATE"].date().isoformat(),
                "source_path": str(risk_free_path),
                "source_sha256": _sha256(risk_free_path),
                "retrieved_at_utc": metadata["retrieved_at_utc"],
            },
        ]
    )
    return {
        "gd_market_capitalization_bridge": market,
        "gd_return_beta_diagnostics": beta,
        "gd_independent_wacc_range": wacc_frame,
        "gd_market_source_lineage": source,
    }
