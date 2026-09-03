from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.industry_data.pqci import load_bls_snapshot, load_census_m3_snapshot


SEGMENT_CATEGORY = {
    "construction": ("33C", "B"),
    "resource": ("33D", "B"),
    "power_energy": ("33S", "C"),
}


def _quarterly_yoy(
    frame: pd.DataFrame,
    *,
    value_method: str,
) -> pd.DataFrame:
    work = frame.copy()
    work["quarter"] = work["observation_date"].dt.to_period("Q")
    grouped = work.sort_values("observation_date").groupby("quarter")["value"]
    values = grouped.sum() if value_method == "sum" else grouped.last() if value_method == "last" else grouped.mean()
    result = values.rename("value").reset_index()
    result["yoy_pct"] = result["value"].pct_change(4) * 100.0
    return result


def build_quarterly_industry_signals(
    *,
    census_snapshot_path: Path,
    bls_snapshot_path: Path,
    cutoff: pd.Timestamp,
    cost_driver_industry_weight: float,
    cost_driver_inflation_weight: float,
) -> pd.DataFrame:
    if not np.isclose(cost_driver_industry_weight + cost_driver_inflation_weight, 1.0):
        raise ValueError("Cost-driver weights must sum to one")
    m3 = load_census_m3_snapshot(census_snapshot_path, cutoff)
    bls = load_bls_snapshot(bls_snapshot_path, cutoff)
    cost_parts: list[pd.DataFrame] = []
    for series_id, weight in [("WPUFD4", 0.4), ("CES0500000003", 0.6)]:
        part = _quarterly_yoy(bls.loc[bls["series_id"].eq(series_id)], value_method="mean")
        part["weighted"] = part["yoy_pct"] * weight
        cost_parts.append(part[["quarter", "weighted"]])
    cost = (
        pd.concat(cost_parts)
        .groupby("quarter")["weighted"]
        .agg(lambda values: values.sum(min_count=2))
        .rename("inflation_cost_signal_pct")
        .reset_index()
    )
    rows: list[pd.DataFrame] = []
    for segment, (category, grade) in SEGMENT_CATEGORY.items():
        components: list[pd.DataFrame] = []
        for code, weight, method in [("VS", 0.50, "sum"), ("NO", 0.25, "sum"), ("UO", 0.25, "last")]:
            subset = m3.loc[
                m3["category_code"].eq(category)
                & m3["data_type_code"].eq(code)
                & m3["seasonally_adj"].eq("yes")
            ]
            if subset.empty:
                raise ValueError(f"Census quarterly signal missing: {category}:{code}")
            part = _quarterly_yoy(subset, value_method=method)
            part["weighted"] = part["yoy_pct"] * weight
            components.append(part[["quarter", "weighted"]])
        signal = (
            pd.concat(components)
            .groupby("quarter")["weighted"]
            .agg(lambda values: values.sum(min_count=3))
            .rename("industry_revenue_signal_pct")
            .reset_index()
        )
        signal = signal.merge(cost, on="quarter", how="inner")
        signal["segment"] = segment
        signal["industry_category_code"] = category
        signal["source_grade"] = grade
        signal["cost_driver_signal_pct"] = (
            cost_driver_industry_weight * signal["industry_revenue_signal_pct"]
            + cost_driver_inflation_weight * signal["inflation_cost_signal_pct"]
        )
        rows.append(signal)
    output = pd.concat(rows, ignore_index=True).dropna().sort_values(["quarter", "segment"])
    output["period"] = output["quarter"].astype(str)
    output["vintage_status"] = "LATEST_REVISED_NOT_HISTORICAL_PIT"
    output["historical_pit_eligible"] = False
    return output.drop(columns="quarter").reset_index(drop=True)


