from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.phase6.financial_targets import EP_TICKERS
from energy_nowcast.research.v351.revenue import CIKS


ACQUISITION_ROUTES = (
    "PaymentsToAcquireBusinessesNetOfCashAcquired",
    "PaymentsToAcquireBusinessesGross",
)
DIVESTITURE_ROUTES = (
    "ProceedsFromDivestitureOfBusinessesAndInterestsInAffiliates",
    "ProceedsFromDivestitureOfBusinesses",
    "ProceedsFromSaleOfOilAndGasPropertyAndEquipment",
    "ProceedsFromSaleOfProductiveAssets",
    "ProceedsFromSaleOfPropertyPlantAndEquipment",
)


def _payload(root: Path, ticker: str) -> dict[str, object]:
    return json.loads(
        (root / f"CIK{CIKS[ticker]:010d}.json").read_text(encoding="utf-8")
    )


def _annual_fact(
    payload: dict[str, object], tag: str
) -> pd.DataFrame:
    fact = payload.get("facts", {}).get("us-gaap", {}).get(tag, {})
    rows = [
        {"unit": unit, **item}
        for unit, values in fact.get("units", {}).items()
        for item in values
    ]
    frame = pd.DataFrame(rows)
    if frame.empty or not {"start", "end", "filed", "val", "form"}.issubset(frame):
        return pd.DataFrame(columns=["year", "val", "source_tag"])
    for column in ("start", "end", "filed"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame["val"] = pd.to_numeric(frame["val"], errors="coerce")
    duration = (frame["end"] - frame["start"]).dt.days + 1
    delay = (frame["filed"] - frame["end"]).dt.days
    frame = frame.loc[
        frame["form"].astype(str).eq("10-K")
        & frame["unit"].astype(str).eq("USD")
        & duration.between(330, 380)
        & delay.between(0, 180)
        & frame["val"].notna()
    ].copy()
    if frame.empty:
        return pd.DataFrame(columns=["year", "val", "source_tag"])
    frame["year"] = frame["end"].dt.year.astype(int)
    frame["source_tag"] = f"us-gaap:{tag}"
    sort_columns = [column for column in ("year", "filed", "accn") if column in frame]
    return (
        frame.sort_values(sort_columns)
        .drop_duplicates("year", keep="first")
        .reset_index(drop=True)
    )


def _route_panel(
    companyfacts_root: Path,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        payload = _payload(companyfacts_root, ticker)
        histories = {
            tag: _annual_fact(payload, tag).set_index("year")
            for tag in (*ACQUISITION_ROUTES, *DIVESTITURE_ROUTES)
        }
        for year in range(2018, 2026):
            acquisition = 0.0
            acquisition_tag = ""
            acquisition_observed = False
            for tag in ACQUISITION_ROUTES:
                history = histories[tag]
                if year in history.index:
                    acquisition = float(history.loc[year, "val"])
                    acquisition_tag = str(history.loc[year, "source_tag"])
                    acquisition_observed = True
                    break
            divestiture = 0.0
            divestiture_tag = ""
            divestiture_observed = False
            for tag in DIVESTITURE_ROUTES:
                history = histories[tag]
                if year in history.index:
                    divestiture = float(history.loc[year, "val"])
                    divestiture_tag = str(history.loc[year, "source_tag"])
                    divestiture_observed = True
                    break
            rows.append(
                {
                    "ticker": ticker,
                    "year": year,
                    "acquisition_cash_proxy_usd": acquisition,
                    "acquisition_source_tag": acquisition_tag,
                    "acquisition_fact_observed": acquisition_observed,
                    "divestiture_cash_proxy_usd": divestiture,
                    "divestiture_source_tag": divestiture_tag,
                    "divestiture_fact_observed": divestiture_observed,
                    "missing_fact_zero_semantics": (
                        "ZERO_FOR_DIAGNOSTIC_ONLY_NOT_AUTHORITATIVE_NO_EVENT_PROOF"
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_mna_normalized_capital_bridge(
    *, companyfacts_root: Path, ttm_financial_path: Path
) -> dict[str, pd.DataFrame]:
    routes = _route_panel(companyfacts_root)
    ttm = pd.read_parquet(ttm_financial_path)
    annual = ttm.loc[
        ttm["subindustry"].eq("ep")
        & ttm["quarter"].astype(str).str.endswith("Q4")
    ].copy()
    annual["year"] = annual["quarter"].astype(str).str[:4].astype(int)
    annual = annual.loc[annual["year"].between(2018, 2025)]
    annual["opening_invested_capital_usd"] = annual[
        "prior_year_invested_capital_usd"
    ]
    annual["closing_invested_capital_usd"] = annual["invested_capital_usd"]
    annual["raw_delta_invested_capital_usd"] = (
        annual["closing_invested_capital_usd"]
        - annual["opening_invested_capital_usd"]
    )
    annual["raw_delta_nopat_usd"] = (
        annual["ttm_nopat_usd"] - annual["prior_year_ttm_nopat"]
    )
    panel = annual.merge(routes, on=["ticker", "year"], how="left")
    panel["mna_cash_normalized_delta_invested_capital_usd"] = (
        panel["raw_delta_invested_capital_usd"]
        - panel["acquisition_cash_proxy_usd"]
        + panel["divestiture_cash_proxy_usd"]
    )
    panel["capital_bridge_residual_usd"] = panel[
        "closing_invested_capital_usd"
    ] - (
        panel["opening_invested_capital_usd"]
        + panel["ttm_cash_capex_usd"]
        + panel["acquisition_cash_proxy_usd"]
        - panel["divestiture_cash_proxy_usd"]
    )
    panel["normalized_delta_to_opening_ratio"] = (
        panel["mna_cash_normalized_delta_invested_capital_usd"]
        / panel["opening_invested_capital_usd"].abs()
    )
    eligible = (
        panel["mna_cash_normalized_delta_invested_capital_usd"].gt(1_000_000.0)
        & panel["normalized_delta_to_opening_ratio"].gt(0.02)
        & panel["raw_delta_nopat_usd"].notna()
    )
    panel["denominator_only_mna_normalized_incremental_roic_pct"] = np.where(
        eligible,
        panel["raw_delta_nopat_usd"]
        / panel["mna_cash_normalized_delta_invested_capital_usd"]
        * 100.0,
        np.nan,
    )
    panel["mna_normalization_status"] = np.where(
        eligible,
        "DIAGNOSTIC_DENOMINATOR_ONLY_CASH_MNA_NORMALIZED",
        "LOCKED_NONPOSITIVE_SMALL_OR_INCOMPLETE_NORMALIZED_DENOMINATOR",
    )
    panel["mna_normalization_validated"] = False
    panel["limitations"] = (
        "ACQUIRED_NOPAT_NOT_REMOVED_NONCASH_CONSIDERATION_AND_BOOK_VALUE_"
        "DIFFERENCES_REMAIN_IN_CAPITAL_BRIDGE_RESIDUAL"
    )
    summary_rows: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        history = panel.loc[
            panel["ticker"].eq(ticker)
            & panel["denominator_only_mna_normalized_incremental_roic_pct"].notna()
        ]
        summary_rows.append(
            {
                "ticker": ticker,
                "diagnostic_years": len(history),
                "mna_normalized_incremental_roic_q50_pct": (
                    float(
                        history[
                            "denominator_only_mna_normalized_incremental_roic_pct"
                        ].median()
                    )
                    if len(history) >= 3
                    else np.nan
                ),
                "acquisition_fact_years": int(
                    panel.loc[panel["ticker"].eq(ticker), "acquisition_fact_observed"].sum()
                ),
                "divestiture_fact_years": int(
                    panel.loc[panel["ticker"].eq(ticker), "divestiture_fact_observed"].sum()
                ),
                "diagnostic_implemented": True,
                "mna_normalization_validated": False,
                "status": (
                    "DIAGNOSTIC_IMPLEMENTED_NOT_FULLY_NORMALIZED"
                    if len(history) >= 1
                    else "IMPLEMENTED_NO_ELIGIBLE_DENOMINATOR"
                ),
            }
        )
    return {
        "annual_mna_normalized_capital_bridge": panel.sort_values(
            ["ticker", "year"]
        ).reset_index(drop=True),
        "mna_normalized_roic_summary": pd.DataFrame(summary_rows),
    }
