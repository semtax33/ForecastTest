from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.research.ep_v13.unit_economics import build_annual_production_kpi
from energy_nowcast.research.phase6.financial_targets import EP_TICKERS
from equity_platform.sectors.energy.research.revenue.v35.taxonomy import GROUP_PRICE_WEIGHTS, group_for_ticker
from energy_nowcast.research.v351.revenue import CIKS


@dataclass(frozen=True)
class TagRoute:
    tag: str
    scope: str


ROUTES: dict[str, tuple[TagRoute, ...]] = {
    "transport_cost_usd": (
        TagRoute("ResultsOfOperationsTransportationCosts", "UPSTREAM_EXACT"),
    ),
    "production_tax_usd": (
        TagRoute("ProductionTaxExpense", "PRODUCTION_TAX_EXACT"),
    ),
    "g_and_a_usd": (
        TagRoute(
            "ResultsOfOperationsGeneralAndAdministrativeRelatedToOilAndGasProducingActivities",
            "UPSTREAM_EXACT",
        ),
        TagRoute("GeneralAndAdministrativeExpense", "CONSOLIDATED_ALLOCATED"),
        TagRoute("SellingGeneralAndAdministrativeExpense", "CONSOLIDATED_ALLOCATED"),
    ),
    "hedge_gain_loss_usd": (
        TagRoute("GainLossOnOilAndGasHedgingActivity", "OIL_GAS_HEDGE_EXACT"),
        TagRoute("GainLossOnDerivativeInstrumentsNetPretax", "DERIVATIVE_BROAD"),
        TagRoute("DerivativeGainLossOnDerivativeNet", "DERIVATIVE_BROAD"),
        TagRoute(
            "DerivativeInstrumentsNotDesignatedAsHedgingInstrumentsGainLossNet",
            "DERIVATIVE_BROAD",
        ),
    ),
    "upstream_revenue_usd": (
        TagRoute(
            "ResultsOfOperationsRevenueFromOilAndGasProducingActivities",
            "UPSTREAM_EXACT",
        ),
        TagRoute("OilAndGasSalesRevenue", "OIL_GAS_SALES_BROAD"),
        TagRoute("OilAndGasRevenue", "OIL_GAS_SALES_BROAD"),
    ),
}