def _slope(frame: pd.DataFrame, driver: str, target: str) -> float:
    x = frame[driver].to_numpy(float)
    y = frame[target].to_numpy(float)
    variance = float(np.sum((x - x.mean()) ** 2))
    return float(np.sum((x - x.mean()) * (y - y.mean())) / variance) if variance > 1e-12 else 0.0


def _fit(
    segment_train: pd.DataFrame,
    pooled_train: pd.DataFrame,
    *,
    driver: str,
    target: str,
    prior_strength: float,
) -> dict[str, float]:
    raw_beta = _slope(segment_train, driver, target)
    pooled_beta = _slope(pooled_train, driver, target)
    weight = len(segment_train) / (len(segment_train) + prior_strength)
    beta = weight * raw_beta + (1.0 - weight) * pooled_beta
    intercept = float(segment_train[target].mean() - beta * segment_train[driver].mean())
    residual = segment_train[target] - (intercept + beta * segment_train[driver])
    return {
        "raw_beta": raw_beta,
        "pooled_beta": pooled_beta,
        "shrinkage_weight": weight,
        "beta": beta,
        "intercept": intercept,
        "residual_std": float(residual.std(ddof=2)) if len(residual) > 2 else float("nan"),
    }


def _actual_panel(history: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    actual = history.loc[history["segment"].isin(SEGMENT_CATEGORY)].copy()
    actual = actual.sort_values(["segment", "fiscal_year", "fiscal_quarter"])
    actual["actual_revenue_growth_pct"] = actual["sales_usd"] / actual["comparable_prior_sales_usd"] * 100.0 - 100.0
    actual["actual_cost_growth_pct"] = actual["operating_cost_usd"] / actual["comparable_prior_operating_cost_usd"] * 100.0 - 100.0
    merged = actual.merge(signals, on=["period", "segment"], how="inner")
    return merged.dropna(subset=["actual_revenue_growth_pct", "actual_cost_growth_pct"]).reset_index(drop=True)


def _validation(
    panel: pd.DataFrame,
    *,
    minimum_training_quarters: int,
    prior_strength: float,
    interval_z: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for segment, group in panel.groupby("segment"):
        group = group.sort_values("period").reset_index(drop=True)
        for index in range(minimum_training_quarters, len(group)):
            test = group.iloc[index]
            earlier_periods = set(group.iloc[:index]["period"])
            pooled = panel.loc[panel["period"].isin(earlier_periods)]
            segment_train = group.iloc[:index]
            revenue_fit = _fit(segment_train, pooled, driver="industry_revenue_signal_pct", target="actual_revenue_growth_pct", prior_strength=prior_strength)
            cost_fit = _fit(segment_train, pooled, driver="cost_driver_signal_pct", target="actual_cost_growth_pct", prior_strength=prior_strength)
            revenue_prediction = revenue_fit["intercept"] + revenue_fit["beta"] * float(test["industry_revenue_signal_pct"])
            cost_prediction = cost_fit["intercept"] + cost_fit["beta"] * float(test["cost_driver_signal_pct"])
            prior_sales = float(test["comparable_prior_sales_usd"])
            prior_cost = float(test["comparable_prior_operating_cost_usd"])
            predicted_sales = prior_sales * (1.0 + revenue_prediction / 100.0)
            predicted_cost = prior_cost * (1.0 + cost_prediction / 100.0)
            predicted_margin = (predicted_sales - predicted_cost) / predicted_sales * 100.0
            prior_margin = (prior_sales - prior_cost) / prior_sales * 100.0
            rows.append(
                {
                    "segment": segment,
                    "period": test["period"],
                    "training_quarters": index,
                    "actual_revenue_growth_pct": test["actual_revenue_growth_pct"],
                    "predicted_revenue_growth_pct": revenue_prediction,
                    "unit_capture_revenue_growth_pct": test["industry_revenue_signal_pct"],
                    "revenue_prediction_lower_pct": revenue_prediction - interval_z * revenue_fit["residual_std"],
                    "revenue_prediction_upper_pct": revenue_prediction + interval_z * revenue_fit["residual_std"],
                    "actual_cost_growth_pct": test["actual_cost_growth_pct"],
                    "predicted_cost_growth_pct": cost_prediction,
                    "unit_capture_cost_growth_pct": test["cost_driver_signal_pct"],
                    "actual_sales_usd": test["sales_usd"],
                    "predicted_sales_usd": predicted_sales,
                    "revenue_level_ape_pct": abs(predicted_sales / float(test["sales_usd"]) - 1.0) * 100.0,
                    "actual_margin_pct": test["segment_margin_pct"],
                    "predicted_margin_pct": predicted_margin,
                    "prior_year_margin_pct": prior_margin,
                    "historical_pit_input": False,
                    "performance_claim_allowed": False,
                }
            )
    return pd.DataFrame(rows)


def _calibration_summary(panel: pd.DataFrame, validation: pd.DataFrame, *, prior_strength: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    specs = [
        ("REVENUE", "industry_revenue_signal_pct", "actual_revenue_growth_pct", "predicted_revenue_growth_pct", "unit_capture_revenue_growth_pct"),
        ("COST", "cost_driver_signal_pct", "actual_cost_growth_pct", "predicted_cost_growth_pct", "unit_capture_cost_growth_pct"),
    ]
    for segment, group in panel.groupby("segment"):
        pooled = panel
        segment_validation = validation.loc[validation["segment"].eq(segment)]
        for target_name, driver, target, prediction, unit_prediction in specs:
            fitted = _fit(group, pooled, driver=driver, target=target, prior_strength=prior_strength)
            actual = segment_validation[target]
            model_error = (actual - segment_validation[prediction]).abs()
            unit_error = (actual - segment_validation[unit_prediction]).abs()
            scale = float(group[target].diff().abs().dropna().mean())
            rows.append(
                {
                    "segment": segment,
                    "target": target_name,
                    "calibration_observations": len(group),
                    "validation_observations": len(segment_validation),
                    "raw_beta": fitted["raw_beta"],
                    "pooled_beta": fitted["pooled_beta"],
                    "shrinkage_weight": fitted["shrinkage_weight"],
                    "shrunk_capture_beta": fitted["beta"],
                    "intercept_pct": fitted["intercept"],
                    "residual_std_pct": fitted["residual_std"],
                    "temporal_validation_mae_pct": float(model_error.mean()),
                    "unit_capture_mae_pct": float(unit_error.mean()),
                    "mae_improvement_vs_unit_capture_pct": float((1.0 - model_error.mean() / unit_error.mean()) * 100.0) if unit_error.mean() else np.nan,
                    "mase": float(model_error.mean() / scale) if scale else np.nan,
                    "mean_revenue_level_ape_pct": float(segment_validation["revenue_level_ape_pct"].mean()) if target_name == "REVENUE" else np.nan,
                    "historical_pit_vintages_available": False,
                    "capture_validated": False,
                    "validation_status": "CALIBRATION_ONLY_LATEST_REVISED_INPUT_NOT_PIT",
                    "terminal_input_allowed": False,
                    "production_eligible": False,
                }
            )
    return pd.DataFrame(rows)


def _forecast_2026(
    history: pd.DataFrame,
    panel: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    prior_strength: float,
    interval_z: float,
) -> pd.DataFrame:
    latest_period = signals["period"].max()
    rows: list[dict[str, object]] = []
    for segment in SEGMENT_CATEGORY:
        group = panel.loc[panel["segment"].eq(segment)]
        signal = signals.loc[(signals["segment"].eq(segment)) & signals["period"].eq(latest_period)].iloc[0]
        revenue_fit = _fit(group, panel, driver="industry_revenue_signal_pct", target="actual_revenue_growth_pct", prior_strength=prior_strength)
        cost_fit = _fit(group, panel, driver="cost_driver_signal_pct", target="actual_cost_growth_pct", prior_strength=prior_strength)
        revenue_growth = revenue_fit["intercept"] + revenue_fit["beta"] * float(signal["industry_revenue_signal_pct"])
        cost_growth = cost_fit["intercept"] + cost_fit["beta"] * float(signal["cost_driver_signal_pct"])
        base = history.loc[(history["segment"].eq(segment)) & history["fiscal_year"].eq(2025)]
        actual_h1 = history.loc[(history["segment"].eq(segment)) & history["fiscal_year"].eq(2026) & history["fiscal_quarter"].le(2)]
        base_h2 = base.loc[base["fiscal_quarter"].gt(2)]
        forecast_sales = float(actual_h1["sales_usd"].sum() + base_h2["sales_usd"].sum() * (1.0 + revenue_growth / 100.0))
        forecast_cost = float(actual_h1["operating_cost_usd"].sum() + base_h2["operating_cost_usd"].sum() * (1.0 + cost_growth / 100.0))
        h2_low = base_h2["sales_usd"].sum() * (1.0 + (revenue_growth - interval_z * revenue_fit["residual_std"]) / 100.0)
        h2_high = base_h2["sales_usd"].sum() * (1.0 + (revenue_growth + interval_z * revenue_fit["residual_std"]) / 100.0)
        rows.append(
            {
                "segment": segment,
                "industry_category_code": signal["industry_category_code"],
                "source_grade": signal["source_grade"],
                "latest_industry_period": latest_period,
                "industry_revenue_signal_pct": signal["industry_revenue_signal_pct"],
                "inflation_cost_signal_pct": signal["inflation_cost_signal_pct"],
                "calibrated_revenue_capture_beta": revenue_fit["beta"],
                "calibrated_cost_capture_beta": cost_fit["beta"],
                "forecast_h2_revenue_growth_pct": revenue_growth,
                "forecast_h2_cost_growth_pct": cost_growth,
                "base_fy2025_sales_usd": float(base["sales_usd"].sum()),
                "forecast_fy2026_sales_usd": forecast_sales,
                "forecast_fy2026_sales_lower_usd": float(actual_h1["sales_usd"].sum() + h2_low),
                "forecast_fy2026_sales_upper_usd": float(actual_h1["sales_usd"].sum() + h2_high),
                "base_fy2025_operating_cost_usd": float(base["operating_cost_usd"].sum()),
                "forecast_fy2026_operating_cost_usd": forecast_cost,
                "forecast_fy2026_segment_profit_usd": forecast_sales - forecast_cost,
                "forecast_fy2026_margin_pct": (forecast_sales - forecast_cost) / forecast_sales * 100.0,
                "forecast_semantics": "H1_ACTUAL_PLUS_H2_CAPTURE_CALIBRATED_RUN_RATE",
                "historical_pit_input": False,
                "performance_claim_allowed": False,
            }
        )
    core = pd.DataFrame(rows)
    history_2025 = history.loc[history["fiscal_year"].eq(2025)]
    history_2026 = history.loc[history["fiscal_year"].eq(2026) & history["fiscal_quarter"].le(2)]
    def residual(frame: pd.DataFrame, metric: str) -> float:
        return float(frame.loc[frame["segment"].eq("mpe"), metric].sum() - frame.loc[frame["segment"].isin(SEGMENT_CATEGORY), metric].sum())
    base_residual_sales = residual(history_2025, "sales_usd")
    base_residual_cost = residual(history_2025, "operating_cost_usd")
    actual_h1_residual_sales = residual(history_2026, "sales_usd")
    actual_h1_residual_cost = residual(history_2026, "operating_cost_usd")
    prior_h2 = history_2025.loc[history_2025["fiscal_quarter"].gt(2)]
    residual_h2_sales = residual(prior_h2, "sales_usd")
    residual_h2_cost = residual(prior_h2, "operating_cost_usd")
    residual_sales = actual_h1_residual_sales + residual_h2_sales
    residual_cost = actual_h1_residual_cost + residual_h2_cost
    residual_row = pd.DataFrame(
        [
            {
                "segment": "mpe_other_corporate",
                "industry_category_code": "RESIDUAL",
                "source_grade": "D",
                "latest_industry_period": latest_period,
                "industry_revenue_signal_pct": 0.0,
                "inflation_cost_signal_pct": 0.0,
                "calibrated_revenue_capture_beta": 0.0,
                "calibrated_cost_capture_beta": 0.0,
                "forecast_h2_revenue_growth_pct": 0.0,
                "forecast_h2_cost_growth_pct": 0.0,
                "base_fy2025_sales_usd": base_residual_sales,
                "forecast_fy2026_sales_usd": residual_sales,
                "forecast_fy2026_sales_lower_usd": residual_sales,
                "forecast_fy2026_sales_upper_usd": residual_sales,
                "base_fy2025_operating_cost_usd": base_residual_cost,
                "forecast_fy2026_operating_cost_usd": residual_cost,
                "forecast_fy2026_segment_profit_usd": residual_sales - residual_cost,
                "forecast_fy2026_margin_pct": (residual_sales - residual_cost) / residual_sales * 100.0 if residual_sales else np.nan,
                "forecast_semantics": "H1_ACTUAL_PLUS_PRIOR_YEAR_H2_RESIDUAL",
                "historical_pit_input": False,
                "performance_claim_allowed": False,
            }
        ]
    )
    return pd.concat([core, residual_row], ignore_index=True)


def build_capture_research(
    *,
    ir_history: pd.DataFrame,
    census_snapshot_path: Path,
    bls_snapshot_path: Path,
    cutoff: pd.Timestamp,
    minimum_training_quarters: int,
    minimum_validation_quarters: int,
    prior_strength: float,
    cost_driver_industry_weight: float,
    cost_driver_inflation_weight: float,
    interval_z: float,
) -> dict[str, pd.DataFrame]:
    signals = build_quarterly_industry_signals(
        census_snapshot_path=census_snapshot_path,
        bls_snapshot_path=bls_snapshot_path,
        cutoff=cutoff,
        cost_driver_industry_weight=cost_driver_industry_weight,
        cost_driver_inflation_weight=cost_driver_inflation_weight,
    )
    panel = _actual_panel(ir_history, signals)
    validation = _validation(panel, minimum_training_quarters=minimum_training_quarters, prior_strength=prior_strength, interval_z=interval_z)
    calibration = _calibration_summary(panel, validation, prior_strength=prior_strength)
    forecast = _forecast_2026(ir_history, panel, signals, prior_strength=prior_strength, interval_z=interval_z)
    margin_rows: list[dict[str, object]] = []
    for segment, group in validation.groupby("segment"):
        model_mae = float((group["actual_margin_pct"] - group["predicted_margin_pct"]).abs().mean())
        baseline_mae = float((group["actual_margin_pct"] - group["prior_year_margin_pct"]).abs().mean())
        margin_rows.append(
            {
                "segment": segment,
                "validation_observations": len(group),
                "margin_mae_pct_points": model_mae,
                "prior_year_margin_mae_pct_points": baseline_mae,
                "margin_mase_vs_prior_year": model_mae / baseline_mae if baseline_mae else np.nan,
                "minimum_observations_met": len(group) >= minimum_validation_quarters,
                "historical_pit_vintages_available": False,
                "margin_model_validated": False,
                "status": "FAIL_CLOSED_NON_PIT_REVISED_MACRO_INPUT",
                "terminal_input_allowed": False,
            }
        )
    return {
        "quarterly_industry_signals": signals,
        "capture_calibration_panel": panel,
        "capture_temporal_validation": validation,
        "capture_calibration_summary": calibration,
        "segment_fy2026_forecast": forecast,
        "margin_validation_summary": pd.DataFrame(margin_rows),
    }
