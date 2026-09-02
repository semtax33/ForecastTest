from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DcfResult:
    enterprise_value_usd: float
    pv_explicit_fcff_usd: float
    pv_terminal_value_usd: float


def _project(
    *,
    base_revenue: float,
    growth_pct: float,
    operating_margin_pct: float,
    terminal_margin_pct: float,
    normalized_roic_pct: float,
    tax_rate_pct: float,
    wacc_pct: float,
    terminal_growth_pct: float,
    years: int = 5,
) -> DcfResult:
    wacc = wacc_pct / 100.0
    terminal_growth = terminal_growth_pct / 100.0
    if wacc <= terminal_growth:
        raise ValueError("WACC must exceed terminal growth")
    revenue = float(base_revenue)
    explicit = 0.0
    for year in range(1, years + 1):
        fade = (year - 1) / max(years - 1, 1)
        growth = growth_pct * (1.0 - fade) + terminal_growth_pct * fade
        revenue *= 1.0 + growth / 100.0
        nopat = (
            revenue * operating_margin_pct / 100.0
            * (1.0 - tax_rate_pct / 100.0)
        )
        reinvestment_rate = growth / normalized_roic_pct
        fcff = nopat * (1.0 - reinvestment_rate)
        explicit += fcff / ((1.0 + wacc) ** year)
    terminal_nopat = (
        revenue * (1.0 + terminal_growth)
        * terminal_margin_pct / 100.0
        * (1.0 - tax_rate_pct / 100.0)
    )
    terminal_reinvestment_rate = terminal_growth_pct / normalized_roic_pct
    terminal_fcff = terminal_nopat * (1.0 - terminal_reinvestment_rate)
    terminal_value = terminal_fcff / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1.0 + wacc) ** years)
    return DcfResult(
        enterprise_value_usd=float(explicit + pv_terminal),
        pv_explicit_fcff_usd=float(explicit),
        pv_terminal_value_usd=float(pv_terminal),
    )


