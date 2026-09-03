from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.industry_data.pqci import load_bls_snapshot, load_census_m3_snapshot


GRADE_WEIGHT = {"A": 1.0, "B": 0.8, "C": 0.5, "D": 0.25, "E": 0.0}


def _signal(series: pd.DataFrame, transformation: str) -> dict[str, object]:
    values = series.sort_values("observation_date").set_index("observation_date")["value"]
    latest_date = values.index.max()
    latest = float(values.loc[latest_date])
    prior_date = latest_date - pd.DateOffset(years=1)
    prior = values.get(prior_date, np.nan)
    latest_yoy = latest / float(prior) * 100.0 - 100.0 if pd.notna(prior) else np.nan
    current = values.loc[values.index.year == latest_date.year]
    prior_ytd = values.loc[
        (values.index.year == latest_date.year - 1)
        & (values.index.month.isin(current.index.month))
    ]
    ytd_yoy = (
        float(current.sum() / prior_ytd.sum() * 100.0 - 100.0)
        if len(current) == len(prior_ytd) and prior_ytd.sum() != 0
        else np.nan
    )
    recent = values.tail(3)
    preceding = values.iloc[-6:-3]
    three_month = (
        float(recent.mean() / preceding.mean() * 100.0 - 100.0)
        if len(recent) == len(preceding) == 3 and preceding.mean() != 0
        else np.nan
    )
    selected = {
        "latest_yoy": latest_yoy,
        "ytd_yoy": ytd_yoy,
        "three_month_momentum": three_month,
    }[transformation]
    return {
        "latest_observation_date": latest_date.date().isoformat(),
        "latest_value": latest,
        "latest_yoy_pct": latest_yoy,
        "ytd_yoy_pct": ytd_yoy,
        "three_month_momentum_pct": three_month,
        "selected_signal_pct": selected,
    }


