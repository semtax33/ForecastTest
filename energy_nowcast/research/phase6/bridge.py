from __future__ import annotations

from collections.abc import Iterable
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from ...data.cutoff import quarter_cutoff_date
from ..v351.revenue import load_companyfacts_quarterly_revenue


def load_target_hierarchy(config_path: Path) -> pd.DataFrame:
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    hierarchy = pd.DataFrame(config["target_hierarchy"])
    hierarchy["architecture"] = "ANCHOR_TO_CONDITIONAL_BRIDGE"
    hierarchy["fixed_ratio_reverse_calculation_allowed"] = bool(
        config["fixed_ratio_reverse_calculation_allowed"]
    )
    hierarchy["scenario_bridge_required"] = bool(config["scenario_bridge_required"])
    hierarchy["production_eligible"] = False
    return hierarchy


def select_segment_predictions(
    predictions: pd.DataFrame,
    passed_segments: Iterable[str],
) -> pd.DataFrame:
    passed = set(passed_segments)
    selected = predictions.copy()
    selected["selected_route"] = np.where(
        selected["segment"].isin(passed),
        "RIDGE_ECONOMIC_DRIVER_CANDIDATE",
        "PRIOR_YEAR_ZERO_CHANGE_BASELINE",
    )
    selected["selected_change"] = np.where(
        selected["segment"].isin(passed),
        selected["candidate_prediction"],
        0.0,
    )
    selected["selected_target_value"] = (
        selected["prior_year_target_value"] + selected["selected_change"]
    )
    selected["production_eligible"] = False
    return selected


def _scenario_quantiles(
    values: pd.Series,
    lower_quantile: float,
    base_quantile: float,
    upper_quantile: float,
) -> tuple[float, float, float]:
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return np.nan, np.nan, np.nan
    return (
        float(clean.quantile(lower_quantile)),
        float(clean.quantile(base_quantile)),
        float(clean.quantile(upper_quantile)),
    )


