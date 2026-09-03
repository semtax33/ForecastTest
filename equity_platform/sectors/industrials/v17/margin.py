from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.v14.economics import _ridge


STRUCTURAL_FEATURES = [
    "structural_price_pct",
    "structural_volume_pct",
    "structural_cost_signal_pct",
    "structural_other_pct",
]
REDUCED_FEATURES = [
    "prior_reported_margin_pct",
    "latest_available_margin_pct",
    "reduced_revenue_signal_pct",
    "dedicated_cost_yoy_pct",
]


def _reduced_features(segment: str) -> list[str]:
    if segment == "power_energy":
        return [*REDUCED_FEATURES, "latest_power_generation_mix_pct", "latest_oil_gas_mix_pct"]
    return REDUCED_FEATURES


def _latest_available_margin(panel: pd.DataFrame, row: pd.Series) -> float:
    available = panel.loc[
        panel["segment"].eq(row["segment"])
        & (pd.PeriodIndex(panel["period"], freq="Q") < pd.Period(row["period"], freq="Q"))
        & pd.to_datetime(panel["actual_available_at"]).le(pd.Timestamp(row["forecast_as_of"]))
    ].sort_values("period")
    return float(available.iloc[-1]["actual_margin_pct"]) if not available.empty else float(row["prior_reported_margin_pct"])


def _fit_structural(training: pd.DataFrame, penalty: float) -> dict[str, float]:
    fit = _ridge(training, STRUCTURAL_FEATURES, "profit_change_pct_prior_sales", penalty, nonnegative=False)
    bounds = {
        "structural_price_pct": (0.0, 1.5),
        "structural_volume_pct": (0.0, 1.0),
        "structural_cost_signal_pct": (-2.0, 0.0),
        "structural_other_pct": (0.0, 1.0),
    }
    for feature, (lower, upper) in bounds.items():
        fit[feature] = float(np.clip(fit[feature], lower, upper))
    fit["intercept"] = float(
        training["profit_change_pct_prior_sales"].mean()
        - sum(fit[feature] * training[feature].mean() for feature in STRUCTURAL_FEATURES)
    )
    predicted = fit["intercept"] + sum(fit[feature] * training[feature] for feature in STRUCTURAL_FEATURES)
    fit["residual_std"] = float((training["profit_change_pct_prior_sales"] - predicted).std(ddof=1))
    return fit


def _driver_calibration(
    *,
    training: pd.DataFrame,
    driver_evidence: pd.DataFrame,
    cutoff: pd.Timestamp,
) -> dict[str, float | int]:
    evidence = driver_evidence.loc[
        driver_evidence["segment"].eq(training.iloc[0]["segment"])
        & driver_evidence["numeric_disclosure"]
        & pd.to_datetime(driver_evidence["filing_date"]).le(cutoff)
    ].copy()
    evidence = evidence.merge(
        training[["period", "price_change_usd", "volume_change_usd"]],
        on="period",
        how="inner",
    )
    price = evidence.loc[evidence["driver"].eq("PRICE_REALIZATION") & evidence["price_change_usd"].abs().gt(1.0)]
    volume = evidence.loc[evidence["driver"].eq("SALES_VOLUME_MIX") & evidence["volume_change_usd"].abs().gt(1.0)]
    return {
        "reported_price_calibration_observations": len(price),
        "reported_price_pass_through_median": float((price["reported_driver_change_usd"] / price["price_change_usd"]).median()) if len(price) else np.nan,
        "reported_volume_calibration_observations": len(volume),
        "reported_volume_pass_through_median": float((volume["reported_driver_change_usd"] / volume["volume_change_usd"]).median()) if len(volume) else np.nan,
    }


