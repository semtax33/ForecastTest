from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.v14.economics import _ridge


def _route_specs(segment: str, lags: list[int]) -> dict[str, list[str]]:
    specs = {f"PPI_RECOGNITION_LAG_{lag}": [f"cost_signal_lag_{lag}"] for lag in lags}
    if segment == "construction":
        specs["CONSTRUCTION_LOAD_MIX_LAG_1"] = [
            "cost_signal_lag_1",
            "lag_retail_world_yoy_pct",
            "lag_retail_regional_dispersion_pct",
        ]
    return specs


def _predict_fit(training: pd.DataFrame, test: pd.Series, features: list[str], penalty: float) -> float:
    fit = _ridge(training, features, "comparable_economic_cost_growth_pct", penalty, nonnegative=False)
    return float(fit["intercept"] + sum(fit[name] * float(test[name]) for name in features))


def _score_routes(
    training: pd.DataFrame,
    *,
    segment: str,
    lags: list[int],
    minimum_inner_validation_quarters: int,
    penalty: float,
) -> pd.DataFrame:
    specs = _route_specs(segment, lags)
    routes: dict[str, list[str]] = {"LAGGED_ACTUAL_COMPARABLE_COST": ["lag_comparable_cost_growth_pct"], **specs}
    rows: list[dict[str, object]] = []
    for route, features in routes.items():
        usable = training.dropna(subset=[*features, "comparable_economic_cost_growth_pct"]).sort_values("quarter")
        first_test = max(4, len(usable) - minimum_inner_validation_quarters)
        errors: list[float] = []
        for index in range(first_test, len(usable)):
            inner_train = usable.iloc[:index]
            test = usable.iloc[index]
            prediction = (
                float(test["lag_comparable_cost_growth_pct"])
                if route == "LAGGED_ACTUAL_COMPARABLE_COST"
                else _predict_fit(inner_train, test, features, penalty)
            )
            errors.append(abs(float(test["comparable_economic_cost_growth_pct"]) - prediction))
        rows.append(
            {
                "route": route,
                "recognition_lag_quarters": int(route.rsplit("_", 1)[-1]) if route.startswith("PPI_RECOGNITION") else np.nan,
                "inner_validation_observations": len(errors),
                "inner_comparable_cost_mae_pct": float(np.mean(errors)) if errors else np.nan,
                "eligible": len(errors) >= minimum_inner_validation_quarters,
            }
        )
    return pd.DataFrame(rows)


def _choose_route(scores: pd.DataFrame) -> str:
    baseline = scores.loc[scores["route"].eq("LAGGED_ACTUAL_COMPARABLE_COST") & scores["eligible"]]
    candidates = scores.loc[scores["route"].ne("LAGGED_ACTUAL_COMPARABLE_COST") & scores["eligible"]].dropna(
        subset=["inner_comparable_cost_mae_pct"]
    )
    if baseline.empty or candidates.empty:
        return "LAGGED_ACTUAL_COMPARABLE_COST"
    champion = candidates.sort_values(["inner_comparable_cost_mae_pct", "route"]).iloc[0]
    return (
        str(champion["route"])
        if champion["inner_comparable_cost_mae_pct"] < baseline.iloc[0]["inner_comparable_cost_mae_pct"]
        else "LAGGED_ACTUAL_COMPARABLE_COST"
    )


def _predict_route(
    route: str,
    training: pd.DataFrame,
    test: pd.Series,
    segment: str,
    lags: list[int],
    penalty: float,
) -> float:
    if route == "LAGGED_ACTUAL_COMPARABLE_COST":
        return float(test["lag_comparable_cost_growth_pct"])
    return _predict_fit(training.dropna(subset=_route_specs(segment, lags)[route]), test, _route_specs(segment, lags)[route], penalty)