def _payload(companyfacts_root: Path, ticker: str) -> dict[str, object]:
    path = companyfacts_root / f"CIK{CIKS[ticker]:010d}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _annual_original_usd(
    payload: dict[str, object], tag: str
) -> pd.DataFrame:
    fact = payload.get("facts", {}).get("us-gaap", {}).get(tag, {})
    frame = pd.DataFrame(fact.get("units", {}).get("USD", []))
    if frame.empty or not {"start", "end", "filed", "val", "form"}.issubset(frame):
        return pd.DataFrame()
    for column in ("start", "end", "filed"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame["val"] = pd.to_numeric(frame["val"], errors="coerce")
    frame["fy"] = pd.to_numeric(frame.get("fy"), errors="coerce")
    duration = (frame["end"] - frame["start"]).dt.days + 1
    eligible = frame.loc[
        frame["form"].astype(str).eq("10-K")
        & duration.between(330, 380)
        & frame["fy"].eq(frame["end"].dt.year)
        & frame["filed"].sub(frame["end"]).dt.days.between(0, 180)
        & frame["val"].notna()
    ].copy()
    if eligible.empty:
        return eligible
    eligible["year"] = eligible["end"].dt.year.astype(int)
    return (
        eligible.sort_values(["year", "filed", "accn"])
        .drop_duplicates("year", keep="first")
        .reset_index(drop=True)
    )


def _routed_history(
    payload: dict[str, object], routes: tuple[TagRoute, ...], output: str
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for priority, route in enumerate(routes):
        values = _annual_original_usd(payload, route.tag)
        if values.empty:
            continue
        values["route_priority"] = priority
        values[f"{output}_source_tag"] = f"us-gaap:{route.tag}"
        values[f"{output}_scope"] = route.scope
        parts.append(values)
    if not parts:
        return pd.DataFrame(
            columns=["year", output, f"{output}_source_tag", f"{output}_scope"]
        )
    combined = pd.concat(parts, ignore_index=True).sort_values(
        ["year", "route_priority", "filed"]
    )
    selected = combined.drop_duplicates("year", keep="first")
    return selected[
        ["year", "val", f"{output}_source_tag", f"{output}_scope"]
    ].rename(columns={"val": output})


def extract_standardized_cost_scope(
    companyfacts_root: Path,
    production: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    annual_production = build_annual_production_kpi(production)
    annual_production = annual_production.loc[
        annual_production["kpi_production_mboe"].notna()
    ].copy()
    panels: list[pd.DataFrame] = []
    audits: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        payload = _payload(companyfacts_root, ticker)
        histories = {
            output: _routed_history(payload, routes, output)
            for output, routes in ROUTES.items()
        }
        for output, history in histories.items():
            recent = history.loc[history["year"].between(2021, 2025)]
            audits.append(
                {
                    "ticker": ticker,
                    "concept": output,
                    "standardized_tag_years_2021_2025": len(recent),
                    "latest_standardized_year": (
                        int(history["year"].max()) if len(history) else np.nan
                    ),
                    "selected_source_tags_2021_2025": (
                        ";".join(sorted(set(recent[f"{output}_source_tag"])))
                        if len(recent)
                        else ""
                    ),
                    "selected_scopes_2021_2025": (
                        ";".join(sorted(set(recent[f"{output}_scope"])))
                        if len(recent)
                        else ""
                    ),
                }
            )
        frame = annual_production.loc[annual_production["ticker"].eq(ticker)].copy()
        for output, history in histories.items():
            frame = frame.merge(history, on="year", how="left")
        if not frame.empty:
            panels.append(frame)
    panel = pd.concat(
        [frame.dropna(axis=1, how="all") for frame in panels],
        ignore_index=True,
        sort=False,
    )
    denominator = panel["kpi_production_mboe"] * 1_000.0
    for output in ROUTES:
        panel[output.replace("_usd", "_per_boe")] = panel[output] / denominator
    return (
        panel.sort_values(["ticker", "year"]).reset_index(drop=True),
        pd.DataFrame(audits).sort_values(["ticker", "concept"]).reset_index(drop=True),
    )


def build_annual_benchmark_basis(
    production: pd.DataFrame,
    prices: pd.DataFrame,
    cost_panel: pd.DataFrame,
) -> pd.DataFrame:
    actuals = production.copy()
    actuals["quarter"] = actuals["quarter"].astype(str)
    actuals["year"] = actuals["quarter"].str[:4].astype(int)
    actuals["days"] = actuals["quarter"].map(
        lambda value: (
            pd.Period(value, freq="Q").end_time.normalize()
            - pd.Period(value, freq="Q").start_time.normalize()
        ).days
        + 1
    )
    price = prices.copy()
    price["quarter"] = price["quarter"].astype(str)
    price["year"] = price["quarter"].str[:4].astype(int)
    annual_prices = price.groupby("year", as_index=False).agg(
        annual_wti_usd_per_bbl=("wti_price", "mean"),
        annual_henry_usd_per_mcf=("henry_price", "mean"),
        annual_propane_usd_per_bbl=("propane_price_bbl", "mean"),
        price_quarters=("quarter", "nunique"),
    )
    cost_lookup = cost_panel.set_index(["ticker", "year"])
    rows: list[dict[str, object]] = []
    for (ticker, year), group in actuals.groupby(["ticker", "year"], sort=True):
        if group["quarter"].nunique() != 4 or (ticker, year) not in cost_lookup.index:
            continue
        total = float(
            (pd.to_numeric(group["total_mboed"], errors="coerce") * group["days"]).sum()
        )
        if not np.isfinite(total) or total <= 0:
            continue
        component_values = {
            "oil": (
                pd.to_numeric(group["oil_mbpd"], errors="coerce") * group["days"]
            ).sum(min_count=1),
            "ngl": (
                pd.to_numeric(group["ngl_mbpd"], errors="coerce") * group["days"]
            ).sum(min_count=1),
            "gas": (
                pd.to_numeric(group["gas_mmcfd"], errors="coerce")
                / 6.0
                * group["days"]
            ).sum(min_count=1),
        }
        known = {
            key: float(value / total)
            for key, value in component_values.items()
            if np.isfinite(value) and value >= 0
        }
        missing = [key for key in ("oil", "ngl", "gas") if key not in known]
        remaining = max(1.0 - sum(known.values()), 0.0)
        group_prior = GROUP_PRICE_WEIGHTS[group_for_ticker(ticker)]
        missing_weight = sum(group_prior[key] for key in missing)
        mix = dict(known)
        for key in missing:
            mix[key] = (
                remaining * group_prior[key] / missing_weight
                if missing_weight
                else 0.0
            )
        scale = sum(mix.values())
        if scale <= 0:
            continue
        mix = {key: value / scale for key, value in mix.items()}
        mix_method = (
            "AUDITED_ALL_COMPONENTS"
            if not missing
            else "SINGLE_MISSING_COMPONENT_DERIVED_AS_RESIDUAL"
            if len(missing) == 1
            else "MULTIPLE_MISSING_COMPONENTS_ALLOCATED_WITH_GROUP_PRIOR"
        )
        selected_price = annual_prices.loc[annual_prices["year"].eq(year)]
        if selected_price.empty or int(selected_price.iloc[0]["price_quarters"]) != 4:
            continue
        p = selected_price.iloc[0]
        basket = (
            mix["oil"] * float(p["annual_wti_usd_per_bbl"])
            + mix["ngl"] * float(p["annual_propane_usd_per_bbl"])
            + mix["gas"] * float(p["annual_henry_usd_per_mcf"]) * 6.0
        )
        costs = cost_lookup.loc[(ticker, year)]
        upstream_revenue = float(costs["upstream_revenue_per_boe"])
        exact_revenue = costs["upstream_revenue_usd_scope"] == "UPSTREAM_EXACT"
        basis = upstream_revenue - basket if exact_revenue and np.isfinite(upstream_revenue) else np.nan
        rows.append(
            {
                "ticker": ticker,
                "year": year,
                "mix_method": mix_method,
                "oil_mix_pct": mix["oil"] * 100.0,
                "ngl_mix_pct": mix["ngl"] * 100.0,
                "gas_boe_mix_pct": mix["gas"] * 100.0,
                "benchmark_basket_usd_per_boe": basket,
                "upstream_revenue_per_boe": upstream_revenue,
                "upstream_revenue_scope": costs["upstream_revenue_usd_scope"],
                "realized_revenue_basis_per_boe": basis,
                "basis_confidence": (
                    "HIGH_EXACT_REVENUE_AUDITED_OR_RESIDUAL_MIX"
                    if exact_revenue and len(missing) <= 1
                    else "MEDIUM_EXACT_REVENUE_GROUP_PRIOR_MIX"
                    if exact_revenue
                    else "LOCKED_NO_EXACT_UPSTREAM_REVENUE"
                ),
                "basis_semantics": (
                    "UPSTREAM_REVENUE_PER_BOE_MINUS_BENCHMARK_MIX_NOT_PURE_PRICE_DIFFERENTIAL"
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["ticker", "year"]).reset_index(drop=True)


def build_cost_scope_coverage(
    cost_panel: pd.DataFrame,
    tag_audit: pd.DataFrame,
    basis: pd.DataFrame,
) -> pd.DataFrame:
    tag_pivot = tag_audit.pivot(
        index="ticker",
        columns="concept",
        values="standardized_tag_years_2021_2025",
    ).add_prefix("tag_").add_suffix("_years_5y")
    rows: list[dict[str, object]] = []
    for ticker in EP_TICKERS:
        history = cost_panel.loc[
            cost_panel["ticker"].eq(ticker) & cost_panel["year"].between(2021, 2025)
        ]
        ticker_basis = basis.loc[
            basis["ticker"].eq(ticker) & basis["year"].between(2021, 2025)
        ]
        row: dict[str, object] = {
            "ticker": ticker,
            "complete_production_years_5y": len(history),
            "exact_realized_basis_years_5y": int(
                ticker_basis["realized_revenue_basis_per_boe"].notna().sum()
            ),
        }
        for output in ROUTES:
            per_boe = output.replace("_usd", "_per_boe")
            row[f"{per_boe}_years_5y"] = int(history[per_boe].notna().sum())
        row["standardized_complete_cost_scope"] = all(
            row[column] >= 3
            for column in (
                "transport_cost_per_boe_years_5y",
                "production_tax_per_boe_years_5y",
                "g_and_a_per_boe_years_5y",
                "exact_realized_basis_years_5y",
            )
        )
        rows.append(row)
    result = pd.DataFrame(rows).set_index("ticker").join(tag_pivot, how="left")
    return result.reset_index().sort_values("ticker").reset_index(drop=True)


def build_expanded_core_cross_check(
    frozen_v13_cross: pd.DataFrame,
    cost_panel: pd.DataFrame,
    basis: pd.DataFrame,
    v11_assumptions: pd.DataFrame,
) -> pd.DataFrame:
    base = v11_assumptions.loc[
        v11_assumptions["scenario"].eq("BASE")
        & v11_assumptions["subindustry"].eq("ep")
    ].set_index("ticker")
    basis_lookup = basis.set_index(["ticker", "year"])
    rows: list[dict[str, object]] = []
    for frozen in frozen_v13_cross.itertuples(index=False):
        ticker = str(frozen.ticker)
        row: dict[str, object] = {
            "ticker": ticker,
            "v13_unit_economics_status": frozen.unit_economics_status,
            "v13_historical_margin_q50_pct": frozen.v12_historical_margin_q50_pct,
            "v13_core_accounting_margin_q50_pct": getattr(
                frozen, "commodity_normalized_accounting_margin_q50_pct", np.nan
            ),
            "v13_core_roic_proxy_q50_pct": getattr(
                frozen, "reserve_replacement_roic_proxy_q50_pct", np.nan
            ),
            "terminal_anchor_ready": False,
            "production_eligible": False,
            "research_only": True,
        }
        if frozen.unit_economics_status != "CORE_STANDARDIZED_RESERVE_REPLACEMENT_CROSS_CHECK":
            row["v14_cost_scope_status"] = "LOCKED_NO_V13_CORE_RESERVE_REPLACEMENT_CHAIN"
            rows.append(row)
            continue
        history = cost_panel.loc[
            cost_panel["ticker"].eq(ticker) & cost_panel["year"].between(2021, 2025)
        ].copy()
        basis_values = []
        for year in history["year"]:
            if (ticker, year) in basis_lookup.index:
                basis_values.append(
                    basis_lookup.loc[(ticker, year), "realized_revenue_basis_per_boe"]
                )
        basis_series = pd.to_numeric(pd.Series(basis_values), errors="coerce").dropna()
        ticker_basis = basis.loc[
            basis["ticker"].eq(ticker) & basis["year"].between(2021, 2025),
            ["year", "realized_revenue_basis_per_boe"],
        ]
        hedge_pair = ticker_basis.merge(
            history[
                ["year", "hedge_gain_loss_per_boe", "hedge_gain_loss_usd_scope"]
            ],
            on="year",
            how="inner",
        ).dropna(
            subset=["realized_revenue_basis_per_boe", "hedge_gain_loss_per_boe"]
        )
        component_columns = {
            "transport": "transport_cost_per_boe",
            "production_tax": "production_tax_per_boe",
            "g_and_a": "g_and_a_per_boe",
            "hedge": "hedge_gain_loss_per_boe",
        }
        observations = {
            name: int(history[column].notna().sum())
            for name, column in component_columns.items()
        }
        observations["realized_basis"] = len(basis_series)
        row.update({f"{key}_observations_5y": value for key, value in observations.items()})
        medians = {
            name: float(history[column].median()) if observations[name] >= 3 else np.nan
            for name, column in component_columns.items()
        }
        basis_median = float(basis_series.median()) if len(basis_series) >= 3 else np.nan
        complete = all(
            observations[name] >= 3
            for name in ("transport", "production_tax", "g_and_a", "realized_basis")
        )
        row["v14_cost_scope_status"] = (
            "COMPLETE_STANDARDIZED_COST_SCOPE_CROSS_CHECK"
            if complete
            else "UPPER_BOUND_MISSING_" + "_AND_".join(
                name.upper()
                for name in ("transport", "production_tax", "g_and_a", "realized_basis")
                if observations[name] < 3
            )
        )
        row["median_transport_cost_per_boe"] = medians["transport"]
        row["median_production_tax_per_boe"] = medians["production_tax"]
        row["median_g_and_a_per_boe"] = medians["g_and_a"]
        row["median_reported_hedge_gain_loss_per_boe"] = medians["hedge"]
        row["median_abs_reported_hedge_gain_loss_per_boe"] = (
            float(hedge_pair["hedge_gain_loss_per_boe"].abs().median())
            if len(hedge_pair) >= 3
            else np.nan
        )
        row["normalized_hedge_gain_loss_per_boe"] = 0.0
        row["hedge_normalization_status"] = (
            "QUANTIFIED_SEPARATELY_ZERO_LONG_RUN_NOT_NETTED_WITHOUT_REVENUE_INCLUSION_PROOF"
            if observations["hedge"] >= 3
            else "LOCKED_INSUFFICIENT_HEDGE_HISTORY"
        )
        row["median_realized_revenue_basis_per_boe"] = basis_median
        row["realized_revenue_basis_iqr_per_boe"] = (
            float(basis_series.quantile(0.75) - basis_series.quantile(0.25))
            if len(basis_series) >= 3
            else np.nan
        )
        if (
            len(hedge_pair) >= 3
            and hedge_pair["realized_revenue_basis_per_boe"].std() > 0
            and hedge_pair["hedge_gain_loss_per_boe"].std() > 0
        ):
            hedge_correlation = float(
                hedge_pair["realized_revenue_basis_per_boe"].corr(
                    hedge_pair["hedge_gain_loss_per_boe"]
                )
            )
            ex_hedge_diagnostic = float(
                (
                    hedge_pair["realized_revenue_basis_per_boe"]
                    - hedge_pair["hedge_gain_loss_per_boe"]
                ).median()
            )
        else:
            hedge_correlation = ex_hedge_diagnostic = np.nan
        exact_hedge_scope = (
            len(hedge_pair) >= 3
            and hedge_pair["hedge_gain_loss_usd_scope"].eq(
                "OIL_GAS_HEDGE_EXACT"
            ).all()
        )
        row["basis_hedge_paired_observations_5y"] = len(hedge_pair)
        row["basis_hedge_correlation"] = hedge_correlation
        row["median_basis_ex_reported_hedge_diagnostic_per_boe"] = (
            ex_hedge_diagnostic
        )
        row["hedge_inclusion_diagnostic"] = (
            "STRONG_EXACT_HEDGE_ASSOCIATION_REVENUE_INCLUSION_NOT_PROVEN"
            if exact_hedge_scope
            and np.isfinite(hedge_correlation)
            and abs(hedge_correlation) >= 0.9
            else "NO_MECHANICAL_NETTING_REVENUE_INCLUSION_NOT_PROVEN"
        )
        row["hedge_adjusted_basis_applied"] = False
        row["realized_basis_status"] = (
            "EXACT_UPSTREAM_REVENUE_BASIS_CROSS_CHECK"
            if observations["realized_basis"] >= 3
            else "LOCKED_INSUFFICIENT_EXACT_UPSTREAM_REVENUE_BASIS"
        )
        gross = float(frozen.normalized_gross_price_q50_per_boe)
        realized = gross + basis_median if np.isfinite(basis_median) else np.nan
        row["v14_realized_basis_adjusted_price_q50_per_boe"] = realized
        basis_iqr = row["realized_revenue_basis_iqr_per_boe"]
        row["basis_iqr_pct_of_adjusted_price"] = (
            basis_iqr / abs(realized) * 100.0
            if np.isfinite(basis_iqr) and np.isfinite(realized) and realized != 0
            else np.nan
        )
        row["basis_dispersion_status"] = (
            "HIGH_DISPERSION_GT_25PCT_OF_ADJUSTED_PRICE"
            if row["basis_iqr_pct_of_adjusted_price"] > 25.0
            else "LOWER_DISPERSION_LE_25PCT_OF_ADJUSTED_PRICE"
            if np.isfinite(row["basis_iqr_pct_of_adjusted_price"])
            else "LOCKED_INSUFFICIENT_BASIS_HISTORY"
        )
        known_costs = [
            float(frozen.normalized_lifting_cost_per_boe),
            float(frozen.normalized_dda_per_boe),
        ]
        cash_costs = [float(frozen.normalized_lifting_cost_per_boe)]
        for name in ("transport", "production_tax", "g_and_a"):
            if np.isfinite(medians[name]):
                known_costs.append(medians[name])
                cash_costs.append(medians[name])
        development = float(frozen.normalized_development_cost_per_added_boe)
        if np.isfinite(realized) and realized > 0:
            accounting_margin = (realized - sum(known_costs)) / realized * 100.0
            replacement_margin = (
                realized - sum(cash_costs) - development
            ) / realized * 100.0
            after_tax_profit = (realized - sum(known_costs)) * (
                1.0 - float(base.loc[ticker, "tax_rate_pct"]) / 100.0
            )
            roic = after_tax_profit / development * 100.0 if development > 0 else np.nan
        else:
            accounting_margin = replacement_margin = roic = np.nan
        row["v14_known_cost_accounting_margin_q50_pct"] = accounting_margin
        row["v14_known_cost_replacement_cash_margin_q50_pct"] = replacement_margin
        row["v14_known_cost_roic_proxy_q50_pct"] = roic
        row["v14_margin_gap_vs_v13_historical_q50_pct_points"] = (
            accounting_margin - float(frozen.v12_historical_margin_q50_pct)
        )
        row["absolute_margin_gap_improvement_vs_v13_core_pct_points"] = (
            abs(
                float(frozen.commodity_normalized_accounting_margin_q50_pct)
                - float(frozen.v12_historical_margin_q50_pct)
            )
            - abs(row["v14_margin_gap_vs_v13_historical_q50_pct_points"])
        )
        row["roic_proxy_reduction_vs_v13_pct_points"] = (
            float(frozen.reserve_replacement_roic_proxy_q50_pct) - roic
        )
        row["margin_semantics"] = (
            "COMPLETE_STANDARDIZED_COST_SCOPE_CROSS_CHECK"
            if complete
            else "KNOWN_COST_UPPER_BOUND_MISSING_COMPONENTS_NOT_ZERO_FILLED"
        )
        row["roic_cross_check_status"] = (
            "BELOW_100PCT_AFTER_COMPLETE_COST_SCOPE_NOT_VALIDATED"
            if complete and np.isfinite(roic) and roic < 100.0
            else "UPPER_BOUND_BELOW_100PCT_STILL_INCOMPLETE"
            if not complete and np.isfinite(roic) and roic < 100.0
            else "ABOVE_100PCT_OR_UNAVAILABLE_REQUIRES_MORE_COST_SCOPE"
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def build_cost_scope_gate(
    coverage: pd.DataFrame,
    cross_check: pd.DataFrame,
) -> pd.DataFrame:
    complete = cross_check["v14_cost_scope_status"].eq(
        "COMPLETE_STANDARDIZED_COST_SCOPE_CROSS_CHECK"
    )
    return pd.DataFrame(
        [{
            "ep_tickers": len(coverage),
            "standardized_complete_cost_scope_tickers": int(
                coverage["standardized_complete_cost_scope"].sum()
            ),
            "v13_core_cross_check_tickers": int(
                cross_check["v13_unit_economics_status"].eq(
                    "CORE_STANDARDIZED_RESERVE_REPLACEMENT_CROSS_CHECK"
                ).sum()
            ),
            "v14_complete_core_cross_check_tickers": int(complete.sum()),
            "v14_roic_below_100pct_core_tickers": int(
                pd.to_numeric(
                    cross_check["v14_known_cost_roic_proxy_q50_pct"],
                    errors="coerce",
                ).lt(100.0).sum()
            ),
            "v14_complete_core_roic_below_100pct_tickers": int(
                cross_check["roic_cross_check_status"].eq(
                    "BELOW_100PCT_AFTER_COMPLETE_COST_SCOPE_NOT_VALIDATED"
                ).sum()
            ),
            "high_basis_dispersion_core_tickers": int(
                cross_check["basis_dispersion_status"].eq(
                    "HIGH_DISPERSION_GT_25PCT_OF_ADJUSTED_PRICE"
                ).sum()
            ),
            "terminal_anchor_ready_tickers": int(
                cross_check["terminal_anchor_ready"].sum()
            ),
            "terminal_anchor_replacement_allowed": False,
            "v1_1_mutation_allowed": False,
            "wacc_range_recalibrated": False,
            "risk_channel_duplicate_count": 0,
            "production_eligible": False,
            "live_matched_observations": "0/20",
        }]
    )


def build_cost_scope_research(
    *,
    companyfacts_root: Path,
    production_path: Path,
    price_path: Path,
    frozen_v13_cross_path: Path,
    v11_assumptions_path: Path,
) -> dict[str, pd.DataFrame]:
    production = pd.read_csv(production_path)
    prices = pd.read_csv(price_path)
    cost_panel, tag_audit = extract_standardized_cost_scope(
        companyfacts_root, production
    )
    basis = build_annual_benchmark_basis(production, prices, cost_panel)
    coverage = build_cost_scope_coverage(cost_panel, tag_audit, basis)
    cross_check = build_expanded_core_cross_check(
        pd.read_csv(frozen_v13_cross_path),
        cost_panel,
        basis,
        pd.read_csv(v11_assumptions_path),
    )
    gate = build_cost_scope_gate(coverage, cross_check)
    return {
        "standardized_tag_coverage": tag_audit,
        "annual_cost_scope_panel": cost_panel,
        "annual_realized_basis_panel": basis,
        "cost_scope_coverage": coverage,
        "expanded_core_cross_check": cross_check,
        "cost_scope_gate": gate,
    }