def _margin_perimeter(panel: pd.DataFrame, cost_perimeter: pd.DataFrame, threshold_pct: float) -> pd.DataFrame:
    frame = panel.copy()
    frame["original_prior_reported_profit_usd"] = frame["prior_reported_sales_usd"] - frame["prior_reported_cost_usd"]
    frame["original_prior_reported_margin_pct"] = frame["original_prior_reported_profit_usd"] / frame["prior_reported_sales_usd"] * 100.0
    frame["comparable_prior_margin_pct"] = frame["comparable_prior_segment_profit_usd"] / frame["comparable_prior_sales_usd"] * 100.0
    frame["current_reported_margin_pct"] = frame["segment_profit_usd"] / frame["sales_usd"] * 100.0
    frame["scope_recast_margin_effect_pct_points"] = frame["comparable_prior_margin_pct"] - frame["original_prior_reported_margin_pct"]
    frame["comparable_economic_margin_change_pct_points"] = frame["current_reported_margin_pct"] - frame["comparable_prior_margin_pct"]
    frame["total_reported_margin_change_pct_points"] = frame["current_reported_margin_pct"] - frame["original_prior_reported_margin_pct"]
    frame["margin_perimeter_identity_error_pct_points"] = (
        frame["total_reported_margin_change_pct_points"]
        - frame["scope_recast_margin_effect_pct_points"]
        - frame["comparable_economic_margin_change_pct_points"]
    )
    frame = frame.merge(
        cost_perimeter[["period", "segment", "recast_scope_pct_of_original", "material_recast_or_scope_change"]],
        on=["period", "segment"],
        how="left",
        validate="one_to_one",
    )
    sales_recast_pct = (frame["comparable_prior_sales_usd"] / frame["prior_reported_sales_usd"] - 1.0) * 100.0
    frame["sales_recast_scope_pct"] = sales_recast_pct
    frame["unforecastable_scope_change"] = (
        frame["material_recast_or_scope_change"].fillna(False)
        | sales_recast_pct.abs().gt(threshold_pct)
        | frame["scope_recast_margin_effect_pct_points"].abs().gt(threshold_pct)
    )
    frame["scope_change_treatment"] = np.where(
        frame["unforecastable_scope_change"],
        "UNFORECASTABLE_SCOPE_CHANGE",
        "COMPARABLE_AND_REPORTED_PERIMETER_ALIGNED",
    )
    frame["margin_perimeter_identity_pass"] = frame["margin_perimeter_identity_error_pct_points"].abs().le(1e-10)
    return frame


