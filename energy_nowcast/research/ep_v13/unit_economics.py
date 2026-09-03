from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from energy_nowcast.research.phase6.financial_targets import EP_TICKERS
from equity_platform.sectors.energy.research.revenue.v35.taxonomy import GROUP_PRICE_WEIGHTS, group_for_ticker
from energy_nowcast.research.v351.revenue import CIKS


QUANTITY_TAGS = {
    "end_reserves": "ProvedDevelopedAndUndevelopedReserveNetEnergy",
    "production": "ProvedDevelopedAndUndevelopedReserveProductionEnergy",
    "extensions_discoveries": (
        "ProvedDevelopedAndUndevelopedReserveExtensionAndDiscoveryEnergy"
    ),
    "revisions": (
        "ProvedDevelopedAndUndevelopedReserveRevisionOfPreviousEstimateEnergy"
    ),
    "improved_recovery": (
        "ProvedDevelopedAndUndevelopedReserveImprovedRecoveryEnergy"
    ),
    "purchases": (
        "ProvedDevelopedAndUndevelopedReservePurchaseOfMineralInPlaceEnergy"
    ),
    "sales": "ProvedDevelopedAndUndevelopedReservesSaleOfMineralInPlaceEnergy",
}

COST_TAGS = {
    "development_cost_usd": ("CostsIncurredDevelopmentCosts",),
    "lifting_cost_usd": ("ResultsOfOperationsProductionOrLiftingCosts",),
    "upstream_dda_usd": (
        "ResultsOfOperationsDepreciationDepletionAmortizationAndAccretion",
        "ResultsOfOperationsDepreciationDepletionAndAmortizationAndValuationProvisions",
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipmentIncludingOilAndGasProperty",
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
    ),
    "upstream_revenue_usd": (
        "ResultsOfOperationsRevenueFromOilAndGasProducingActivities",
    ),
}

# Output quantities use MBOE (thousand barrels of oil equivalent). Companyfacts
# values retain filer unit identifiers, so a production-KPI cross-check below
# detects and records any additional power-of-ten scale used by the filing.
UNIT_TO_MBOE = {
    "boe": 1.0 / 1_000.0,
    "mboe": 1.0,
    "mmboe": 1_000.0,
    "mcfe": 1.0 / 6_000.0,
    "mmcfe": 1.0 / 6.0,
    "bcfe": 1_000.0 / 6.0,
}