def _source_history(history: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    ordered = history.sort_values("quarter_ordinal")
    prior = ordered.iloc[:-20]
    if len(prior) >= 8:
        return prior, "PRE_RECENT_20Q_COMPANY_HISTORY"
    return ordered, "FULL_HISTORY_INSUFFICIENT_PRE_RECENT_WINDOW"


def _shrunk_quantile(
    company: pd.Series,
    peers: pd.Series,
    quantile: float,
    prior_strength: float,
) -> tuple[float, float]:
    company = pd.to_numeric(company, errors="coerce").dropna()
    peers = pd.to_numeric(peers, errors="coerce").dropna()
    weight = len(company) / (len(company) + prior_strength)
    value = (
        weight * float(company.quantile(quantile))
        + (1.0 - weight) * float(peers.quantile(quantile))
    )
    return value, weight


def build_through_cycle_economics(
    ttm: pd.DataFrame,
    prior_strength: float = 8.0,
) -> pd.DataFrame:
    """Estimate research-only through-cycle distributions with peer shrinkage."""
    ep = ttm.loc[ttm["ttm_complete"] & ttm["subindustry"].eq("ep")].copy()
    source: dict[str, tuple[pd.DataFrame, str]] = {
        ticker: _source_history(history)
        for ticker, history in ep.groupby("ticker", sort=True)
    }
    peer = pd.concat([frame for frame, _ in source.values()], ignore_index=True)
    rows: list[dict[str, object]] = []
    for ticker, (history, method) in source.items():
        margin_values = history["operating_margin_pct"]
        roic_values = history["roic_pct"]
        row: dict[str, object] = {
            "ticker": ticker,
            "source_method": method,
            "company_observations": len(history),
            "history_start_quarter": history["quarter"].min(),
            "history_end_quarter": history["quarter"].max(),
        }
        for prefix, values, peer_values, lower, upper in (
            ("margin", margin_values, peer["operating_margin_pct"], -20.0, 50.0),
            ("roic", roic_values, peer["roic_pct"], 2.0, 35.0),
        ):
            for label, q in (("q25", 0.25), ("q50", 0.50), ("q75", 0.75)):
                value, weight = _shrunk_quantile(
                    values, peer_values, q, prior_strength
                )
                row[f"normalized_{prefix}_{label}_pct"] = float(
                    np.clip(value, lower, upper)
                )
                row[f"{prefix}_company_weight"] = weight
        recent = ep.loc[ep["ticker"].eq(ticker)].sort_values(
            "quarter_ordinal"
        ).tail(20)
        row["recent_20q_margin_median_pct"] = float(
            recent["operating_margin_pct"].median()
        )
        row["recent_20q_roic_median_pct"] = float(recent["roic_pct"].median())
        years = (
            pd.Period(row["history_end_quarter"], freq="Q").year
            - pd.Period(row["history_start_quarter"], freq="Q").year
        )
        row["normalization_confidence"] = (
            "HIGH_PRE_RECENT_WINDOW"
            if method.startswith("PRE_") and len(history) >= 12 and years >= 5
            else "MEDIUM_HIERARCHICAL_FULL_HISTORY"
            if len(history) >= 16
            else "LOW_LIMITED_COMPANY_HISTORY"
        )
        row["research_only"] = True
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def _common_equity_per_share(enterprise_value: float, market: pd.Series) -> float:
    equity = (
        enterprise_value
        - float(market["adjusted_total_debt_usd"])
        - float(market["noncontrolling_interest_usd"])
        - float(market["preferred_stock_usd"])
        + float(market["cash_usd"])
        + float(market["nonoperating_assets_usd"])
    )
    return equity / float(market["shares_outstanding"])


def evaluate_weighted_value(
    assumptions: pd.DataFrame,
    market: pd.Series,
    *,
    terminal_margin_center_pct: float | None = None,
    wacc_center_pct: float | None = None,
    growth_center_pct: float | None = None,
    operating_margin_center_pct: float | None = None,
    normalized_roic_center_pct: float | None = None,
) -> dict[str, float]:
    base = assumptions.loc[assumptions["scenario"].eq("BASE")].iloc[0]
    weighted_ev = 0.0
    weighted_terminal = 0.0
    weighted_fair = 0.0
    for _, scenario in assumptions.iterrows():
        weight = float(scenario["scenario_weight"])
        growth = float(scenario["growth_pct"])
        operating_margin = float(scenario["operating_margin_pct"])
        terminal_margin = operating_margin
        roic = float(scenario["roic_pct"])
        wacc = float(scenario["wacc_pct"])
        if growth_center_pct is not None:
            growth += growth_center_pct - float(base["growth_pct"])
            growth = float(np.clip(
                growth,
                float(scenario["growth_lower_bound"]),
                float(scenario["growth_upper_bound"]),
            ))
        if operating_margin_center_pct is not None:
            operating_margin += (
                operating_margin_center_pct
                - float(base["operating_margin_pct"])
            )
            operating_margin = float(np.clip(
                operating_margin,
                float(scenario["operating_margin_lower_bound"]),
                float(scenario["operating_margin_upper_bound"]),
            ))
            terminal_margin = operating_margin
        if terminal_margin_center_pct is not None:
            terminal_margin = float(np.clip(
                terminal_margin_center_pct
                + float(scenario["operating_margin_pct"])
                - float(base["operating_margin_pct"]),
                float(scenario["operating_margin_lower_bound"]),
                float(scenario["operating_margin_upper_bound"]),
            ))
        if normalized_roic_center_pct is not None:
            roic += normalized_roic_center_pct - float(base["roic_pct"])
            roic = float(np.clip(
                roic,
                float(scenario["roic_lower_bound"]),
                float(scenario["roic_upper_bound"]),
            ))
        if wacc_center_pct is not None:
            wacc += wacc_center_pct - float(base["wacc_pct"])
            wacc = float(np.clip(wacc, 3.0, 20.0))
        terminal_growth = float(scenario["terminal_growth_pct"])
        wacc = max(wacc, terminal_growth + 1.0)
        result = _project(
            base_revenue=float(market["ttm_revenue"]),
            growth_pct=growth,
            operating_margin_pct=operating_margin,
            terminal_margin_pct=terminal_margin,
            normalized_roic_pct=roic,
            tax_rate_pct=float(scenario["tax_rate_pct"]),
            wacc_pct=wacc,
            terminal_growth_pct=terminal_growth,
        )
        weighted_ev += result.enterprise_value_usd * weight
        weighted_terminal += result.pv_terminal_value_usd * weight
        weighted_fair += _common_equity_per_share(
            result.enterprise_value_usd, market
        ) * weight
    market_price = float(market["market_price"])
    return {
        "fair_value": weighted_fair,
        "market_price": market_price,
        "value_gap_pct": (weighted_fair / market_price - 1.0) * 100.0,
        "weighted_enterprise_value_usd": weighted_ev,
        "terminal_value_share_pct": weighted_terminal / weighted_ev * 100.0,
    }


SURFACE_GRIDS = {
    "TERMINAL_MARGIN_X_WACC": (
        (12.0, 17.0, 22.0, 27.0, 32.0, 37.0),
        (6.5, 7.5, 8.5, 9.5, 10.5),
    ),
    "GROWTH_X_OPERATING_MARGIN": (
        (-5.0, 0.0, 5.0, 10.0, 15.0),
        (12.0, 17.0, 22.0, 27.0, 32.0, 37.0),
    ),
    "GROWTH_X_NORMALIZED_ROIC": (
        (-5.0, 0.0, 5.0, 10.0, 15.0),
        (6.0, 10.0, 14.0, 18.0, 22.0, 26.0),
    ),
}


def _surface_kwargs(dimension: str, x: float, y: float) -> dict[str, float]:
    if dimension == "TERMINAL_MARGIN_X_WACC":
        return {"terminal_margin_center_pct": x, "wacc_center_pct": y}
    if dimension == "GROWTH_X_OPERATING_MARGIN":
        return {"growth_center_pct": x, "operating_margin_center_pct": y}
    if dimension == "GROWTH_X_NORMALIZED_ROIC":
        return {"growth_center_pct": x, "normalized_roic_center_pct": y}
    raise ValueError(f"Unsupported surface: {dimension}")


def build_expectations_surfaces(
    assumptions: pd.DataFrame,
    market: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    market_lookup = market.set_index("ticker")
    rows: list[dict[str, object]] = []
    for dimension, (x_values, y_values) in SURFACE_GRIDS.items():
        for ticker, ticker_assumptions in assumptions.groupby("ticker", sort=True):
            current = market_lookup.loc[ticker]
            for x in x_values:
                for y in y_values:
                    result = evaluate_weighted_value(
                        ticker_assumptions, current,
                        **_surface_kwargs(dimension, x, y),
                    )
                    rows.append({
                        "surface": dimension,
                        "ticker": ticker,
                        "x_value_pct": x,
                        "y_value_pct": y,
                        **result,
                        "production_eligible": False,
                    })
    detail = pd.DataFrame(rows)
    sector = (
        detail.groupby(["surface", "x_value_pct", "y_value_pct"], as_index=False)
        .agg(
            median_value_gap_pct=("value_gap_pct", "median"),
            q25_value_gap_pct=("value_gap_pct", lambda values: values.quantile(0.25)),
            q75_value_gap_pct=("value_gap_pct", lambda values: values.quantile(0.75)),
            tickers_below_market=("value_gap_pct", lambda values: values.lt(0).sum()),
            tickers_above_market=("value_gap_pct", lambda values: values.gt(0).sum()),
        )
    )
    return detail, sector


def _bisect(
    function: Callable[[float], float],
    lower: float,
    upper: float,
    tolerance: float = 1e-8,
) -> tuple[float | None, str, float]:
    low_value = function(lower)
    high_value = function(upper)
    if not np.isfinite(low_value) or not np.isfinite(high_value):
        return None, "NONFINITE_DOMAIN_ENDPOINT", np.nan
    if low_value == 0:
        return lower, "SOLVED", 0.0
    if high_value == 0:
        return upper, "SOLVED", 0.0
    if np.sign(low_value) == np.sign(high_value):
        nearest = lower if abs(low_value) < abs(high_value) else upper
        residual = low_value if nearest == lower else high_value
        return None, "UNBRACKETED_NO_SOLUTION_IN_DOMAIN", residual
    low, high = lower, upper
    for _ in range(100):
        midpoint = (low + high) / 2.0
        value = function(midpoint)
        if abs(value) <= tolerance:
            return midpoint, "SOLVED", value
        if np.sign(value) == np.sign(low_value):
            low = midpoint
            low_value = value
        else:
            high = midpoint
    solution = (low + high) / 2.0
    return solution, "SOLVED", function(solution)


def build_iso_value_curves(
    assumptions: pd.DataFrame,
    market: pd.DataFrame,
) -> pd.DataFrame:
    market_lookup = market.set_index("ticker")
    specifications = (
        (
            "TERMINAL_MARGIN_X_WACC", "terminal_margin_center_pct",
            tuple(np.arange(12.0, 40.1, 2.0)), "wacc_center_pct", 4.5, 15.0,
        ),
        (
            "GROWTH_X_OPERATING_MARGIN", "growth_center_pct",
            (-10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0),
            "operating_margin_center_pct", -10.0, 60.0,
        ),
        (
            "GROWTH_X_NORMALIZED_ROIC", "growth_center_pct",
            (-10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0),
            "normalized_roic_center_pct", 2.0, 50.0,
        ),
    )
    rows: list[dict[str, object]] = []
    for ticker, ticker_assumptions in assumptions.groupby("ticker", sort=True):
        current = market_lookup.loc[ticker]
        for surface, fixed_name, fixed_values, solved_name, low, high in specifications:
            for fixed_value in fixed_values:
                def objective(solved_value: float) -> float:
                    return evaluate_weighted_value(
                        ticker_assumptions,
                        current,
                        **{fixed_name: fixed_value, solved_name: solved_value},
                    )["value_gap_pct"]

                solution, status, residual = _bisect(objective, low, high)
                rows.append({
                    "surface": surface,
                    "ticker": ticker,
                    "fixed_variable": fixed_name,
                    "fixed_value_pct": fixed_value,
                    "solved_variable": solved_name,
                    "solved_value_pct": solution,
                    "solver_status": status,
                    "residual_value_gap_pct": residual,
                    "domain_lower_pct": low,
                    "domain_upper_pct": high,
                    "interpretation": "ONE_POINT_ON_NON_UNIQUE_ISO_VALUE_CURVE",
                })
    return pd.DataFrame(rows)


def build_conditional_margin_wacc_tradeoffs(
    assumptions: pd.DataFrame,
    market: pd.DataFrame,
    economics: pd.DataFrame,
) -> pd.DataFrame:
    market_lookup = market.set_index("ticker")
    economics_lookup = economics.set_index("ticker")
    rows: list[dict[str, object]] = []
    for ticker, ticker_assumptions in assumptions.groupby("ticker", sort=True):
        current = market_lookup.loc[ticker]
        for label in ("q25", "q50", "q75"):
            margin = float(
                economics_lookup.loc[ticker, f"normalized_margin_{label}_pct"]
            )

            def objective(wacc: float) -> float:
                return evaluate_weighted_value(
                    ticker_assumptions,
                    current,
                    terminal_margin_center_pct=margin,
                    wacc_center_pct=wacc,
                )["value_gap_pct"]

            solution, status, residual = _bisect(objective, 4.5, 15.0)
            rows.append({
                "ticker": ticker,
                "through_cycle_margin_reference": label.upper(),
                "terminal_margin_pct": margin,
                "market_equivalent_wacc_pct": solution,
                "solver_status": status,
                "residual_value_gap_pct": residual,
                "interpretation": "CONDITIONAL_COMBINATION_NOT_UNIQUE_MARKET_EXPECTATION",
            })
    return pd.DataFrame(rows)