def build_margin_research(
    *,
    route_panel: pd.DataFrame,
    revenue_validation: pd.DataFrame,
    cost_perimeter: pd.DataFrame,
    driver_evidence: pd.DataFrame,
    application_mix: pd.DataFrame,
    validation_start_period: str,
    predeclared_routes: dict[str, str],
    ridge_penalty: float,
    material_scope_threshold_pct: float,
) -> dict[str, pd.DataFrame]:
    panel = route_panel.copy()
    panel["forecast_as_of"] = pd.to_datetime(panel["forecast_as_of"])
    panel["actual_available_at"] = pd.to_datetime(panel["actual_available_at"])
    panel["actual_margin_pct"] = panel["segment_profit_usd"] / panel["sales_usd"] * 100.0
    panel["original_prior_reported_profit_usd"] = panel["prior_reported_sales_usd"] - panel["prior_reported_cost_usd"]
    panel["profit_change_pct_prior_sales"] = (panel["segment_profit_usd"] - panel["original_prior_reported_profit_usd"]) / panel["prior_reported_sales_usd"] * 100.0
    panel["price_change_usd"] = panel["price_contribution_pct"] / 100.0 * panel["prior_reported_sales_usd"]
    panel["volume_change_usd"] = panel["volume_contribution_pct"] / 100.0 * panel["prior_reported_sales_usd"]
    panel["structural_price_pct"] = panel["price_contribution_pct"]
    panel["structural_volume_pct"] = panel["volume_contribution_pct"]
    panel["structural_cost_signal_pct"] = panel["dedicated_cost_yoy_pct"]
    panel["structural_other_pct"] = panel["currency_other_contribution_pct"]
    panel["reduced_revenue_signal_pct"] = panel["actual_revenue_growth_pct"]
    panel["latest_available_margin_pct"] = panel.apply(lambda row: _latest_available_margin(panel, row), axis=1)
    application_mix = application_mix.copy()
    application_mix["filing_date"] = pd.to_datetime(application_mix["filing_date"])
    for index, row in panel.iterrows():
        available_mix = application_mix.loc[
            (pd.PeriodIndex(application_mix["period"], freq="Q") < pd.Period(row["period"], freq="Q"))
            & application_mix["filing_date"].le(row["forecast_as_of"])
        ].sort_values("period")
        latest = available_mix.iloc[-1] if not available_mix.empty else None
        panel.loc[index, "latest_power_generation_mix_pct"] = float(latest["power_generation_mix_pct"]) if latest is not None and pd.notna(latest["power_generation_mix_pct"]) else 0.0
        panel.loc[index, "latest_oil_gas_mix_pct"] = float(latest["oil_gas_mix_pct"]) if latest is not None and pd.notna(latest["oil_gas_mix_pct"]) else 0.0
        panel.loc[index, "application_mix_reference_period"] = latest["period"] if latest is not None else ""
        panel.loc[index, "application_mix_release_date"] = latest["filing_date"] if latest is not None else pd.NaT

    validation = revenue_validation.merge(
        panel,
        on=["period", "segment"],
        how="left",
        validate="one_to_one",
        suffixes=("_forecast", ""),
    )
    validation["forecast_as_of_forecast"] = pd.to_datetime(validation["forecast_as_of_forecast"])
    rows: list[dict[str, object]] = []
    coefficient_rows: list[dict[str, object]] = []
    for test in validation.itertuples(index=False):
        test_period = pd.Period(test.period, freq="Q")
        cutoff = pd.Timestamp(test.forecast_as_of_forecast)
        training = panel.loc[
            (pd.PeriodIndex(panel["period"], freq="Q") < test_period)
            & panel["segment"].eq(test.segment)
            & panel["actual_available_at"].le(cutoff)
            & panel["historical_pit_input"].astype(bool)
        ].copy()
        structural = _fit_structural(training, ridge_penalty)
        calibration = _driver_calibration(training=training, driver_evidence=driver_evidence, cutoff=cutoff)
        test_values = {
            "structural_price_pct": float(test.predicted_price_contribution_pct),
            "structural_volume_pct": float(test.predicted_volume_contribution_pct),
            "structural_cost_signal_pct": float(test.dedicated_cost_yoy_pct),
            "structural_other_pct": float(test.predicted_other_contribution_pct),
        }
        structural_delta_pct = structural["intercept"] + sum(structural[name] * value for name, value in test_values.items())
        prior_profit = float(test.original_prior_reported_profit_usd)
        structural_profit = prior_profit + structural_delta_pct / 100.0 * float(test.prior_reported_sales_usd)
        structural_margin = structural_profit / float(test.predicted_sales_usd) * 100.0

        reduced_training = training.copy()
        reduced_features = _reduced_features(str(test.segment))
        reduced = _ridge(reduced_training, reduced_features, "actual_margin_pct", ridge_penalty, nonnegative=False)
        reduced_values = {
            "prior_reported_margin_pct": float(test.prior_reported_margin_pct),
            "latest_available_margin_pct": float(test.latest_available_margin_pct),
            "reduced_revenue_signal_pct": float(test.predicted_revenue_growth_pct),
            "dedicated_cost_yoy_pct": float(test.dedicated_cost_yoy_pct),
            "latest_power_generation_mix_pct": float(test.latest_power_generation_mix_pct),
            "latest_oil_gas_mix_pct": float(test.latest_oil_gas_mix_pct),
        }
        reduced_margin = reduced["intercept"] + sum(reduced[name] * reduced_values[name] for name in reduced_features)
        selected_route = predeclared_routes[str(test.segment)]
        selected_margin = structural_margin if selected_route == "STRUCTURAL_PROFIT_DRIVER" else reduced_margin
        actual_margin = float(test.actual_margin_pct)
        interval_std = structural["residual_std"] if selected_route == "STRUCTURAL_PROFIT_DRIVER" else reduced["residual_std"]
        rows.append(
            {
                "period": test.period,
                "segment": test.segment,
                "forecast_as_of": cutoff.date().isoformat(),
                "actual_available_at": pd.Timestamp(test.actual_available_at_forecast).date().isoformat(),
                "training_quarters": len(training),
                "predeclared_route": selected_route,
                "route_selected_without_oos_peeking": True,
                "actual_reported_margin_pct": actual_margin,
                "naive_prior_year_margin_pct": float(test.prior_reported_margin_pct),
                "structural_predicted_margin_pct": structural_margin,
                "reduced_form_predicted_margin_pct": reduced_margin,
                "selected_predicted_margin_pct": selected_margin,
                "selected_interval_lower_pct": selected_margin - 1.6448536269514722 * interval_std,
                "selected_interval_upper_pct": selected_margin + 1.6448536269514722 * interval_std,
                "structural_predicted_profit_usd": structural_profit,
                "predicted_revenue_usd": float(test.predicted_sales_usd),
                "actual_profit_usd": float(test.segment_profit_usd),
                "historical_pit_input": bool(test.historical_pit_input_forecast),
                "actual_after_forecast": pd.Timestamp(test.actual_available_at_forecast) > cutoff,
                "application_mix_reference_period": test.application_mix_reference_period,
                "application_mix_available_at_origin": bool(
                    str(test.segment) != "power_energy"
                    or pd.Timestamp(test.application_mix_release_date) <= cutoff
                ),
            }
        )
        coefficient_rows.append(
            {
                "period": test.period,
                "segment": test.segment,
                "training_quarters": len(training),
                "intercept_pct_prior_sales": structural["intercept"],
                "price_profit_pass_through": structural["structural_price_pct"],
                "volume_mix_profit_pass_through": structural["structural_volume_pct"],
                "manufacturing_cost_signal_beta": structural["structural_cost_signal_pct"],
                "currency_other_profit_pass_through": structural["structural_other_pct"],
                **calibration,
                "company_reported_driver_calibration_is_cross_check_only": True,
            }
        )
    walk = pd.DataFrame(rows).sort_values(["segment", "period"]).reset_index(drop=True)
    perimeter = _margin_perimeter(route_panel, cost_perimeter, material_scope_threshold_pct)
    scope = perimeter[["period", "segment", "unforecastable_scope_change", "scope_change_treatment"]]
    walk = walk.merge(scope, on=["period", "segment"], how="left", validate="one_to_one")
    summaries: list[dict[str, object]] = []
    for segment, group in walk.groupby("segment"):
        actual = group["actual_reported_margin_pct"]
        naive_error = (actual - group["naive_prior_year_margin_pct"]).abs()
        structural_error = (actual - group["structural_predicted_margin_pct"]).abs()
        reduced_error = (actual - group["reduced_form_predicted_margin_pct"]).abs()
        selected_error = (actual - group["selected_predicted_margin_pct"]).abs()
        denominator = float(naive_error.mean())
        summaries.append(
            {
                "segment": segment,
                "validation_observations": len(group),
                "predeclared_route": group.iloc[0]["predeclared_route"],
                "structural_margin_mae_pct_points": float(structural_error.mean()),
                "structural_margin_mase": float(structural_error.mean() / denominator),
                "reduced_form_margin_mae_pct_points": float(reduced_error.mean()),
                "reduced_form_margin_mase": float(reduced_error.mean() / denominator),
                "selected_margin_mae_pct_points": float(selected_error.mean()),
                "selected_margin_mase": float(selected_error.mean() / denominator),
                "naive_margin_mae_pct_points": denominator,
                "unforecastable_scope_change_rows": int(group["unforecastable_scope_change"].sum()),
                "interval_coverage_pct": float(((actual >= group["selected_interval_lower_pct"]) & (actual <= group["selected_interval_upper_pct"])).mean() * 100.0),
                "historical_pit_input_pct": float(group["historical_pit_input"].mean() * 100.0),
                "margin_champion_eligible": bool(selected_error.mean() < denominator and len(group) == 6),
            }
        )
    summary = pd.DataFrame(summaries)
    return {
        "reported_comparable_margin_perimeter": perimeter,
        "margin_structural_calibration": pd.DataFrame(coefficient_rows),
        "margin_route_walk_forward": walk,
        "margin_route_summary": summary,
    }
