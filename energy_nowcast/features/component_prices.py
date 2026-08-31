from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..config import ModelConfig, ProjectPaths
from ..data.cutoff import quarter_cutoff_date


def _load_company_sources(
    paths: ProjectPaths,
    ticker: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    assert paths.data_lake is not None
    if ticker == "EOG":
        actual_path = paths.data_lake / "energy_v3_2_7_actual_EOG.csv"
        guidance_path = paths.data_lake / "energy_v3_2_7_guidance_EOG.csv"
        actual = pd.read_csv(actual_path).rename(
            columns={
                "release_date": "source_release_date",
                "oil_production": "oil",
                "total_production": "total",
            }
        )
        guidance = pd.read_csv(guidance_path).rename(
            columns={
                "release_date": "source_release_date",
                "guidance_oil_production": "oil",
                "guidance_total_production": "total",
            }
        )
    else:
        actual_path = paths.data_lake / f"energy_v3_2_1_actual_selected_{ticker}.csv"
        guidance_path = (
            paths.data_lake / f"energy_v3_2_1_guidance_selected_{ticker}.csv"
        )
        actual = pd.read_csv(actual_path).rename(
            columns={
                "filing_date": "source_release_date",
                "oil_production": "oil",
                "total_production": "total",
            }
        )
        guidance = pd.read_csv(guidance_path).rename(
            columns={
                "filing_date": "source_release_date",
                "guidance_oil_production": "oil",
                "guidance_total_production": "total",
            }
        )
    guidance = guidance.rename(columns={"target_quarter": "quarter"})
    for frame in (actual, guidance):
        frame["quarter"] = frame["quarter"].astype(str)
        frame["source_release_date"] = pd.to_datetime(
            frame["source_release_date"], errors="coerce"
        )
        frame["total"] = pd.to_numeric(frame["total"], errors="coerce")
        frame["oil"] = pd.to_numeric(frame["oil"], errors="coerce")
    return actual, guidance


def _last_row_available(
    frame: pd.DataFrame,
    quarter: pd.Period,
    cutoff: pd.Timestamp,
) -> pd.Series | None:
    eligible = frame.loc[
        frame["quarter"].eq(str(quarter))
        & frame["source_release_date"].notna()
        & frame["source_release_date"].le(cutoff)
    ].sort_values("source_release_date")
    return None if eligible.empty else eligible.iloc[-1]


def _price_lookup(prices: pd.DataFrame, quarter: pd.Period) -> pd.Series | None:
    selected = prices.loc[prices["quarter"].astype(str).eq(str(quarter))]
    return None if selected.empty else selected.iloc[-1]


def _safe_log_ratio(current: float, prior: float) -> float:
    if not np.isfinite(current) or not np.isfinite(prior) or current <= 0 or prior <= 0:
        return float("nan")
    return float(100.0 * np.log(current / prior))


def _estimated_oil_share(
    actual: pd.DataFrame,
    cutoff: pd.Timestamp,
    fallback: float,
) -> float:
    eligible = actual.loc[
        actual["source_release_date"].notna()
        & actual["source_release_date"].le(cutoff)
        & actual["oil"].notna()
        & actual["total"].gt(0)
    ].copy()
    if eligible.empty:
        return float(np.clip(fallback, 0.05, 0.95))
    share = float((eligible.iloc[-1]["oil"] / eligible.iloc[-1]["total"]))
    return float(np.clip(share, 0.05, 0.95))


def _component_row(
    ticker: str,
    quarter: pd.Period,
    actual: pd.DataFrame,
    guidance: pd.DataFrame,
    prices: pd.DataFrame,
    oil_share_fallback: float,
    config: ModelConfig,
) -> dict[str, object] | None:
    cutoff = quarter_cutoff_date(quarter, config.release_cutoff_day_of_quarter)
    current = _last_row_available(guidance, quarter, cutoff)
    if current is None or not np.isfinite(current["total"]):
        return None

    prior_quarter = quarter - 4
    prior = _last_row_available(actual, prior_quarter, cutoff)
    prior_source = "ACTUAL"
    if prior is None or not np.isfinite(prior["total"]):
        prior = _last_row_available(guidance, prior_quarter, cutoff)
        prior_source = "GUIDANCE_FALLBACK"
    if prior is None or not np.isfinite(prior["total"]):
        return None

    oil_share = _estimated_oil_share(actual, cutoff, oil_share_fallback)
    current_oil_imputed = not np.isfinite(current["oil"])
    prior_oil_imputed = not np.isfinite(prior["oil"])
    current_total = float(current["total"])
    prior_total = float(prior["total"])
    current_oil = (
        current_total * oil_share if current_oil_imputed else float(current["oil"])
    )
    prior_oil = prior_total * oil_share if prior_oil_imputed else float(prior["oil"])
    current_non_oil = max(current_total - current_oil, 0.0)
    prior_non_oil = max(prior_total - prior_oil, 0.0)

    current_price = _price_lookup(prices, quarter)
    prior_price = _price_lookup(prices, prior_quarter)
    if current_price is None or prior_price is None:
        return None
    current_non_oil_price = 0.5 * float(current_price["propane_price_bbl"]) + 0.5 * (
        float(current_price["henry_price"]) * 6.0
    )
    prior_non_oil_price = 0.5 * float(prior_price["propane_price_bbl"]) + 0.5 * (
        float(prior_price["henry_price"]) * 6.0
    )
    current_driver = current_oil * float(current_price["wti_price"]) + (
        current_non_oil * current_non_oil_price
    )
    prior_driver = prior_oil * float(prior_price["wti_price"]) + (
        prior_non_oil * prior_non_oil_price
    )
    imputation_count = int(current_oil_imputed) + int(prior_oil_imputed)
    source_quality = 1.0 - 0.125 * imputation_count
    if prior_source != "ACTUAL":
        source_quality -= 0.10
    return {
        "ticker": ticker,
        "quarter": str(quarter),
        "forecast_cutoff_date": cutoff,
        "current_source_release_date": current["source_release_date"],
        "prior_volume_source": prior_source,
        "current_total_boe": current_total,
        "current_oil": current_oil,
        "current_non_oil_boe": current_non_oil,
        "prior_total_boe": prior_total,
        "prior_oil": prior_oil,
        "prior_non_oil_boe": prior_non_oil,
        "current_wti": float(current_price["wti_price"]),
        "prior_wti": float(prior_price["wti_price"]),
        "current_non_oil_price": current_non_oil_price,
        "prior_non_oil_price": prior_non_oil_price,
        "component_structural_log_yoy": _safe_log_ratio(
            current_driver, prior_driver
        ),
        "oil_component_imputed": current_oil_imputed or prior_oil_imputed,
        "source_quality_score": max(source_quality, 0.35),
        "component_model_type": "OIL_PLUS_NON_OIL_PRICE_X_VOLUME",
    }


def build_component_candidates(
    target_quarters: pd.DataFrame,
    prices: pd.DataFrame,
    structural_panel: pd.DataFrame,
    config: ModelConfig,
    paths: ProjectPaths,
) -> pd.DataFrame:
    """Generalize price x volume candidates to COP/FANG/DVN with explicit imputation."""
    records: list[dict[str, object]] = []
    for ticker in config.component_tickers:
        if ticker == "EOG":
            continue
        actual, guidance = _load_company_sources(paths, ticker)
        ticker_targets = target_quarters.loc[target_quarters["ticker"].eq(ticker)]
        for quarter_value in ticker_targets["quarter"].astype(str).unique():
            quarter = pd.Period(quarter_value, freq="Q")
            fallback_rows = structural_panel.loc[
                structural_panel["ticker"].eq(ticker)
                & structural_panel["quarter"].astype(str).eq(str(quarter)),
                "oil_share_l1",
            ]
            fallback = float(
                pd.to_numeric(fallback_rows, errors="coerce").dropna().iloc[-1]
            ) if not pd.to_numeric(fallback_rows, errors="coerce").dropna().empty else 0.55
            row = _component_row(
                ticker,
                quarter,
                actual,
                guidance,
                prices,
                fallback,
                config,
            )
            if row is not None:
                records.append(row)
    return pd.DataFrame(records)