def _payload(companyfacts_root: Path, ticker: str) -> dict[str, object]:
    path = companyfacts_root / f"CIK{CIKS[ticker]:010d}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _annual_original_rows(
    payload: dict[str, object], namespace: str, tag: str
) -> pd.DataFrame:
    fact = payload.get("facts", {}).get(namespace, {}).get(tag, {})
    rows: list[dict[str, object]] = []
    for unit, values in fact.get("units", {}).items():
        for value in values:
            rows.append({"unit": unit, **value})
    frame = pd.DataFrame(rows)
    if frame.empty or not {"end", "filed", "val", "form"}.issubset(frame):
        return pd.DataFrame()
    for column in ("start", "end", "filed"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame["val"] = pd.to_numeric(frame["val"], errors="coerce")
    frame["fy"] = pd.to_numeric(frame.get("fy"), errors="coerce")
    eligible = frame.loc[
        frame["form"].astype(str).eq("10-K")
        & frame["end"].notna()
        & frame["filed"].notna()
        & frame["val"].notna()
        & frame["fy"].eq(frame["end"].dt.year)
        & frame["filed"].sub(frame["end"]).dt.days.between(0, 180)
    ].copy()
    if eligible.empty:
        return eligible
    eligible["year"] = eligible["end"].dt.year.astype(int)
    if "start" in eligible:
        duration = (eligible["end"] - eligible["start"]).dt.days + 1
        duration_ok = eligible["start"].isna() | duration.between(330, 380)
        eligible = eligible.loc[duration_ok]
    return (
        eligible.sort_values(["year", "unit", "filed", "accn"])
        .drop_duplicates(["year", "unit"], keep="first")
        .reset_index(drop=True)
    )


def _quantity_rows(payload: dict[str, object], tag: str) -> pd.DataFrame:
    for namespace in ("srt", "us-gaap"):
        result = _annual_original_rows(payload, namespace, tag)
        if not result.empty:
            result["namespace"] = namespace
            result["source_tag"] = f"{namespace}:{tag}"
            return result
    return pd.DataFrame()


def build_annual_production_kpi(production: pd.DataFrame) -> pd.DataFrame:
    frame = production.copy()
    frame["quarter"] = frame["quarter"].astype(str)
    frame["year"] = frame["quarter"].map(lambda value: pd.Period(value, freq="Q").year)
    frame["days"] = frame["quarter"].map(
        lambda value: (
            pd.Period(value, freq="Q").end_time.normalize()
            - pd.Period(value, freq="Q").start_time.normalize()
        ).days
        + 1
    )
    frame["quarter_production_mboe"] = (
        pd.to_numeric(frame["total_mboed"], errors="coerce") * frame["days"]
    )
    annual = (
        frame.groupby(["ticker", "year"], as_index=False)
        .agg(
            kpi_production_mboe=("quarter_production_mboe", "sum"),
            kpi_quarters=("quarter", "nunique"),
            kpi_min_quality=("quality_score", "min"),
            kpi_last_filing_date=("filing_date", "max"),
        )
    )
    annual.loc[annual["kpi_quarters"].ne(4), "kpi_production_mboe"] = np.nan
    return annual


def _best_quantity_scale(
    candidates: pd.DataFrame, kpi_production_mboe: float
) -> dict[str, object] | None:
    if candidates.empty or not np.isfinite(kpi_production_mboe) or kpi_production_mboe <= 0:
        return None
    scored: list[dict[str, object]] = []
    for row in candidates.itertuples(index=False):
        unit = str(row.unit)
        base = UNIT_TO_MBOE.get(unit.lower())
        if base is None or not np.isfinite(row.val) or float(row.val) <= 0:
            continue
        for power in range(-6, 7):
            normalized = float(row.val) * base * (10.0**power)
            ratio = normalized / kpi_production_mboe
            scored.append(
                {
                    "unit": unit,
                    "base_factor": base,
                    "scale_power10": power,
                    "factor_to_mboe": base * (10.0**power),
                    "calibration_ratio": ratio,
                    "calibration_log_error": abs(float(np.log(ratio))),
                    "source_tag": row.source_tag,
                }
            )
    if not scored:
        return None
    selected = min(scored, key=lambda row: row["calibration_log_error"])
    if not 0.75 <= float(selected["calibration_ratio"]) <= 1.25:
        return None
    return selected


def extract_reserve_quantity_panel(
    companyfacts_root: Path,
    production: pd.DataFrame,
    tickers: Iterable[str] = EP_TICKERS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    annual_kpi = build_annual_production_kpi(production)
    rows: list[dict[str, object]] = []
    coverage: list[dict[str, object]] = []
    for ticker in tickers:
        payload = _payload(companyfacts_root, ticker)
        concepts = {
            name: _quantity_rows(payload, tag)
            for name, tag in QUANTITY_TAGS.items()
        }
        production_rows = concepts["production"]
        required_unit_sets = [
            set(values["unit"].astype(str))
            for name, values in concepts.items()
            if name in {"end_reserves", "extensions_discoveries", "revisions"}
            and not values.empty
        ]
        common_chain_units = (
            set.intersection(*required_unit_sets) if required_unit_sets else set()
        )
        kpi = annual_kpi.loc[annual_kpi["ticker"].eq(ticker)].set_index("year")
        ticker_rows = 0
        for year in sorted(set(production_rows.get("year", pd.Series(dtype=int)))):
            if year not in kpi.index:
                continue
            kpi_row = kpi.loc[year]
            year_candidates = production_rows.loc[production_rows["year"].eq(year)]
            if common_chain_units:
                year_candidates = year_candidates.loc[
                    year_candidates["unit"].astype(str).isin(common_chain_units)
                ]
            selected = _best_quantity_scale(
                year_candidates,
                float(kpi_row["kpi_production_mboe"]),
            )
            if selected is None:
                continue
            unit = str(selected["unit"])
            factor = float(selected["factor_to_mboe"])
            row: dict[str, object] = {
                "ticker": ticker,
                "year": year,
                "quantity_unit": unit,
                "quantity_factor_to_mboe": factor,
                "quantity_scale_power10": int(selected["scale_power10"]),
                "production_calibration_ratio": float(selected["calibration_ratio"]),
                "kpi_production_mboe": float(kpi_row["kpi_production_mboe"]),
                "kpi_min_quality": float(kpi_row["kpi_min_quality"]),
                "quantity_scale_status": "KPI_CALIBRATED_WITHIN_25PCT",
            }
            sources: list[str] = []
            missing_events: list[str] = []
            for name, values in concepts.items():
                exact = values.loc[
                    values["year"].eq(year) & values["unit"].astype(str).eq(unit)
                ] if not values.empty else pd.DataFrame()
                if exact.empty:
                    row[f"{name}_mboe"] = np.nan
                    if name in {"improved_recovery", "purchases", "sales"}:
                        missing_events.append(name)
                    continue
                fact = exact.iloc[0]
                row[f"{name}_mboe"] = float(fact["val"]) * factor
                sources.append(str(fact["source_tag"]))
            row["quantity_source_tags"] = ";".join(sorted(set(sources)))
            row["missing_event_facts_assumed_zero_for_identity"] = ";".join(
                missing_events
            )
            if np.isfinite(row.get("production_mboe", np.nan)):
                rows.append(row)
                ticker_rows += 1
        coverage.append(
            {
                "ticker": ticker,
                "reserve_quantity_years": ticker_rows,
                "reserve_chain_status": (
                    "STANDARDIZED_RESERVE_CHAIN_KPI_SCALE_VERIFIED"
                    if ticker_rows >= 3
                    else "LOCKED_INSUFFICIENT_STANDARDIZED_RESERVE_CHAIN"
                ),
            }
        )
    panel = pd.DataFrame(rows)
    if panel.empty:
        return panel, pd.DataFrame(coverage)
    panel = panel.sort_values(["ticker", "year"]).reset_index(drop=True)
    panel["begin_reserves_source_year"] = panel.groupby("ticker")["year"].shift(1)
    prior_reserves = panel.groupby("ticker")["end_reserves_mboe"].shift(1)
    consecutive = panel["year"].sub(panel["begin_reserves_source_year"]).eq(1)
    panel["begin_reserves_mboe"] = prior_reserves.where(consecutive)
    for event in ("improved_recovery", "purchases", "sales"):
        panel[f"{event}_identity_mboe"] = panel[f"{event}_mboe"].fillna(0.0)
    panel["stock_flow_net_organic_additions_mboe"] = (
        panel["end_reserves_mboe"]
        - panel["begin_reserves_mboe"]
        + panel["production_mboe"]
        - panel["purchases_identity_mboe"]
        + panel["sales_identity_mboe"]
    )
    panel["identified_organic_additions_mboe"] = (
        panel["extensions_discoveries_mboe"]
        + panel["revisions_mboe"]
        + panel["improved_recovery_identity_mboe"]
    )
    panel["gross_positive_additions_mboe"] = (
        panel["extensions_discoveries_mboe"].clip(lower=0.0)
        + panel["revisions_mboe"].clip(lower=0.0)
        + panel["improved_recovery_identity_mboe"].clip(lower=0.0)
    )
    panel["reserve_reconciliation_residual_mboe"] = (
        panel["stock_flow_net_organic_additions_mboe"]
        - panel["identified_organic_additions_mboe"]
    )
    panel["reserve_life_years"] = panel["end_reserves_mboe"] / panel["production_mboe"]
    panel["stock_flow_organic_replacement_rate_pct"] = (
        panel["stock_flow_net_organic_additions_mboe"]
        / panel["production_mboe"]
        * 100.0
    )
    panel["identified_organic_replacement_rate_pct"] = (
        panel["identified_organic_additions_mboe"]
        / panel["production_mboe"]
        * 100.0
    )
    panel["reserve_reconciliation_residual_pct_of_production"] = (
        panel["reserve_reconciliation_residual_mboe"]
        / panel["production_mboe"]
        * 100.0
    )
    return panel, pd.DataFrame(coverage)


def _annual_usd_history(
    payload: dict[str, object], tags: tuple[str, ...], output: str
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for priority, tag in enumerate(tags):
        values = _annual_original_rows(payload, "us-gaap", tag)
        if values.empty:
            continue
        usd = values.loc[values["unit"].astype(str).eq("USD")].copy()
        if usd.empty:
            continue
        usd["tag_priority"] = priority
        usd["source_tag"] = f"us-gaap:{tag}"
        parts.append(usd)
    if not parts:
        return pd.DataFrame(columns=["year", output, f"{output}_source_tag"])
    combined = pd.concat(parts, ignore_index=True).sort_values(
        ["year", "tag_priority", "filed"]
    )
    selected = combined.drop_duplicates("year", keep="first")
    return selected[["year", "val", "source_tag"]].rename(
        columns={"val": output, "source_tag": f"{output}_source_tag"}
    )


def add_annual_cost_economics(
    companyfacts_root: Path, quantity_panel: pd.DataFrame
) -> pd.DataFrame:
    if quantity_panel.empty:
        return quantity_panel
    output: list[pd.DataFrame] = []
    for ticker, quantities in quantity_panel.groupby("ticker", sort=True):
        payload = _payload(companyfacts_root, ticker)
        frame = quantities.copy()
        for output_name, tags in COST_TAGS.items():
            frame = frame.merge(
                _annual_usd_history(payload, tags, output_name),
                on="year",
                how="left",
            )
        denominator = frame["production_mboe"] * 1_000.0
        frame["lifting_cost_per_boe"] = frame["lifting_cost_usd"] / denominator
        frame["upstream_dda_per_boe"] = frame["upstream_dda_usd"] / denominator
        frame["upstream_revenue_per_boe"] = frame["upstream_revenue_usd"] / denominator
        additions_boe = frame["gross_positive_additions_mboe"] * 1_000.0
        frame["development_cost_per_added_boe"] = (
            frame["development_cost_usd"] / additions_boe.where(additions_boe.gt(0))
        )
        output.append(frame)
    normalized = [frame.dropna(axis=1, how="all") for frame in output]
    return pd.concat(normalized, ignore_index=True).sort_values(
        ["ticker", "year"]
    ).reset_index(drop=True)


def build_normalized_price_reference(
    prices: pd.DataFrame,
    start_quarter: str = "2015Q1",
    end_quarter: str = "2024Q4",
) -> pd.DataFrame:
    frame = prices.copy()
    frame["quarter"] = frame["quarter"].astype(str)
    start = pd.Period(start_quarter, freq="Q").ordinal
    end = pd.Period(end_quarter, freq="Q").ordinal
    frame["ordinal"] = frame["quarter"].map(lambda value: pd.Period(value, freq="Q").ordinal)
    history = frame.loc[frame["ordinal"].between(start, end)]
    rows = []
    for label, quantile in (("Q25", 0.25), ("Q50", 0.50), ("Q75", 0.75)):
        rows.append(
            {
                "reference": label,
                "wti_usd_per_bbl": history["wti_price"].quantile(quantile),
                "henry_usd_per_mcf": history["henry_price"].quantile(quantile),
                "gas_usd_per_boe": history["henry_price"].quantile(quantile) * 6.0,
                "propane_usd_per_bbl": history["propane_price_bbl"].quantile(quantile),
                "history_start_quarter": start_quarter,
                "history_end_quarter": end_quarter,
                "quarter_observations": len(history),
                "normalization_method": "PRE_RECENT_2015_2024_EMPIRICAL_QUANTILE",
                "hormuz_long_run_anchor": False,
            }
        )
    return pd.DataFrame(rows)


def build_production_mix_price_proxy(
    production: pd.DataFrame,
    price_reference: pd.DataFrame,
    strict_realized_gas_coverage: pd.DataFrame | None = None,
    tickers: Iterable[str] = EP_TICKERS,
) -> pd.DataFrame:
    frame = production.copy()
    frame["quarter"] = frame["quarter"].astype(str)
    frame["ordinal"] = frame["quarter"].map(lambda value: pd.Period(value, freq="Q").ordinal)
    strict_counts = {}
    if strict_realized_gas_coverage is not None and not strict_realized_gas_coverage.empty:
        strict_counts = strict_realized_gas_coverage.set_index("ticker")[
            "strict_price_quarters"
        ].to_dict()
    refs = price_reference.set_index("reference")
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        available = frame.loc[
            frame["ticker"].eq(ticker) & frame["total_mboed"].notna()
        ].sort_values("ordinal")
        if available.empty:
            rows.append(
                {
                    "ticker": ticker,
                    "production_mix_status": "LOCKED_NO_AUDITED_PRODUCTION_KPI",
                    "strict_realized_gas_price_quarters": int(strict_counts.get(ticker, 0)),
                    "realized_basis_status": "DEFERRED_NO_COMMON_CROSS_COMMODITY_BASIS",
                }
            )
            continue
        latest = available.tail(4)
        weighted = {}
        for component, column, divisor in (
            ("oil", "oil_mbpd", 1.0),
            ("ngl", "ngl_mbpd", 1.0),
            ("gas", "gas_mmcfd", 6.0),
        ):
            values = pd.to_numeric(latest[column], errors="coerce") / divisor
            weighted[component] = float(values.mean()) if values.notna().any() else np.nan
        total = float(pd.to_numeric(latest["total_mboed"], errors="coerce").mean())
        known = {
            component: value / total
            for component, value in weighted.items()
            if np.isfinite(value) and value >= 0 and total > 0
        }
        group_weights = GROUP_PRICE_WEIGHTS[group_for_ticker(ticker)]
        missing = [component for component in ("oil", "ngl", "gas") if component not in known]
        remaining = max(1.0 - sum(known.values()), 0.0)
        missing_prior = sum(group_weights[component] for component in missing)
        mix = dict(known)
        for component in missing:
            mix[component] = (
                remaining * group_weights[component] / missing_prior
                if missing_prior
                else 0.0
            )
        mix_total = sum(mix.values())
        if mix_total <= 0:
            mix = dict(group_weights)
            mix_method = "GROUP_PRIOR_NO_COMPONENT_MIX"
        else:
            mix = {key: value / mix_total for key, value in mix.items()}
            mix_method = (
                "AUDITED_COMPONENT_MIX"
                if not missing and 0.75 <= sum(known.values()) <= 1.25
                else "AUDITED_PARTIAL_MIX_COMPLETED_WITH_GROUP_PRIOR"
            )
        row = {
            "ticker": ticker,
            "production_mix_status": "PRICE_VOLUME_PROXY_READY",
            "mix_method": mix_method,
            "mix_start_quarter": latest["quarter"].min(),
            "mix_end_quarter": latest["quarter"].max(),
            "mix_quarters": latest["quarter"].nunique(),
            "oil_mix_pct": mix["oil"] * 100.0,
            "ngl_mix_pct": mix["ngl"] * 100.0,
            "gas_boe_mix_pct": mix["gas"] * 100.0,
            "strict_realized_gas_price_quarters": int(strict_counts.get(ticker, 0)),
            "realized_basis_status": "DEFERRED_NO_COMMON_CROSS_COMMODITY_BASIS",
        }
        for reference in ("Q25", "Q50", "Q75"):
            price = refs.loc[reference]
            row[f"normalized_gross_price_{reference.lower()}_per_boe"] = (
                mix["oil"] * float(price["wti_usd_per_bbl"])
                + mix["ngl"] * float(price["propane_usd_per_bbl"])
                + mix["gas"] * float(price["gas_usd_per_boe"])
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def build_unit_cross_check(
    annual: pd.DataFrame,
    price_proxy: pd.DataFrame,
    v12_economics: pd.DataFrame,
    v11_base_assumptions: pd.DataFrame,
    coverage: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    v12 = v12_economics.set_index("ticker")
    base = v11_base_assumptions.loc[
        v11_base_assumptions["scenario"].eq("BASE")
    ].set_index("ticker")
    reserve_status = coverage.set_index("ticker")["reserve_chain_status"].to_dict()
    price_lookup = price_proxy.set_index("ticker")
    for ticker in EP_TICKERS:
        history = annual.loc[annual["ticker"].eq(ticker)].sort_values("year").tail(5)
        price = price_lookup.loc[ticker]
        row: dict[str, object] = {
            "ticker": ticker,
            "reserve_chain_status": reserve_status.get(
                ticker, "LOCKED_INSUFFICIENT_STANDARDIZED_RESERVE_CHAIN"
            ),
            "production_mix_status": price["production_mix_status"],
            "realized_basis_status": price["realized_basis_status"],
            "v12_historical_margin_q50_pct": float(
                v12.loc[ticker, "normalized_margin_q50_pct"]
            ),
            "v11_base_operating_margin_pct": float(
                base.loc[ticker, "operating_margin_pct"]
            ),
            "research_only": True,
            "production_eligible": False,
            "cost_scope": (
                "LIFTING_PLUS_DDA_PLUS_DEVELOPMENT_EXCLUDES_TRANSPORT_TAX_HEDGE_BASIS_CORPORATE"
            ),
            "terminal_anchor_status": (
                "LOCKED_INCOMPLETE_TRANSPORT_TAX_AND_REALIZED_BASIS"
            ),
            "margin_cross_check_status": "LOCKED_INSUFFICIENT_STANDARDIZED_COST_CHAIN",
            "roic_cross_check_status": "LOCKED_INSUFFICIENT_STANDARDIZED_COST_CHAIN",
        }
        required = {
            "lifting": int(history["lifting_cost_per_boe"].notna().sum()) if len(history) else 0,
            "dda": int(history["upstream_dda_per_boe"].notna().sum()) if len(history) else 0,
            "development": int(history["development_cost_per_added_boe"].notna().sum()) if len(history) else 0,
            "reserve": int(history["reserve_life_years"].notna().sum()) if len(history) else 0,
        }
        row.update({f"{key}_observations_5y": value for key, value in required.items()})
        full = (
            row["reserve_chain_status"] == "STANDARDIZED_RESERVE_CHAIN_KPI_SCALE_VERIFIED"
            and all(value >= 3 for value in required.values())
            and price["production_mix_status"] == "PRICE_VOLUME_PROXY_READY"
        )
        if not full:
            row["unit_economics_status"] = (
                "PARTIAL_PRICE_VOLUME_ONLY_RESERVE_REPLACEMENT_LOCKED"
                if price["production_mix_status"] == "PRICE_VOLUME_PROXY_READY"
                else "LOCKED_NO_AUDITED_PRODUCTION_INPUT"
            )
            rows.append(row)
            continue
        lifting = float(history["lifting_cost_per_boe"].median())
        dda = float(history["upstream_dda_per_boe"].median())
        development = float(history["development_cost_per_added_boe"].median())
        tax_rate = float(base.loc[ticker, "tax_rate_pct"]) / 100.0
        row.update(
            {
                "unit_economics_status": "CORE_STANDARDIZED_RESERVE_REPLACEMENT_CROSS_CHECK",
                "normalized_lifting_cost_per_boe": lifting,
                "normalized_dda_per_boe": dda,
                "normalized_development_cost_per_added_boe": development,
                "reserve_life_median_years": float(history["reserve_life_years"].median()),
                "stock_flow_organic_replacement_rate_median_pct": float(
                    history["stock_flow_organic_replacement_rate_pct"].median()
                ),
                "identified_organic_replacement_rate_median_pct": float(
                    history["identified_organic_replacement_rate_pct"].median()
                ),
            }
        )
        for reference in ("q25", "q50", "q75"):
            gross = float(price[f"normalized_gross_price_{reference}_per_boe"])
            accounting_margin = (gross - lifting - dda) / gross * 100.0
            replacement_cash_margin = (gross - lifting - development) / gross * 100.0
            row[f"normalized_gross_price_{reference}_per_boe"] = gross
            row[f"commodity_normalized_accounting_margin_{reference}_pct"] = accounting_margin
            row[f"reserve_replacement_cash_margin_{reference}_pct"] = replacement_cash_margin
            row[f"reserve_replacement_roic_proxy_{reference}_pct"] = (
                (gross - lifting - dda) * (1.0 - tax_rate) / development * 100.0
                if development > 0
                else np.nan
            )
        row["accounting_margin_q50_gap_vs_v12_pct_points"] = (
            row["commodity_normalized_accounting_margin_q50_pct"]
            - row["v12_historical_margin_q50_pct"]
        )
        row["margin_cross_check_status"] = (
            "DIRECTIONALLY_CONSISTENT_WITH_V12_WITHIN_10PPT"
            if abs(row["accounting_margin_q50_gap_vs_v12_pct_points"]) <= 10.0
            else "REJECT_AS_TERMINAL_ANCHOR_CORE_COST_SCOPE_INCOMPLETE"
        )
        row["roic_cross_check_status"] = (
            "PLAUSIBILITY_REVIEW_REQUIRED_ABOVE_100PCT"
            if row["reserve_replacement_roic_proxy_q50_pct"] > 100.0
            else "RESEARCH_RANGE_BELOW_100PCT_NOT_VALIDATED"
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def build_unit_economics_research(
    *,
    companyfacts_root: Path,
    production_path: Path,
    price_path: Path,
    strict_realized_gas_coverage_path: Path,
    v12_economics_path: Path,
    v11_assumptions_path: Path,
) -> dict[str, pd.DataFrame]:
    production = pd.read_csv(production_path)
    prices = pd.read_csv(price_path)
    strict = (
        pd.read_csv(strict_realized_gas_coverage_path)
        if strict_realized_gas_coverage_path.exists()
        else pd.DataFrame()
    )
    quantities, coverage = extract_reserve_quantity_panel(
        companyfacts_root, production
    )
    annual = add_annual_cost_economics(companyfacts_root, quantities)
    price_reference = build_normalized_price_reference(prices)
    price_proxy = build_production_mix_price_proxy(
        production, price_reference, strict
    )
    cross_check = build_unit_cross_check(
        annual,
        price_proxy,
        pd.read_csv(v12_economics_path),
        pd.read_csv(v11_assumptions_path),
        coverage,
    )
    coverage = coverage.merge(
        price_proxy[
            ["ticker", "production_mix_status", "strict_realized_gas_price_quarters"]
        ],
        on="ticker",
        how="left",
    ).merge(
        cross_check[["ticker", "unit_economics_status"]],
        on="ticker",
        how="left",
    )
    return {
        "data_coverage": coverage,
        "normalized_price_reference": price_reference,
        "production_mix_price_proxy": price_proxy,
        "reserve_quantity_panel": quantities,
        "annual_unit_economics_panel": annual,
        "unit_economics_cross_check": cross_check,
    }
