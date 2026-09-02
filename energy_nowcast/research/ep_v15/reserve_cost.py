from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v13.unit_economics import build_annual_production_kpi
from energy_nowcast.research.phase6.financial_targets import EP_TICKERS
from energy_nowcast.research.v351.revenue import CIKS


QUANTITY_ROUTES = {
    "end_reserves": (
        "ProvedDevelopedAndUndevelopedReserveNetEnergy",
        "ProvedDevelopedAndUndevelopedReservesNet",
    ),
    "production": (
        "ProvedDevelopedAndUndevelopedReserveProductionEnergy",
        "ProvedDevelopedAndUndevelopedReservesProduction",
    ),
    "extensions_discoveries": (
        "ProvedDevelopedAndUndevelopedReserveExtensionAndDiscoveryEnergy",
        "ProvedDevelopedAndUndevelopedReservesExtensionsDiscoveriesAndAdditions",
    ),
    "revisions": (
        "ProvedDevelopedAndUndevelopedReserveRevisionOfPreviousEstimateEnergy",
        "ProvedDevelopedAndUndevelopedReservesRevisionsOfPreviousEstimatesIncreaseDecrease",
    ),
    "improved_recovery": (
        "ProvedDevelopedAndUndevelopedReserveImprovedRecoveryEnergy",
        "ProvedDevelopedAndUndevelopedReservesImprovedRecovery",
    ),
    "purchases": (
        "ProvedDevelopedAndUndevelopedReservePurchaseOfMineralInPlaceEnergy",
        "ProvedDevelopedAndUndevelopedReservesPurchasesOfMineralsInPlace",
    ),
    "sales": (
        "ProvedDevelopedAndUndevelopedReservesSaleOfMineralInPlaceEnergy",
        "ProvedDevelopedAndUndevelopedReservesSalesOfMineralsInPlace",
    ),
}

UNIT_TO_MBOE = {
    "boe": 1.0 / 1_000.0,
    "mboe": 1.0,
    "mmboe": 1_000.0,
    "bbl": 1.0 / 1_000.0,
    "mbbl": 1.0,
    "mbbls": 1.0,
    "mmbbls": 1_000.0,
    "mcf": 1.0 / 6_000.0,
    "mcfe": 1.0 / 6_000.0,
    "mmcf": 1.0 / 6.0,
    "mmcfe": 1.0 / 6.0,
    "bcf": 1_000.0 / 6.0,
    "bcfe": 1_000.0 / 6.0,
}

ALL_IN_TAGS = {
    "reported_total_primary_usd": "CostsIncurredAcquisitionOfOilAndGasProperties",
    "reported_total_alternate_usd": (
        "CostsIncurredOilAndGasPropertyAcquisitionExplorationAndDevelopmentActivities"
    ),
    "development_usd": "CostsIncurredDevelopmentCosts",
    "exploration_usd": "CostsIncurredExplorationCosts",
    "proved_acquisition_usd": (
        "CostsIncurredAcquisitionOfOilAndGasPropertiesWithProvedReserves"
    ),
    "unproved_acquisition_usd": (
        "CostsIncurredAcquisitionOfUnprovedOilAndGasProperties"
    ),
}


def _payload(root: Path, ticker: str) -> dict[str, object]:
    return json.loads(
        (root / f"CIK{CIKS[ticker]:010d}.json").read_text(encoding="utf-8")
    )


