from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..data.cutoff import quarter_cutoff_date


REQUIRED_CONSENSUS_COLUMNS = {
    "ticker",
    "quarter",
    "snapshot_date",
    "consensus_revenue",
}


def _snapshot_from_path(path: Path) -> pd.Timestamp:
    match = re.search(r"snapshot_date=(\d{4}-\d{2}-\d{2})", str(path))
    return pd.Timestamp(match.group(1)) if match else pd.NaT


def _quarter_from_date(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else str(parsed.to_period("Q"))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _arcana_fmp_rows(base: Path, tickers: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    directory = base / "fmp" / "analyst-estimates" / "period=quarter"
    for ticker in tickers:
        for path in directory.glob(f"snapshot_date=*/ticker={ticker}.json"):
            payload = _read_json(path)
            snapshot = _snapshot_from_path(path)
            for estimate in payload.get("data", []):
                quarter = _quarter_from_date(estimate.get("date"))
                revenue = pd.to_numeric(estimate.get("revenueAvg"), errors="coerce")
                if quarter is None or not np.isfinite(revenue):
                    continue
                rows.append(
                    {
                        "ticker": ticker,
                        "quarter": quarter,
                        "snapshot_date": snapshot,
                        "consensus_revenue": float(revenue),
                        "consensus_revenue_low": pd.to_numeric(
                            estimate.get("revenueLow"), errors="coerce"
                        ),
                        "consensus_revenue_high": pd.to_numeric(
                            estimate.get("revenueHigh"), errors="coerce"
                        ),
                        "analyst_count": pd.to_numeric(
                            estimate.get("numAnalystsRevenue"), errors="coerce"
                        ),
                        "provider": "FMP",
                        "source_path": str(path),
                    }
                )
    return rows


def _arcana_alpha_vantage_rows(
    base: Path, tickers: tuple[str, ...]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    directory = base / "alpha-vantage" / "earnings-estimates"
    for ticker in tickers:
        for path in directory.glob(f"snapshot_date=*/ticker={ticker}.json"):
            payload = _read_json(path)
            snapshot = _snapshot_from_path(path)
            for estimate in payload.get("estimates", []):
                if "quarter" not in str(estimate.get("horizon", "")).lower():
                    continue
                quarter = _quarter_from_date(estimate.get("date"))
                revenue = pd.to_numeric(
                    estimate.get("revenue_estimate_average"), errors="coerce"
                )
                if quarter is None or not np.isfinite(revenue):
                    continue
                rows.append(
                    {
                        "ticker": ticker,
                        "quarter": quarter,
                        "snapshot_date": snapshot,
                        "consensus_revenue": float(revenue),
                        "consensus_revenue_low": pd.to_numeric(
                            estimate.get("revenue_estimate_low"), errors="coerce"
                        ),
                        "consensus_revenue_high": pd.to_numeric(
                            estimate.get("revenue_estimate_high"), errors="coerce"
                        ),
                        "analyst_count": pd.to_numeric(
                            estimate.get("revenue_estimate_analyst_count"), errors="coerce"
                        ),
                        "provider": "ALPHA_VANTAGE",
                        "source_path": str(path),
                    }
                )
    return rows


def _arcana_finnworlds_coverage(
    base: Path, tickers: tuple[str, ...]
) -> pd.DataFrame:
    """Record Finnworlds coverage; its local dataset has ratings, not revenue."""
    rows: list[dict[str, Any]] = []
    directory = base / "finnworlds" / "company-ratings"
    for ticker in tickers:
        for path in directory.glob(f"snapshot_date=*/ticker={ticker}.json"):
            payload = _read_json(path)
            rows.append(
                {
                    "provider": "FINNWORLDS",
                    "ticker": ticker,
                    "snapshot_date": _snapshot_from_path(path),
                    "dataset": payload.get("dataset", "COMPANY_RATINGS"),
                    "revenue_consensus_available": False,
                    "status": "RATINGS_ONLY_NOT_USED_AS_REVENUE_CONSENSUS",
                    "source_path": str(path),
                }
            )
    return pd.DataFrame(rows)


def load_arcana_consensus(
    base: Path,
    tickers: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize Arcana Alpha Vantage/FMP estimates and Finnworlds coverage."""
    rows = _arcana_fmp_rows(base, tickers) + _arcana_alpha_vantage_rows(base, tickers)
    columns = [
        "ticker",
        "quarter",
        "snapshot_date",
        "consensus_revenue",
        "consensus_revenue_low",
        "consensus_revenue_high",
        "analyst_count",
        "provider",
        "source_path",
    ]
    return pd.DataFrame(rows, columns=columns), _arcana_finnworlds_coverage(base, tickers)


def load_consensus(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=sorted(REQUIRED_CONSENSUS_COLUMNS))
    frame = pd.read_csv(path)
    missing = REQUIRED_CONSENSUS_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"consensus input is missing columns: {sorted(missing)}")
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["quarter"] = frame["quarter"].astype(str)
    frame["snapshot_date"] = pd.to_datetime(frame["snapshot_date"], errors="coerce")
    frame["consensus_revenue"] = pd.to_numeric(
        frame["consensus_revenue"], errors="coerce"
    )
    frame["provider"] = (
        frame["source"].fillna("MANUAL") if "source" in frame else "MANUAL"
    )
    frame["consensus_revenue_low"] = frame["consensus_revenue"]
    frame["consensus_revenue_high"] = frame["consensus_revenue"]
    frame["analyst_count"] = np.nan
    frame["source_path"] = str(path)
    return frame


def point_in_time_consensus(
    consensus: pd.DataFrame,
    day_of_quarter: int,
) -> pd.DataFrame:
    if consensus.empty:
        return consensus.copy()
    result = consensus.copy()
    result["forecast_cutoff_date"] = result["quarter"].map(
        lambda quarter: quarter_cutoff_date(quarter, day_of_quarter)
    )
    eligible = result.loc[
        result["snapshot_date"].notna()
        & result["snapshot_date"].le(result["forecast_cutoff_date"])
    ]
    latest_provider = (
        eligible.sort_values("snapshot_date")
        .groupby(["provider", "ticker", "quarter"], as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
    if latest_provider.empty:
        return latest_provider
    aggregated = (
        latest_provider.groupby(["ticker", "quarter"], as_index=False)
        .agg(
            snapshot_date=("snapshot_date", "max"),
            consensus_revenue=("consensus_revenue", "median"),
            consensus_revenue_low=("consensus_revenue_low", "min"),
            consensus_revenue_high=("consensus_revenue_high", "max"),
            analyst_count=("analyst_count", "sum"),
            provider_count=("provider", "nunique"),
            providers=("provider", lambda values: ",".join(sorted(set(values)))),
        )
    )
    aggregated["forecast_cutoff_date"] = aggregated["quarter"].map(
        lambda quarter: quarter_cutoff_date(quarter, day_of_quarter)
    )
    return aggregated


def current_model_vs_consensus(
    nowcast: pd.DataFrame,
    consensus: pd.DataFrame,
) -> pd.DataFrame:
    model = nowcast.rename(columns={"nowcast_quarter": "quarter"}).copy()
    model["quarter"] = model["quarter"].astype(str)
    model["model_revenue"] = model["predicted_revenue_B"] * 1e9
    comparison = model.merge(consensus, on=["ticker", "quarter"], how="left")
    comparison["model_minus_consensus"] = (
        comparison["model_revenue"] - comparison["consensus_revenue"]
    )
    comparison["model_minus_consensus_pct"] = (
        comparison["model_minus_consensus"] / comparison["consensus_revenue"] * 100.0
    )
    expected = [
        "ticker", "quarter", "model_revenue", "consensus_revenue",
        "consensus_revenue_low", "consensus_revenue_high", "provider_count",
        "providers", "snapshot_date", "model_minus_consensus",
        "model_minus_consensus_pct",
    ]
    for column in expected:
        if column not in comparison:
            comparison[column] = np.nan
    return comparison[expected]


def evaluate_model_vs_consensus(
    model_predictions: pd.DataFrame,
    consensus: pd.DataFrame,
    minimum_observations: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_model = {"ticker", "quarter", "predicted_revenue", "actual_revenue"}
    missing = required_model.difference(model_predictions.columns)
    if missing:
        raise ValueError(f"model predictions are missing columns: {sorted(missing)}")
    columns = ["ticker", "quarter", "snapshot_date", "consensus_revenue"]
    if consensus.empty or any(column not in consensus for column in columns):
        comparison = pd.DataFrame()
    else:
        comparison = model_predictions.merge(
            consensus[columns], on=["ticker", "quarter"], how="inner"
        )
    if not comparison.empty:
        comparison = comparison.dropna(
            subset=["predicted_revenue", "actual_revenue", "consensus_revenue"]
        ).copy()
    if comparison.empty:
        summary = pd.DataFrame([{
            "status": "NO_MATCHED_OBSERVATIONS", "observations": 0,
            "model_mape_pct": np.nan, "consensus_mape_pct": np.nan,
            "model_win_rate": np.nan, "surprise_direction_accuracy": np.nan,
            "statistical_test_status": f"NEEDS_{minimum_observations}_OBSERVATIONS",
        }])
        return comparison, summary
    comparison["model_ape_pct"] = (
        (comparison["predicted_revenue"] / comparison["actual_revenue"] - 1.0).abs() * 100.0
    )
    comparison["consensus_ape_pct"] = (
        (comparison["consensus_revenue"] / comparison["actual_revenue"] - 1.0).abs() * 100.0
    )
    comparison["model_wins"] = comparison["model_ape_pct"] < comparison["consensus_ape_pct"]
    comparison["surprise_direction_correct"] = np.sign(
        comparison["predicted_revenue"] - comparison["consensus_revenue"]
    ) == np.sign(comparison["actual_revenue"] - comparison["consensus_revenue"])
    observations = len(comparison)
    summary = pd.DataFrame([{
        "status": "READY" if observations >= minimum_observations else "TRACKING",
        "observations": observations,
        "model_mape_pct": float(comparison["model_ape_pct"].mean()),
        "consensus_mape_pct": float(comparison["consensus_ape_pct"].mean()),
        "model_win_rate": float(comparison["model_wins"].mean()),
        "surprise_direction_accuracy": float(comparison["surprise_direction_correct"].mean()),
        "statistical_test_status": (
            "ELIGIBLE_FOR_DM_TEST" if observations >= minimum_observations
            else f"NEEDS_{minimum_observations - observations}_MORE_OBSERVATIONS"
        ),
    }])
    return comparison, summary