def build_midstream_ebitda_revenue_bridge(
    predictions: pd.DataFrame,
    quarterly_ebitda: pd.DataFrame,
    companyfacts_root: Path,
    *,
    trailing_quarters: int = 12,
    minimum_history: int = 8,
    lower_quantile: float = 0.20,
    base_quantile: float = 0.50,
    upper_quantile: float = 0.80,
    cutoff_day: int = 61,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Bridge EBITDA to a revenue range using only PIT historical margin regimes."""
    targets = predictions.loc[
        predictions["forecast_target"].eq("ADJUSTED_EBITDA_NON_GAAP")
        & predictions["validation"].str.contains("TIME", na=False)
    ].copy()
    tickers = tuple(sorted(targets["ticker"].unique()))
    revenue = load_companyfacts_quarterly_revenue(companyfacts_root, tickers)
    revenue = revenue[["ticker", "quarter", "revenue", "filing_date"]].rename(
        columns={"filing_date": "revenue_filing_date"}
    )
    history = quarterly_ebitda.rename(columns={"report_quarter": "quarter"}).merge(
        revenue, on=["ticker", "quarter"], how="inner"
    )
    history["available_at"] = pd.to_datetime(history["available_at"], errors="coerce")
    history["revenue_filing_date"] = pd.to_datetime(
        history["revenue_filing_date"], errors="coerce"
    )
    history["adjusted_ebitda_usd"] = history["adjusted_ebitda_usd_million"] * 1e6
    history["ebitda_margin"] = history["adjusted_ebitda_usd"] / history["revenue"]
    history["margin_available_at"] = history[["available_at", "revenue_filing_date"]].max(axis=1)
    history["quarter_ordinal"] = history["quarter"].map(
        lambda value: int(pd.Period(value, freq="Q").ordinal)
    )
    history = history.loc[history["ebitda_margin"].gt(0)].copy()

    rows: list[dict[str, object]] = []
    for target in targets.itertuples(index=False):
        target_ordinal = int(pd.Period(target.quarter, freq="Q").ordinal)
        cutoff = quarter_cutoff_date(str(target.quarter), cutoff_day)
        eligible = history.loc[
            history["ticker"].eq(target.ticker)
            & history["quarter_ordinal"].lt(target_ordinal)
            & pd.to_datetime(history["margin_available_at"], errors="coerce").le(cutoff)
        ].sort_values("quarter_ordinal").tail(trailing_quarters)
        low_margin, base_margin, high_margin = _scenario_quantiles(
            eligible["ebitda_margin"], lower_quantile, base_quantile, upper_quantile
        )
        actual_row = history.loc[
            history["ticker"].eq(target.ticker) & history["quarter"].eq(target.quarter)
        ]
        actual_margin = float(actual_row["ebitda_margin"].iloc[-1]) if len(actual_row) else np.nan
        actual_revenue = float(actual_row["revenue"].iloc[-1]) if len(actual_row) else np.nan
        predicted_ebitda = float(target.predicted_value)
        ready = len(eligible) >= minimum_history and all(
            np.isfinite(value) and value > 0
            for value in (low_margin, base_margin, high_margin, predicted_ebitda)
        )
        actual_ready = (
            np.isfinite(actual_margin) and actual_margin > 0
            and np.isfinite(actual_revenue) and actual_revenue > 0
        )
        revenue_low = predicted_ebitda / high_margin if ready else np.nan
        revenue_base = predicted_ebitda / base_margin if ready else np.nan
        revenue_high = predicted_ebitda / low_margin if ready else np.nan
        actual_ebitda = float(target.actual_value)
        anchor_only = (
            predicted_ebitda / actual_margin - actual_revenue
            if ready and actual_ready
            else np.nan
        )
        bridge_only = (
            actual_ebitda / base_margin - actual_revenue
            if ready and actual_ready else np.nan
        )
        total_error = revenue_base - actual_revenue if ready and actual_ready else np.nan
        rows.append(
            {
                "ticker": target.ticker,
                "quarter": target.quarter,
                "primary_anchor": "ADJUSTED_EBITDA_NON_GAAP",
                "secondary_target": "GAAP_REVENUE_RANGE",
                "anchor_route": target.research_route_model,
                "bridge_method": "PIT_TRAILING_MARGIN_REGIME_QUANTILES",
                "fixed_margin_used": False,
                "guidance_adjustment": 0.0,
                "history_observations": len(eligible),
                "history_first_quarter": eligible["quarter"].min() if len(eligible) else pd.NA,
                "history_last_quarter": eligible["quarter"].max() if len(eligible) else pd.NA,
                "forecast_cutoff_date": cutoff,
                "margin_bear_low": low_margin,
                "margin_base": base_margin,
                "margin_bull_high": high_margin,
                "predicted_ebitda_usd": predicted_ebitda,
                "actual_ebitda_usd": actual_ebitda,
                "actual_margin": actual_margin,
                "actual_revenue_usd": actual_revenue,
                "revenue_scenario_low_usd": revenue_low,
                "revenue_scenario_base_usd": revenue_base,
                "revenue_scenario_high_usd": revenue_high,
                "anchor_only_revenue_error_usd": anchor_only,
                "bridge_only_revenue_error_usd": bridge_only,
                "total_revenue_error_usd": total_error,
                "interaction_error_usd": (
                    total_error - anchor_only - bridge_only
                    if all(np.isfinite(value) for value in (total_error, anchor_only, bridge_only))
                    else np.nan
                ),
                "scenario_covered": (
                    bool(revenue_low <= actual_revenue <= revenue_high)
                    if ready and actual_ready else np.nan
                ),
                "bridge_status": "AVAILABLE" if ready else "INSUFFICIENT_PIT_MARGIN_HISTORY",
                "attribution_status": (
                    "EVALUABLE" if ready and actual_ready
                    else "ACTUAL_REVENUE_UNAVAILABLE" if ready
                    else "BRIDGE_UNAVAILABLE"
                ),
                "production_eligible": False,
            }
        )
    bridge = pd.DataFrame(rows)
    available = bridge.loc[bridge["bridge_status"].eq("AVAILABLE")].copy()
    valid = bridge.loc[bridge["attribution_status"].eq("EVALUABLE")].copy()
    denominator = valid["actual_revenue_usd"].abs().sum()
    summary = pd.DataFrame(
        [{
            "bridge": "MIDSTREAM_ADJUSTED_EBITDA_TO_REVENUE_RANGE",
            "forecasts": len(bridge),
            "available_forecasts": len(available),
            "evaluable_forecasts": len(valid),
            "aggregate_revenue_wape_pct": (
                float(valid["total_revenue_error_usd"].abs().sum() / denominator * 100.0)
                if denominator > 0 else np.nan
            ),
            "median_revenue_ape_pct": (
                float((valid["total_revenue_error_usd"].abs() / valid["actual_revenue_usd"].abs() * 100.0).median())
                if len(valid) else np.nan
            ),
            "scenario_coverage": float(valid["scenario_covered"].mean()) if len(valid) else np.nan,
            "fixed_margin_used": False,
            "production_eligible": False,
        }]
    )
    return bridge, summary


def build_integrated_consolidated_earnings_bridge(
    selected_predictions: pd.DataFrame,
    segment_earnings: pd.DataFrame,
    revenue: pd.DataFrame,
    net_income: pd.DataFrame,
    *,
    trailing_quarters: int = 12,
    minimum_history: int = 8,
    lower_quantile: float = 0.20,
    base_quantile: float = 0.50,
    upper_quantile: float = 0.80,
    cutoff_day: int = 61,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add a PIT corporate/unmodeled scenario to covered segment earnings."""
    expected = {"CVX": {"upstream", "downstream"}, "XOM": {"upstream", "downstream", "chemicals"}}
    actual_segments = segment_earnings.rename(columns={"report_quarter": "quarter"}).copy()
    actual_segments["segment_contribution_usd"] = actual_segments["segment_earnings_usd_million"] * 1e6
    complete_rows: list[dict[str, object]] = []
    for (ticker, quarter), group in actual_segments.groupby(["ticker", "quarter"]):
        if set(group["segment"]) != expected.get(str(ticker), set()):
            continue
        complete_rows.append({
            "ticker": ticker,
            "quarter": quarter,
            "covered_segment_earnings_usd": float(group["segment_contribution_usd"].sum()),
            "segments": ";".join(sorted(group["segment"])),
            "segment_available_at": pd.to_datetime(group["available_at"], errors="coerce").max(),
        })
    covered = pd.DataFrame(complete_rows)
    consolidated = covered.merge(
        revenue[["ticker", "quarter", "revenue", "filing_date"]].rename(columns={"filing_date": "revenue_filing_date"}),
        on=["ticker", "quarter"], how="inner"
    ).merge(
        net_income[["ticker", "quarter", "net_income_usd", "filing_date"]].rename(columns={"filing_date": "net_income_filing_date"}),
        on=["ticker", "quarter"], how="inner"
    )
    for column in (
        "segment_available_at", "revenue_filing_date", "net_income_filing_date"
    ):
        consolidated[column] = pd.to_datetime(consolidated[column], errors="coerce")
    consolidated["covered_segment_margin_pct"] = consolidated["covered_segment_earnings_usd"] / consolidated["revenue"] * 100.0
    consolidated["net_income_margin_pct"] = consolidated["net_income_usd"] / consolidated["revenue"] * 100.0
    consolidated["corporate_unmodeled_bridge_pct"] = consolidated["net_income_margin_pct"] - consolidated["covered_segment_margin_pct"]
    consolidated["bridge_available_at"] = consolidated[["segment_available_at", "revenue_filing_date", "net_income_filing_date"]].max(axis=1)
    consolidated["quarter_ordinal"] = consolidated["quarter"].map(lambda value: int(pd.Period(value, freq="Q").ordinal))

    predictions = (
        selected_predictions.groupby(["ticker", "quarter"], as_index=False)
        .agg(
            predicted_covered_segment_margin_pct=("selected_target_value", "sum"),
            actual_covered_segment_margin_pct=("target_value", "sum"),
            segment_routes=("selected_route", lambda values: ";".join(sorted(set(values)))),
            segment_count=("segment", "nunique"),
        )
    )
    rows: list[dict[str, object]] = []
    for target in predictions.itertuples(index=False):
        if int(target.segment_count) != len(expected.get(str(target.ticker), set())):
            continue
        target_ordinal = int(pd.Period(target.quarter, freq="Q").ordinal)
        cutoff = quarter_cutoff_date(str(target.quarter), cutoff_day)
        eligible = consolidated.loc[
            consolidated["ticker"].eq(target.ticker)
            & consolidated["quarter_ordinal"].lt(target_ordinal)
            & pd.to_datetime(consolidated["bridge_available_at"], errors="coerce").le(cutoff)
        ].sort_values("quarter_ordinal").tail(trailing_quarters)
        low, base, high = _scenario_quantiles(
            eligible["corporate_unmodeled_bridge_pct"], lower_quantile, base_quantile, upper_quantile
        )
        actual = consolidated.loc[
            consolidated["ticker"].eq(target.ticker) & consolidated["quarter"].eq(target.quarter)
        ]
        if actual.empty:
            continue
        actual = actual.iloc[-1]
        ready = len(eligible) >= minimum_history and all(np.isfinite(value) for value in (low, base, high))
        predicted_covered = float(target.predicted_covered_segment_margin_pct)
        actual_covered = float(actual["covered_segment_margin_pct"])
        actual_bridge = float(actual["corporate_unmodeled_bridge_pct"])
        actual_total = float(actual["net_income_margin_pct"])
        predicted_total = predicted_covered + base if ready else np.nan
        rows.append({
            "ticker": target.ticker,
            "quarter": target.quarter,
            "primary_anchor": "GAAP_SEGMENT_EARNINGS_CONTRIBUTION_MARGIN",
            "secondary_target": "CONSOLIDATED_NET_INCOME_MARGIN_RANGE",
            "segments": actual["segments"],
            "segment_routes": target.segment_routes,
            "bridge_method": "PIT_TRAILING_CORPORATE_UNMODELED_QUANTILES",
            "fixed_ratio_used": False,
            "guidance_adjustment": 0.0,
            "history_observations": len(eligible),
            "history_first_quarter": eligible["quarter"].min() if len(eligible) else pd.NA,
            "history_last_quarter": eligible["quarter"].max() if len(eligible) else pd.NA,
            "forecast_cutoff_date": cutoff,
            "predicted_covered_segment_margin_pct": predicted_covered,
            "actual_covered_segment_margin_pct": actual_covered,
            "bridge_scenario_low_pct": low,
            "bridge_scenario_base_pct": base,
            "bridge_scenario_high_pct": high,
            "actual_bridge_pct": actual_bridge,
            "net_income_margin_scenario_low_pct": predicted_covered + low if ready else np.nan,
            "net_income_margin_scenario_base_pct": predicted_total,
            "net_income_margin_scenario_high_pct": predicted_covered + high if ready else np.nan,
            "actual_net_income_margin_pct": actual_total,
            "anchor_error_pct": predicted_covered - actual_covered,
            "bridge_error_pct": base - actual_bridge if ready else np.nan,
            "total_error_pct": predicted_total - actual_total if ready else np.nan,
            "scenario_covered": (
                bool(predicted_covered + low <= actual_total <= predicted_covered + high)
                if ready else np.nan
            ),
            "bridge_status": "AVAILABLE" if ready else "INSUFFICIENT_PIT_BRIDGE_HISTORY",
            "production_eligible": False,
        })
    bridge = pd.DataFrame(rows)
    valid = bridge.loc[bridge["bridge_status"].eq("AVAILABLE")].copy()
    summary = pd.DataFrame([{
        "bridge": "INTEGRATED_SEGMENTS_TO_CONSOLIDATED_NET_INCOME_MARGIN",
        "forecasts": len(bridge),
        "available_forecasts": len(valid),
        "mean_absolute_anchor_error_pct_points": float(valid["anchor_error_pct"].abs().mean()) if len(valid) else np.nan,
        "mean_absolute_bridge_error_pct_points": float(valid["bridge_error_pct"].abs().mean()) if len(valid) else np.nan,
        "mean_absolute_total_error_pct_points": float(valid["total_error_pct"].abs().mean()) if len(valid) else np.nan,
        "scenario_coverage": float(valid["scenario_covered"].mean()) if len(valid) else np.nan,
        "fixed_ratio_used": False,
        "production_eligible": False,
    }])
    return bridge, summary