def _annual_facts(
    payload: dict[str, object], namespace: str, tag: str
) -> pd.DataFrame:
    fact = payload.get("facts", {}).get(namespace, {}).get(tag, {})
    rows = [
        {"unit": unit, **item}
        for unit, values in fact.get("units", {}).items()
        for item in values
    ]
    frame = pd.DataFrame(rows)
    required = {"end", "filed", "val", "form"}
    if frame.empty or not required.issubset(frame):
        return pd.DataFrame()
    for column in ("start", "end", "filed"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame["val"] = pd.to_numeric(frame["val"], errors="coerce")
    delay = frame["filed"].sub(frame["end"]).dt.days
    eligible = frame.loc[
        frame["form"].astype(str).eq("10-K")
        & frame["end"].notna()
        & frame["filed"].notna()
        & frame["val"].notna()
        & delay.between(0, 180)
    ].copy()
    if "start" in eligible:
        duration = (eligible["end"] - eligible["start"]).dt.days + 1
        eligible = eligible.loc[eligible["start"].isna() | duration.between(330, 380)]
    if eligible.empty:
        return eligible
    eligible["year"] = eligible["end"].dt.year.astype(int)
    eligible["namespace"] = namespace
    eligible["source_tag"] = f"{namespace}:{tag}"
    return (
        eligible.sort_values(["year", "unit", "filed", "accn"])
        .drop_duplicates(["year", "unit"], keep="first")
        .reset_index(drop=True)
    )


def _quantity_candidates(
    payload: dict[str, object], tags: tuple[str, ...]
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for route_priority, tag in enumerate(tags):
        for namespace_priority, namespace in enumerate(("srt", "us-gaap")):
            values = _annual_facts(payload, namespace, tag)
            if values.empty:
                continue
            values["route_priority"] = route_priority
            values["namespace_priority"] = namespace_priority
            parts.append(values)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True).sort_values(
        ["year", "route_priority", "namespace_priority", "filed"]
    )


def _select_production_scale(
    candidates: pd.DataFrame, kpi_production_mboe: float
) -> dict[str, object] | None:
    scored: list[dict[str, object]] = []
    for item in candidates.itertuples(index=False):
        base = UNIT_TO_MBOE.get(str(item.unit).lower())
        if base is None or float(item.val) <= 0:
            continue
        for power in range(-6, 7):
            normalized = float(item.val) * base * 10.0**power
            ratio = normalized / kpi_production_mboe
            if ratio <= 0:
                continue
            scored.append(
                {
                    "unit": str(item.unit),
                    "power": power,
                    "factor": base * 10.0**power,
                    "ratio": ratio,
                    "error": abs(float(np.log(ratio))),
                    "source_tag": str(item.source_tag),
                    "route_priority": int(item.route_priority),
                }
            )
    if not scored:
        return None
    acceptable = [row for row in scored if 0.75 <= float(row["ratio"]) <= 1.25]
    if not acceptable:
        return None
    return min(
        acceptable,
        key=lambda row: (
            abs(int(row["power"])),
            row["error"],
            row["route_priority"],
        ),
    )


def _select_event(
    candidates: pd.DataFrame, year: int, selected_unit: str, power: int
) -> dict[str, object] | None:
    values = candidates.loc[candidates["year"].eq(year)].copy()
    if values.empty:
        return None
    values["same_unit"] = values["unit"].astype(str).eq(selected_unit)
    values = values.sort_values(
        ["same_unit", "route_priority", "namespace_priority", "filed"],
        ascending=[False, True, True, True],
    )
    for item in values.itertuples(index=False):
        base = UNIT_TO_MBOE.get(str(item.unit).lower())
        if base is None:
            continue
        event_power = power if str(item.unit) == selected_unit else 0
        return {
            "value_mboe": float(item.val) * base * 10.0**event_power,
            "source_tag": str(item.source_tag),
            "unit": str(item.unit),
        }
    return None


def build_route_aware_reserve_panel(
    companyfacts_root: Path, production_path: Path
) -> pd.DataFrame:
    production = pd.read_csv(production_path)
    kpi = build_annual_production_kpi(production)
    kpi = kpi.loc[kpi["kpi_production_mboe"].notna()].set_index(["ticker", "year"])
    rows: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        payload = _payload(companyfacts_root, ticker)
        concepts = {
            name: _quantity_candidates(payload, routes)
            for name, routes in QUANTITY_ROUTES.items()
        }
        production_candidates = concepts["production"]
        if production_candidates.empty:
            continue
        for year in sorted(set(production_candidates["year"])):
            if (ticker, year) not in kpi.index:
                continue
            kpi_row = kpi.loc[(ticker, year)]
            scale = _select_production_scale(
                production_candidates.loc[production_candidates["year"].eq(year)],
                float(kpi_row["kpi_production_mboe"]),
            )
            if scale is None:
                continue
            row: dict[str, object] = {
                "ticker": ticker,
                "year": int(year),
                "kpi_production_mboe": float(kpi_row["kpi_production_mboe"]),
                "quantity_scale_power10": int(scale["power"]),
                "production_calibration_ratio": float(scale["ratio"]),
                "production_source_tag": scale["source_tag"],
                "production_source_unit": scale["unit"],
            }
            missing_required = False
            for name, values in concepts.items():
                selected = _select_event(
                    values,
                    year,
                    str(scale["unit"]),
                    int(scale["power"]),
                ) if not values.empty else None
                if selected is None:
                    row[f"{name}_mboe"] = np.nan
                    row[f"{name}_source_tag"] = ""
                    row[f"{name}_source_unit"] = ""
                    if name in {
                        "end_reserves",
                        "production",
                        "extensions_discoveries",
                        "revisions",
                    }:
                        missing_required = True
                else:
                    row[f"{name}_mboe"] = selected["value_mboe"]
                    row[f"{name}_source_tag"] = selected["source_tag"]
                    row[f"{name}_source_unit"] = selected["unit"]
            if missing_required:
                continue
            row["missing_optional_events_assumed_zero_for_identity"] = ";".join(
                name
                for name in ("improved_recovery", "purchases", "sales")
                if not np.isfinite(row.get(f"{name}_mboe", np.nan))
            )
            row["quantity_route_status"] = "ROUTE_AWARE_REQUIRED_CHAIN_KPI_VERIFIED"
            rows.append(row)
    panel = pd.DataFrame(rows)
    if panel.empty:
        return panel
    panel = panel.sort_values(["ticker", "year"]).reset_index(drop=True)
    panel["begin_reserves_source_year"] = panel.groupby("ticker")["year"].shift(1)
    prior = panel.groupby("ticker")["end_reserves_mboe"].shift(1)
    consecutive = panel["year"].sub(panel["begin_reserves_source_year"]).eq(1)
    panel["begin_reserves_mboe"] = prior.where(consecutive)
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
    panel["total_gross_reserve_additions_mboe"] = (
        panel["gross_positive_additions_mboe"]
        + panel["purchases_identity_mboe"].clip(lower=0.0)
    )
    return panel


def build_reserve_coverage_summary(
    route_panel: pd.DataFrame, v13_coverage_path: Path
) -> pd.DataFrame:
    prior = pd.read_csv(v13_coverage_path).set_index("ticker")
    rows = []
    for ticker in EP_TICKERS:
        history = route_panel.loc[route_panel["ticker"].eq(ticker)]
        years = len(history)
        usable = int(history["begin_reserves_mboe"].notna().sum())
        rows.append(
            {
                "ticker": ticker,
                "v13_reserve_quantity_years": int(
                    prior.loc[ticker, "reserve_quantity_years"]
                ),
                "v15_route_aware_reserve_quantity_years": years,
                "v15_usable_replacement_years": usable,
                "coverage_year_improvement": years
                - int(prior.loc[ticker, "reserve_quantity_years"]),
                "route_aware_reserve_chain_ready": years >= 3,
                "coverage_status": (
                    "ROUTE_AWARE_RESERVE_CHAIN_READY"
                    if years >= 3
                    else "LOCKED_FEWER_THAN_3_KPI_VERIFIED_YEARS"
                ),
            }
        )
    return pd.DataFrame(rows)


def _annual_usd(payload: dict[str, object], tag: str) -> pd.DataFrame:
    values = _annual_facts(payload, "us-gaap", tag)
    if values.empty:
        return pd.DataFrame(columns=["year", "value"])
    values = values.loc[values["unit"].astype(str).eq("USD")]
    return values[["year", "val"]].rename(columns={"val": "value"})


def build_annual_all_in_cost_panel(companyfacts_root: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        payload = _payload(companyfacts_root, ticker)
        histories = {
            name: _annual_usd(payload, tag).set_index("year")["value"]
            for name, tag in ALL_IN_TAGS.items()
        }
        years = sorted(set().union(*(set(values.index) for values in histories.values())))
        for year in years:
            if not 2021 <= year <= 2025:
                continue
            values = {
                name: float(history.loc[year]) if year in history.index else np.nan
                for name, history in histories.items()
            }
            component_names = (
                "development_usd",
                "exploration_usd",
                "proved_acquisition_usd",
                "unproved_acquisition_usd",
            )
            component_values = [
                values[name] for name in component_names if np.isfinite(values[name])
            ]
            component_sum = float(sum(component_values)) if component_values else np.nan
            candidates = (
                ("PRIMARY_REPORTED_TOTAL_RECONCILED_TO_COMPONENTS", values["reported_total_primary_usd"]),
                ("ALTERNATE_REPORTED_TOTAL_RECONCILED_TO_COMPONENTS", values["reported_total_alternate_usd"]),
            )
            selected = np.nan
            method = "LOCKED_NO_RECONCILED_ALL_IN_TOTAL"
            selected_source_tag = ""
            reconciliation_error = np.nan
            for candidate_method, candidate in candidates:
                if (
                    np.isfinite(candidate)
                    and candidate > 0
                    and np.isfinite(component_sum)
                    and component_sum > 0
                ):
                    error = abs(candidate / component_sum - 1.0)
                    if error <= 0.05:
                        selected = candidate
                        method = candidate_method
                        selected_source_tag = (
                            "us-gaap:CostsIncurredAcquisitionOfOilAndGasProperties"
                            if candidate_method.startswith("PRIMARY")
                            else "us-gaap:CostsIncurredOilAndGasPropertyAcquisitionExplorationAndDevelopmentActivities"
                        )
                        reconciliation_error = error
                        break
            all_components = all(np.isfinite(values[name]) for name in component_names)
            if not np.isfinite(selected) and all_components and component_sum > 0:
                selected = component_sum
                method = "SUM_OF_DEVELOPMENT_EXPLORATION_PROVED_AND_UNPROVED_ACQUISITION"
                selected_source_tag = ";".join(
                    f"us-gaap:{ALL_IN_TAGS[name]}" for name in component_names
                )
                reconciliation_error = 0.0
            rows.append(
                {
                    "ticker": ticker,
                    "year": year,
                    **values,
                    "observed_component_sum_usd": component_sum,
                    "selected_all_in_reserve_investment_usd": selected,
                    "all_in_cost_selection_method": method,
                    "selected_all_in_source_tags": selected_source_tag,
                    "reported_total_component_reconciliation_error": reconciliation_error,
                    "included_scope": "DEVELOPMENT_EXPLORATION_PROVED_AND_UNPROVED_ACQUISITION",
                    "excluded_or_unproven_scope": (
                        "LEASEHOLD_INFRASTRUCTURE_CORPORATE_CAPITAL_DRY_HOLE_OVERLAP_"
                        "AND_ACQUISITION_PREMIUM_NOT_SEPARATELY_PROVEN"
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(["ticker", "year"]).reset_index(drop=True)


def build_reserve_roic_scope_cross_check(
    *,
    route_panel: pd.DataFrame,
    all_in_cost: pd.DataFrame,
    v13_cross_path: Path,
    v14_cross_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    annual = route_panel.merge(all_in_cost, on=["ticker", "year"], how="inner")
    denominator = annual["total_gross_reserve_additions_mboe"] * 1_000.0
    annual["observed_all_in_cost_per_gross_added_boe"] = (
        annual["selected_all_in_reserve_investment_usd"] / denominator
    )
    annual["all_in_cost_per_boe_status"] = np.where(
        annual["observed_all_in_cost_per_gross_added_boe"].gt(0)
        & np.isfinite(annual["observed_all_in_cost_per_gross_added_boe"]),
        "OBSERVED_ALL_IN_COST_PER_GROSS_ADDED_BOE",
        "LOCKED_INVALID_OR_MISSING_ALL_IN_COST_DENOMINATOR",
    )
    v13 = pd.read_csv(v13_cross_path).set_index("ticker")
    v14 = pd.read_csv(v14_cross_path).set_index("ticker")
    rows = []
    for ticker in EP_TICKERS:
        history = annual.loc[
            annual["ticker"].eq(ticker)
            & annual["all_in_cost_per_boe_status"].eq(
                "OBSERVED_ALL_IN_COST_PER_GROSS_ADDED_BOE"
            )
        ]
        years = len(history)
        all_in_per_boe = (
            float(history["observed_all_in_cost_per_gross_added_boe"].median())
            if years >= 3
            else np.nan
        )
        project_roic = (
            float(v14.loc[ticker, "v14_known_cost_roic_proxy_q50_pct"])
            if ticker in v14.index
            else np.nan
        )
        development = (
            float(v13.loc[ticker, "normalized_development_cost_per_added_boe"])
            if ticker in v13.index
            else np.nan
        )
        company_scope_roic = (
            project_roic * development / all_in_per_boe
            if np.isfinite(project_roic)
            and np.isfinite(development)
            and np.isfinite(all_in_per_boe)
            and all_in_per_boe > 0
            else np.nan
        )
        rows.append(
            {
                "ticker": ticker,
                "observed_all_in_reserve_cost_years": years,
                "project_development_cost_per_added_boe": development,
                "observed_all_in_cost_per_gross_added_boe": all_in_per_boe,
                "project_development_roic_proxy_q50_pct": project_roic,
                "company_scope_all_in_reserve_roic_proxy_q50_pct": company_scope_roic,
                "roic_reduction_from_project_to_company_scope_pct_points": (
                    project_roic - company_scope_roic
                    if np.isfinite(company_scope_roic)
                    else np.nan
                ),
                "roic_scope_status": (
                    "OBSERVED_DEV_EXPLORATION_ACQUISITION_SCOPE_NOT_FULL_COMPANY_INCREMENTAL_ROIC"
                    if years >= 3 and np.isfinite(company_scope_roic)
                    else "LOCKED_NO_COMPLETE_UNIT_MARGIN_OR_PROJECT_ROIC"
                    if years >= 3
                    else "LOCKED_FEWER_THAN_3_ALL_IN_COST_YEARS"
                ),
                "project_roic_equals_company_incremental_roic": False,
                "company_incremental_roic_validated": False,
                "terminal_anchor_ready": False,
                "research_only": True,
            }
        )
    return annual, pd.DataFrame(rows)


def build_production_mix_coverage(basis_path: Path) -> pd.DataFrame:
    basis = pd.read_csv(basis_path)
    basis = basis.loc[basis["year"].between(2021, 2025)]
    rows = []
    for ticker in EP_TICKERS:
        history = basis.loc[basis["ticker"].eq(ticker)]
        rows.append(
            {
                "ticker": ticker,
                "basis_years": len(history),
                "audited_all_component_mix_years": int(
                    history["mix_method"].eq("AUDITED_ALL_COMPONENTS").sum()
                ),
                "single_residual_component_years": int(
                    history["mix_method"].eq(
                        "SINGLE_MISSING_COMPONENT_DERIVED_AS_RESIDUAL"
                    ).sum()
                ),
                "group_prior_allocated_mix_years": int(
                    history["mix_method"].eq(
                        "MULTIPLE_MISSING_COMPONENTS_ALLOCATED_WITH_GROUP_PRIOR"
                    ).sum()
                ),
                "actual_mix_ready": bool(
                    len(history) >= 3
                    and history["mix_method"].eq("AUDITED_ALL_COMPONENTS").all()
                ),
            }
        )
    return pd.DataFrame(rows)


def build_reserve_coverage_and_cost_research(
    *,
    companyfacts_root: Path,
    production_path: Path,
    v13_coverage_path: Path,
    v13_cross_path: Path,
    v14_cross_path: Path,
    v14_basis_path: Path,
) -> dict[str, pd.DataFrame]:
    route_panel = build_route_aware_reserve_panel(companyfacts_root, production_path)
    coverage = build_reserve_coverage_summary(route_panel, v13_coverage_path)
    all_in = build_annual_all_in_cost_panel(companyfacts_root)
    annual_roic, roic = build_reserve_roic_scope_cross_check(
        route_panel=route_panel,
        all_in_cost=all_in,
        v13_cross_path=v13_cross_path,
        v14_cross_path=v14_cross_path,
    )
    return {
        "route_aware_reserve_panel": route_panel,
        "reserve_coverage_summary": coverage,
        "annual_all_in_reserve_cost": all_in,
        "annual_reserve_roic_scope_panel": annual_roic,
        "reserve_roic_scope_cross_check": roic,
        "production_mix_coverage": build_production_mix_coverage(v14_basis_path),
    }