def build_cost_timing_validation(
    *,
    cost_perimeter: pd.DataFrame,
    base_validation: pd.DataFrame,
    validation_start_period: str,
    expected_oos_quarters_per_segment: int,
    minimum_training_quarters: int,
    minimum_inner_validation_quarters: int,
    ridge_penalty: float,
    cost_recognition_lags: list[int],
) -> dict[str, pd.DataFrame]:
    panel = cost_perimeter.copy()
    panel["quarter"] = pd.PeriodIndex(panel["period"], freq="Q")
    panel["actual_available_at"] = pd.to_datetime(panel["actual_available_at"])
    panel["forecast_as_of"] = pd.to_datetime(panel["forecast_as_of"])
    panel = panel.sort_values(["segment", "quarter"]).reset_index(drop=True)
    for lag in cost_recognition_lags:
        panel[f"cost_signal_lag_{lag}"] = panel.groupby("segment")["dedicated_cost_yoy_pct"].shift(lag)
    panel["lag_comparable_cost_growth_pct"] = panel.groupby("segment")["comparable_economic_cost_growth_pct"].shift(1)

    base = base_validation.copy()
    base["forecast_as_of"] = pd.to_datetime(base["forecast_as_of"])
    base = base.rename(
        columns={
            "predicted_cost_growth_pct": "v1_5_predicted_reported_cost_growth_pct",
            "predicted_margin_pct": "v1_5_predicted_margin_pct",
            "gross_component_absolute_error_pct": "v1_5_gross_component_absolute_error_pct",
            "component_cancellation_ratio": "v1_5_component_cancellation_ratio",
        }
    )
    keep = [
        "period", "segment", "predicted_sales_usd", "predicted_revenue_growth_pct",
        "predicted_volume_contribution_pct", "predicted_price_contribution_pct",
        "margin_shrinkage_weight", "v1_5_predicted_reported_cost_growth_pct",
        "v1_5_predicted_margin_pct", "v1_5_gross_component_absolute_error_pct",
        "v1_5_component_cancellation_ratio",
    ]
    panel = panel.merge(base[keep], on=["period", "segment"], how="left", validate="one_to_one")

    validation_start = pd.Period(validation_start_period, freq="Q")
    score_rows: list[dict[str, object]] = []
    result_rows: list[dict[str, object]] = []
    for segment, group in panel.groupby("segment"):
        group = group.sort_values("quarter").reset_index(drop=True)
        tests = group.loc[group["quarter"].ge(validation_start)]
        if len(tests) != expected_oos_quarters_per_segment:
            raise ValueError(
                f"Fixed V1.6 OOS window changed for {segment}: {len(tests)} != {expected_oos_quarters_per_segment}"
            )
        for _, test in tests.iterrows():
            training = group.loc[
                group["quarter"].lt(test["quarter"])
                & group["actual_available_at"].le(test["forecast_as_of"])
                & group["historical_pit_input"].astype(bool)
            ].copy()
            if len(training) < minimum_training_quarters:
                raise ValueError(f"Insufficient fixed-window training rows for {segment} {test['period']}")
            scores = _score_routes(
                training,
                segment=segment,
                lags=cost_recognition_lags,
                minimum_inner_validation_quarters=minimum_inner_validation_quarters,
                penalty=ridge_penalty,
            )
            route = _choose_route(scores)
            for score in scores.itertuples(index=False):
                score_rows.append(
                    {
                        "segment": segment,
                        "forecast_period": test["period"],
                        "training_quarters": len(training),
                        "route": score.route,
                        "recognition_lag_quarters": score.recognition_lag_quarters,
                        "inner_validation_observations": score.inner_validation_observations,
                        "inner_comparable_cost_mae_pct": score.inner_comparable_cost_mae_pct,
                        "eligible": score.eligible,
                        "selected": score.route == route,
                    }
                )
            predicted_comparable_growth = _predict_route(
                route, training, test, segment, cost_recognition_lags, ridge_penalty
            )
            predicted_recast_scope_pct = 0.0
            predicted_cost = float(test["original_prior_reported_cost_usd"]) * (
                1.0 + predicted_recast_scope_pct / 100.0
            ) * (1.0 + predicted_comparable_growth / 100.0)
            predicted_reported_growth = predicted_cost / float(test["original_prior_reported_cost_usd"]) * 100.0 - 100.0
            raw_margin = (float(test["predicted_sales_usd"]) - predicted_cost) / float(test["predicted_sales_usd"]) * 100.0
            predicted_margin = float(test["prior_reported_margin_pct"]) + float(test["margin_shrinkage_weight"]) * (
                raw_margin - float(test["prior_reported_margin_pct"])
            )
            bridge_cost = float(test["predicted_sales_usd"]) * (1.0 - predicted_margin / 100.0)
            volume_error = abs(float(test["volume_contribution_pct"]) - float(test["predicted_volume_contribution_pct"]))
            price_error = abs(float(test["price_contribution_pct"]) - float(test["predicted_price_contribution_pct"]))
            economic_cost_error = abs(
                float(test["comparable_economic_cost_growth_pct"]) - predicted_comparable_growth
            )
            reported_cost_error = abs(float(test["reported_cost_growth_pct"]) - predicted_reported_growth)
            economic_gross_error = volume_error + price_error + economic_cost_error
            reported_gross_error = volume_error + price_error + reported_cost_error
            raw_margin_error = abs(float(test["actual_margin_pct"]) - raw_margin)
            cancellation_ratio = (
                float(np.clip(1.0 - raw_margin_error / reported_gross_error, 0.0, 1.0)) if reported_gross_error else 0.0
            )
            result_rows.append(
                {
                    "segment": segment,
                    "period": test["period"],
                    "forecast_as_of": test["forecast_as_of"].date().isoformat(),
                    "actual_available_at": test["actual_available_at"].date().isoformat(),
                    "training_quarters": len(training),
                    "selected_cost_route": route,
                    "selected_recognition_lag_quarters": (
                        int(route.rsplit("_", 1)[-1]) if route.startswith("PPI_RECOGNITION") else np.nan
                    ),
                    "actual_comparable_cost_growth_pct": test["comparable_economic_cost_growth_pct"],
                    "predicted_comparable_cost_growth_pct": predicted_comparable_growth,
                    "naive_lagged_comparable_cost_growth_pct": test["lag_comparable_cost_growth_pct"],
                    "actual_recast_scope_pct": test["recast_scope_pct_of_original"],
                    "predicted_recast_scope_pct": predicted_recast_scope_pct,
                    "material_recast_or_scope_change": bool(test["material_recast_or_scope_change"]),
                    "actual_reported_cost_growth_pct": test["reported_cost_growth_pct"],
                    "predicted_reported_cost_growth_pct": predicted_reported_growth,
                    "v1_5_predicted_reported_cost_growth_pct": test["v1_5_predicted_reported_cost_growth_pct"],
                    "actual_cost_usd": test["current_reported_cost_usd"],
                    "raw_predicted_cost_usd": predicted_cost,
                    "bridge_predicted_cost_usd": bridge_cost,
                    "actual_sales_usd": test["sales_usd"],
                    "predicted_sales_usd": test["predicted_sales_usd"],
                    "actual_revenue_growth_pct": test["actual_revenue_growth_pct"],
                    "predicted_revenue_growth_pct": test["predicted_revenue_growth_pct"],
                    "actual_volume_contribution_pct": test["volume_contribution_pct"],
                    "predicted_volume_contribution_pct": test["predicted_volume_contribution_pct"],
                    "actual_price_contribution_pct": test["price_contribution_pct"],
                    "predicted_price_contribution_pct": test["predicted_price_contribution_pct"],
                    "actual_margin_pct": test["actual_margin_pct"],
                    "prior_margin_pct": test["prior_reported_margin_pct"],
                    "raw_bridge_margin_pct": raw_margin,
                    "margin_shrinkage_weight": test["margin_shrinkage_weight"],
                    "predicted_margin_pct": predicted_margin,
                    "v1_5_predicted_margin_pct": test["v1_5_predicted_margin_pct"],
                    "economic_component_gross_error_pct": economic_gross_error,
                    "reported_component_gross_error_pct": reported_gross_error,
                    "raw_margin_absolute_error_pct_points": raw_margin_error,
                    "component_cancellation_ratio": cancellation_ratio,
                    "historical_pit_input": bool(test["historical_pit_input"]),
                    "actual_after_forecast": bool(test["actual_available_at"] > test["forecast_as_of"]),
                    "unexpected_recast_forecasted": False,
                }
            )
    validation = pd.DataFrame(result_rows).sort_values(["segment", "period"]).reset_index(drop=True)
    scores = pd.DataFrame(score_rows).sort_values(["segment", "forecast_period", "route"]).reset_index(drop=True)
    summary_rows: list[dict[str, object]] = []
    for segment, group in validation.groupby("segment"):
        economic_mae = float(
            (group["actual_comparable_cost_growth_pct"] - group["predicted_comparable_cost_growth_pct"]).abs().mean()
        )
        naive_mae = float(
            (group["actual_comparable_cost_growth_pct"] - group["naive_lagged_comparable_cost_growth_pct"]).abs().mean()
        )
        reported_mae = float(
            (group["actual_reported_cost_growth_pct"] - group["predicted_reported_cost_growth_pct"]).abs().mean()
        )
        v15_mae = float(
            (group["actual_reported_cost_growth_pct"] - group["v1_5_predicted_reported_cost_growth_pct"]).abs().mean()
        )
        routes = group["selected_cost_route"].value_counts()
        summary_rows.append(
            {
                "segment": segment,
                "validation_observations": len(group),
                "champion_cost_route": routes.index[0],
                "champion_route_selection_share_pct": float(routes.iloc[0] / len(group) * 100.0),
                "comparable_economic_cost_mae_pct": economic_mae,
                "naive_lagged_comparable_cost_mae_pct": naive_mae,
                "comparable_cost_mase": economic_mae / naive_mae if naive_mae else np.nan,
                "reported_cost_mae_pct": reported_mae,
                "v1_5_reported_cost_mae_pct": v15_mae,
                "reported_cost_mae_change_vs_v1_5_pct": (reported_mae / v15_mae - 1.0) * 100.0 if v15_mae else np.nan,
                "material_recast_rows": int(group["material_recast_or_scope_change"].sum()),
                "historical_pit_input_pct": float(group["historical_pit_input"].mean() * 100.0),
                "unexpected_recast_forecasted": False,
            }
        )
    return {
        "cost_timing_panel": panel.drop(columns="quarter"),
        "cost_route_inner_validation": scores,
        "cost_timing_walk_forward": validation,
        "cost_timing_validation_summary": pd.DataFrame(summary_rows),
    }
