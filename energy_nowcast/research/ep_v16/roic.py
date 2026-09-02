from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.phase6.financial_targets import EP_TICKERS


def build_three_level_roic(
    *, parent_roic_path: Path, ttm_financial_path: Path
) -> dict[str, pd.DataFrame]:
    parent = pd.read_csv(parent_roic_path).set_index("ticker")
    ttm = pd.read_parquet(ttm_financial_path)
    annual = ttm.loc[
        ttm["subindustry"].eq("ep")
        & ttm["quarter"].astype(str).str.endswith("Q4")
    ].copy()
    annual["year"] = annual["quarter"].astype(str).str[:4].astype(int)
    annual = annual.loc[annual["year"].between(2018, 2025)]
    annual["delta_nopat_usd"] = annual["ttm_nopat_usd"] - annual["prior_year_ttm_nopat"]
    annual["delta_invested_capital_usd"] = (
        annual["invested_capital_usd"] - annual["prior_year_invested_capital_usd"]
    )
    annual["delta_capital_to_prior_ratio"] = (
        annual["delta_invested_capital_usd"]
        / annual["prior_year_invested_capital_usd"].abs()
    )
    annual["company_incremental_roic_pct"] = (
        annual["delta_nopat_usd"] / annual["delta_invested_capital_usd"] * 100.0
    )
    annual["company_incremental_roic_eligible"] = (
        annual["ttm_complete"].fillna(False)
        & annual["delta_invested_capital_usd"].gt(1_000_000.0)
        & annual["delta_capital_to_prior_ratio"].gt(0.02)
        & np.isfinite(annual["company_incremental_roic_pct"])
    )
    annual["company_incremental_roic_status"] = np.where(
        annual["company_incremental_roic_eligible"],
        "POSITIVE_MATERIAL_DELTA_CAPITAL_DIAGNOSTIC",
        "LOCKED_NEGATIVE_SMALL_OR_INCOMPLETE_DELTA_CAPITAL",
    )
    annual_panel = annual[
        [
            "ticker",
            "year",
            "quarter",
            "ttm_nopat_usd",
            "prior_year_ttm_nopat",
            "delta_nopat_usd",
            "invested_capital_usd",
            "prior_year_invested_capital_usd",
            "delta_invested_capital_usd",
            "delta_capital_to_prior_ratio",
            "company_incremental_roic_pct",
            "company_incremental_roic_eligible",
            "company_incremental_roic_status",
        ]
    ].sort_values(["ticker", "year"])
    rows: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        history = annual_panel.loc[
            annual_panel["ticker"].eq(ticker)
            & annual_panel["company_incremental_roic_eligible"]
        ]
        years = len(history)
        q50 = (
            float(history["company_incremental_roic_pct"].median())
            if years >= 3
            else np.nan
        )
        project = float(parent.loc[ticker, "project_development_roic_proxy_q50_pct"])
        replacement = float(
            parent.loc[ticker, "company_scope_all_in_reserve_roic_proxy_q50_pct"]
        )
        rows.append(
            {
                "ticker": ticker,
                "level_1_development_roic_pct": project,
                "level_1_semantics": "PROJECT_DEVELOPMENT_UNIT_ECONOMICS_PROXY",
                "level_2_reserve_replacement_roic_pct": replacement,
                "level_2_semantics": "DEV_EXPLORATION_AND_ACQUISITION_RESERVE_PROXY",
                "level_3_company_incremental_roic_q50_pct": q50,
                "level_3_eligible_years": years,
                "level_3_semantics": "DELTA_NOPAT_OVER_DELTA_TOTAL_INVESTED_CAPITAL",
                "three_level_roic_separated": True,
                "company_incremental_roic_validated": False,
                "level_3_status": (
                    "DIAGNOSTIC_3PLUS_YEARS_NOT_MNA_NORMALIZED"
                    if years >= 3
                    else "LOCKED_FEWER_THAN_3_POSITIVE_MATERIAL_DELTA_CAPITAL_YEARS"
                ),
                "unexplained_roic_over_100pct": bool(
                    (np.isfinite(project) and project > 100.0)
                    or (np.isfinite(replacement) and replacement > 100.0)
                    or (np.isfinite(q50) and abs(q50) > 100.0)
                ),
                "terminal_anchor_ready": False,
                "research_only": True,
            }
        )
    return {
        "annual_company_incremental_roic_panel": annual_panel,
        "three_level_roic_summary": pd.DataFrame(rows),
    }