def build_cat_industry_forecast(
    *,
    segment_history: pd.DataFrame,
    sensor_map_path: Path,
    category_weights_path: Path,
    census_snapshot_path: Path,
    bls_snapshot_path: Path,
    cutoff: pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    sensors = pd.read_csv(sensor_map_path)
    weights = pd.read_csv(category_weights_path).set_index("category_code")["weight"]
    if not np.isclose(weights.sum(), 1.0):
        raise ValueError("CAT industry category weights must sum to one")
    m3 = load_census_m3_snapshot(census_snapshot_path, cutoff)
    bls = load_bls_snapshot(bls_snapshot_path, cutoff)
    rows: list[dict[str, object]] = []
    for sensor in sensors.to_dict("records"):
        if sensor["source"] == "Census":
            category_rows: list[dict[str, object]] = []
            for category in str(sensor["categories"]).split("|"):
                subset = m3.loc[
                    m3["category_code"].eq(category)
                    & m3["data_type_code"].eq(sensor["data_type_code"])
                    & m3["seasonally_adj"].eq("yes")
                ]
                if subset.empty:
                    raise ValueError(f"Census M3 sensor missing: {category}:{sensor['data_type_code']}")
                item = _signal(subset, str(sensor["transformation"]))
                item.update({"category_code": category, "category_weight": weights[category]})
                category_rows.append(item)
            category_frame = pd.DataFrame(category_rows)
            aggregate = {
                key: float(np.average(category_frame[key], weights=category_frame["category_weight"]))
                for key in [
                    "latest_value",
                    "latest_yoy_pct",
                    "ytd_yoy_pct",
                    "three_month_momentum_pct",
                    "selected_signal_pct",
                ]
            }
            latest_date = category_frame["latest_observation_date"].max()
        else:
            subset = bls.loc[bls["series_id"].eq(sensor["data_type_code"])]
            if subset.empty:
                raise ValueError(f"BLS sensor missing: {sensor['data_type_code']}")
            aggregate = _signal(subset, str(sensor["transformation"]))
            latest_date = aggregate.pop("latest_observation_date")
        rows.append(
            {
                **sensor,
                **aggregate,
                "latest_observation_date": latest_date,
                "grade_weight": GRADE_WEIGHT[str(sensor["grade"])],
                "forecast_use": (
                    "FORECAST" if sensor["economic_role"] == "LEADING" else "NOWCAST"
                ),
                "vintage_status": "LATEST_REVISED_SNAPSHOT_NO_HISTORICAL_RELEASE_DATE",
                "snapshot_retrieved_at": subset["retrieved_at"].max().isoformat(),
                "release_date_status": "NOT_PRESERVED_IN_ARCANA_SNAPSHOT",
                "historical_pit_backtest_eligible": False,
                "production_eligible": False,
            }
        )
    signals = pd.DataFrame(rows)
    signals["effective_weight"] = signals["weight"] * signals["grade_weight"]

    def weighted_target(target: str) -> float:
        group = signals.loc[signals["target"].eq(target)]
        return float(np.average(group["selected_signal_pct"], weights=group["effective_weight"]))

    revenue_growth = weighted_target("revenue_growth")
    cost_growth = weighted_target("cost_growth")
    inventory_growth = weighted_target("reinvestment")
    latest = segment_history.iloc[-1]
    window = segment_history.tail(5)
    base_revenue = float(latest["mpe_total_revenue_usd"])
    base_ebit = float(latest["mpe_operating_profit_usd"])
    base_cost = base_revenue - base_ebit
    forecast_revenue = base_revenue * (1.0 + revenue_growth / 100.0)
    forecast_cost = base_cost * (1.0 + cost_growth / 100.0)
    forecast_ebit = forecast_revenue - forecast_cost
    tax_rate = float(window["mpe_effective_tax_rate_pct"].median())
    forecast_nopat = forecast_ebit * (1.0 - tax_rate / 100.0)
    base_nopat = float(latest["mpe_nopat_usd"])
    base_capital = float(latest["mpe_invested_capital_usd"])
    historical_sales_to_capital = float(
        (window["mpe_total_revenue_usd"] / window["mpe_invested_capital_usd"]).median()
    )
    forecast_sales_to_capital = historical_sales_to_capital / (1.0 + inventory_growth / 100.0)
    incremental_revenue = forecast_revenue - base_revenue
    required_reinvestment = incremental_revenue / forecast_sales_to_capital
    forecast_capital = base_capital + required_reinvestment
    average_capital = (base_capital + forecast_capital) / 2.0
    forecast_roic = forecast_nopat / average_capital * 100.0
    incremental_roic = (
        (forecast_nopat - base_nopat) / required_reinvestment * 100.0
        if required_reinvestment != 0
        else np.nan
    )
    reinvestment_rate = required_reinvestment / base_nopat
    nopat_growth = forecast_nopat / base_nopat - 1.0
    growth_identity = reinvestment_rate * incremental_roic / 100.0
    historical_margin = float(window["mpe_operating_margin_pct"].median())
    margin_delta = forecast_ebit / forecast_revenue * 100.0 - historical_margin
    economics_flag = (
        "REQUIRES_COST_SCOPE_AND_COMPANY_CAPTURE_VALIDATION"
        if incremental_roic > 100.0 or abs(margin_delta) > 5.0
        else "WITHIN_RESEARCH_DIAGNOSTIC_RANGE"
    )
    bridge = pd.DataFrame(
        [
            {
                "ticker": "CAT",
                "forecast_origin_fiscal_year": int(latest["fiscal_year"]),
                "target_fiscal_year": int(latest["fiscal_year"]) + 1,
                "anchor_architecture": "INDUSTRY_PQCI_TO_FINANCIAL_BRIDGE",
                "industry_revenue_growth_signal_pct": revenue_growth,
                "industry_cost_growth_signal_pct": cost_growth,
                "industry_inventory_growth_signal_pct": inventory_growth,
                "base_revenue_usd": base_revenue,
                "forecast_revenue_usd": forecast_revenue,
                "forecast_revenue_growth_pct": revenue_growth,
                "base_operating_cost_usd": base_cost,
                "forecast_operating_cost_usd": forecast_cost,
                "forecast_ebit_usd": forecast_ebit,
                "forecast_operating_margin_pct": forecast_ebit / forecast_revenue * 100.0,
                "historical_operating_margin_median_pct": historical_margin,
                "margin_vs_history_pct_points": margin_delta,
                "normalized_tax_rate_pct": tax_rate,
                "forecast_nopat_usd": forecast_nopat,
                "historical_sales_to_capital": historical_sales_to_capital,
                "inventory_adjusted_sales_to_capital": forecast_sales_to_capital,
                "required_reinvestment_usd": required_reinvestment,
                "reinvestment_rate_on_base_nopat": reinvestment_rate,
                "forecast_invested_capital_usd": forecast_capital,
                "forecast_roic_pct": forecast_roic,
                "incremental_roic_pct": incremental_roic,
                "forecast_nopat_growth_pct": nopat_growth * 100.0,
                "reinvestment_x_incremental_roic_pct": growth_identity * 100.0,
                "growth_identity_error_pct_points": (nopat_growth - growth_identity) * 100.0,
                "reinvestment_bridge_method": "INVENTORY_ADJUSTED_HISTORICAL_SALES_TO_CAPITAL",
                "reinvestment_bridge_validated": False,
                "economics_scope_flag": economics_flag,
                "valuation_use": "YEAR_ONE_RESEARCH_ONLY_FADE_TO_V1_1_FROZEN_TERMINAL",
                "snapshot_pit_status": "CURRENT_AS_OF_CUTOFF_BUT_NO_HISTORICAL_VINTAGES",
                "historical_backtest_allowed": False,
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    gate = pd.DataFrame(
        [
            {
                "sensor_count": len(signals),
                "leading_sensor_count": int(signals["economic_role"].eq("LEADING").sum()),
                "pqci_dimensions": "|".join(sorted(signals["pqci_dimension"].unique())),
                "all_sources_available_at_cutoff": True,
                "historical_release_date_coverage": False,
                "current_research_nowcast_allowed": True,
                "historical_pit_backtest_allowed": False,
                "terminal_replacement_allowed": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
    return {"industry_sensor_signals": signals, "industry_financial_bridge": bridge, "industry_data_gate": gate}
