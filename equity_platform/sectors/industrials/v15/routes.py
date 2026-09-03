from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.sectors.industrials.v14.economics import _ridge


SEGMENTS = ("construction", "resource", "power_energy")


def _candidate_features(segment: str) -> dict[str, list[str]]:
    routes = {
        "DEALER_RETAIL_WORLD": ["lag_retail_world_yoy_pct"],
        "DEALER_RETAIL_PLUS_LAG_VOLUME": [
            "lag_retail_world_yoy_pct",
            "lag_actual_volume_contribution_pct",
        ],
    }
    if segment == "construction":
        routes["REGIONAL_DEALER_TRANSMISSION"] = [
            "lag_retail_world_yoy_pct",
            "lag_retail_north_america_yoy_pct",
            "lag_retail_regional_dispersion_pct",
            "lag_actual_volume_contribution_pct",
        ]
    return routes


def _fit_predict(training: pd.DataFrame, row: pd.Series, features: list[str], target: str, penalty: float) -> float:
    fit = _ridge(training, features, target, penalty, nonnegative=False)
    return float(fit["intercept"] + sum(fit[name] * float(row[name]) for name in features))


def _inner_route_scores(
    training: pd.DataFrame,
    *,
    segment: str,
    penalty: float,
    minimum_inner_validation_quarters: int,
) -> pd.DataFrame:
    training = training.sort_values("quarter").reset_index(drop=True)
    candidates = _candidate_features(segment)
    rows: list[dict[str, object]] = []
    first_test = max(4, len(training) - minimum_inner_validation_quarters)
    for index in range(first_test, len(training)):
        inner_train = training.iloc[:index]
        test = training.iloc[index]
        actual = float(test["volume_contribution_pct"])
        rows.append(
            {
                "inner_period": test["period"],
                "route": "LAGGED_ACTUAL_VOLUME",
                "absolute_error_pct": abs(actual - float(test["lag_actual_volume_contribution_pct"])),
            }
        )
        for route, features in candidates.items():
            prediction = _fit_predict(inner_train, test, features, "volume_contribution_pct", penalty)
            rows.append(
                {
                    "inner_period": test["period"],
                    "route": route,
                    "absolute_error_pct": abs(actual - prediction),
                }
            )
    scores = pd.DataFrame(rows)
    if scores.empty:
        return pd.DataFrame(
            [{"route": "LAGGED_ACTUAL_VOLUME", "inner_validation_observations": 0, "inner_volume_mae_pct": np.nan}]
        )
    return (
        scores.groupby("route")
        .agg(
            inner_validation_observations=("absolute_error_pct", "size"),
            inner_volume_mae_pct=("absolute_error_pct", "mean"),
        )
        .reset_index()
    )


def _choose_route(scores: pd.DataFrame) -> str:
    baseline = scores.loc[scores["route"].eq("LAGGED_ACTUAL_VOLUME")]
    alternatives = scores.loc[scores["route"].ne("LAGGED_ACTUAL_VOLUME")].dropna(subset=["inner_volume_mae_pct"])
    if baseline.empty or alternatives.empty or pd.isna(baseline.iloc[0]["inner_volume_mae_pct"]):
        return "LAGGED_ACTUAL_VOLUME"
    champion = alternatives.sort_values(["inner_volume_mae_pct", "route"]).iloc[0]
    return str(champion["route"]) if champion["inner_volume_mae_pct"] < baseline.iloc[0]["inner_volume_mae_pct"] else "LAGGED_ACTUAL_VOLUME"


def _retail_as_of(
    vintages: pd.DataFrame,
    *,
    target: pd.Period,
    segment: str,
    cutoff: pd.Timestamp,
) -> dict[str, object] | None:
    available = vintages.loc[
        vintages["segment"].eq(segment) & pd.to_datetime(vintages["release_date"]).le(cutoff)
    ].copy()
    for lag in range(1, 5):
        reference = str(target - lag)
        candidate = available.loc[available["period"].eq(reference)]
        if candidate.empty:
            continue
        selected = candidate.loc[candidate.groupby("metric")["release_date"].idxmax()]
        values = dict(zip(selected["metric"], selected["vintage_value"]))
        if "world_retail_yoy_pct" not in values:
            continue
        return {
            "retail_reference_period": reference,
            "retail_lag_quarters": lag,
            "retail_release_date": selected["release_date"].max(),
            "lag_retail_world_yoy_pct": float(values["world_retail_yoy_pct"]),
            "lag_retail_north_america_yoy_pct": float(values.get("north_america_retail_yoy_pct", values["world_retail_yoy_pct"])),
            "lag_retail_regional_dispersion_pct": float(
                np.nanstd(
                    [
                        values.get("asia_pacific_retail_yoy_pct", np.nan),
                        values.get("eame_retail_yoy_pct", np.nan),
                        values.get("latin_america_retail_yoy_pct", np.nan),
                        values.get("north_america_retail_yoy_pct", np.nan),
                    ]
                )
            ) if segment == "construction" else 0.0,
        }
    return None


def _build_route_panel(
    *,
    ir_history: pd.DataFrame,
    pq_bridge: pd.DataFrame,
    pit_features: pd.DataFrame,
    forecast_origins: pd.DataFrame,
    retail_vintages: pd.DataFrame,
) -> pd.DataFrame:
    history = ir_history.loc[ir_history["segment"].isin(SEGMENTS)].copy()
    history["quarter"] = pd.PeriodIndex(history["period"], freq="Q")
    history["actual_available_at"] = pd.to_datetime(history["filing_date"])
    history["actual_margin_pct"] = history["segment_profit_usd"] / history["sales_usd"] * 100.0

    prior = history[
        ["quarter", "segment", "sales_usd", "operating_cost_usd", "actual_margin_pct"]
    ].copy()
    prior["quarter"] = prior["quarter"] + 4
    prior = prior.rename(
        columns={
            "sales_usd": "prior_reported_sales_usd",
            "operating_cost_usd": "prior_reported_cost_usd",
            "actual_margin_pct": "prior_reported_margin_pct",
        }
    )
    panel = history.merge(prior, on=["quarter", "segment"], how="inner", validate="one_to_one")
    panel = panel.merge(
        pq_bridge[
            [
                "period", "segment", "volume_contribution_pct", "price_contribution_pct",
                "currency_other_contribution_pct", "reported_revenue_growth_pct",
            ]
        ],
        on=["period", "segment"], how="inner", validate="one_to_one",
    )
    lag = pq_bridge[["period", "segment", "volume_contribution_pct"]].copy()
    lag["quarter"] = pd.PeriodIndex(lag["period"], freq="Q") + 1
    lag = lag.drop(columns="period").rename(columns={"volume_contribution_pct": "lag_actual_volume_contribution_pct"})
    panel = panel.merge(lag, on=["quarter", "segment"], how="inner", validate="one_to_one")
    panel = panel.merge(forecast_origins, on="period", how="inner", validate="many_to_one", suffixes=("", "_origin"))
    panel = panel.merge(
        pit_features.drop(columns=["actual_available_at"], errors="ignore"),
        on=["period", "segment", "forecast_as_of"], how="inner", validate="one_to_one",
    )

    retail_rows: list[dict[str, object]] = []
    for row in panel[["period", "segment", "forecast_as_of"]].itertuples(index=False):
        selected = _retail_as_of(
            retail_vintages,
            target=pd.Period(row.period, freq="Q"),
            segment=row.segment,
            cutoff=pd.Timestamp(row.forecast_as_of),
        )
        if selected is not None:
            retail_rows.append({"period": row.period, "segment": row.segment, **selected})
    retail = pd.DataFrame(retail_rows)
    panel = panel.merge(retail, on=["period", "segment"], how="inner", validate="one_to_one")
    panel["actual_revenue_growth_pct"] = panel["sales_usd"] / panel["prior_reported_sales_usd"] * 100.0 - 100.0
    panel["actual_cost_growth_pct"] = panel["operating_cost_usd"] / panel["prior_reported_cost_usd"] * 100.0 - 100.0
    panel["comparable_basis_gap_pct"] = panel["reported_revenue_growth_pct"] - panel["actual_revenue_growth_pct"]
    panel["forecast_as_of"] = pd.to_datetime(panel["forecast_as_of"])
    panel["actual_available_at_origin"] = pd.to_datetime(panel["actual_available_at_origin"])
    panel["retail_release_date"] = pd.to_datetime(panel["retail_release_date"])
    panel["historical_pit_input"] = (
        panel["historical_pit_eligible"].astype(bool)
        & panel["actual_available_at_origin"].gt(panel["forecast_as_of"])
        & panel["retail_release_date"].le(panel["forecast_as_of"])
    )
    return panel.sort_values(["quarter", "segment"]).reset_index(drop=True)


def _predict_route(route: str, training: pd.DataFrame, test: pd.Series, segment: str, penalty: float) -> float:
    if route == "LAGGED_ACTUAL_VOLUME":
        return float(test["lag_actual_volume_contribution_pct"])
    return _fit_predict(training, test, _candidate_features(segment)[route], "volume_contribution_pct", penalty)


def _margin_weight(
    training: pd.DataFrame,
    *,
    route: str,
    segment: str,
    price_fit: dict[str, float],
    cost_fit: dict[str, float],
    other: float,
    penalty: float,
) -> tuple[float, float]:
    structural: list[float] = []
    actual_delta: list[float] = []
    for _, row in training.iterrows():
        volume = _predict_route(route, training, row, segment, penalty)
        price = price_fit["intercept"] + price_fit["output_price_yoy_pct"] * float(row["output_price_yoy_pct"])
        cost_growth = cost_fit["intercept"] + cost_fit["dedicated_cost_yoy_pct"] * float(row["dedicated_cost_yoy_pct"])
        sales = float(row["prior_reported_sales_usd"]) * (1.0 + (volume + price + other) / 100.0)
        cost = float(row["prior_reported_cost_usd"]) * (1.0 + cost_growth / 100.0)
        raw_margin = (sales - cost) / sales * 100.0
        structural.append(raw_margin - float(row["prior_reported_margin_pct"]))
        actual_delta.append(float(row["actual_margin_pct"] - row["prior_reported_margin_pct"]))
    x = np.asarray(structural)
    y = np.asarray(actual_delta)
    scale = max(float(np.var(x)), 1.0)
    denominator = float(x @ x + penalty * scale)
    weight = float(np.clip((x @ y) / denominator, 0.0, 1.0)) if denominator else 0.0
    residual = y - weight * x
    return weight, float(pd.Series(residual).std(ddof=1))


def build_segment_route_validation(
    *,
    ir_history: pd.DataFrame,
    pq_bridge: pd.DataFrame,
    pit_features: pd.DataFrame,
    forecast_origins: pd.DataFrame,
    retail_vintages: pd.DataFrame,
    validation_start_period: str,
    minimum_training_quarters: int,
    minimum_inner_validation_quarters: int,
    ridge_penalty: float,
) -> dict[str, pd.DataFrame]:
    panel = _build_route_panel(
        ir_history=ir_history,
        pq_bridge=pq_bridge,
        pit_features=pit_features,
        forecast_origins=forecast_origins,
        retail_vintages=retail_vintages,
    )
    validation_start = pd.Period(validation_start_period, freq="Q")
    validation_rows: list[dict[str, object]] = []
    score_rows: list[dict[str, object]] = []
    for segment, group in panel.groupby("segment"):
        group = group.sort_values("quarter").reset_index(drop=True)
        for _, test in group.loc[group["quarter"].ge(validation_start)].iterrows():
            training = group.loc[
                group["quarter"].lt(test["quarter"])
                & group["actual_available_at"].le(test["forecast_as_of"])
                & group["historical_pit_input"]
            ].copy()
            if len(training) < minimum_training_quarters:
                continue
            scores = _inner_route_scores(
                training,
                segment=segment,
                penalty=ridge_penalty,
                minimum_inner_validation_quarters=minimum_inner_validation_quarters,
            )
            route = _choose_route(scores)
            for score in scores.itertuples(index=False):
                score_rows.append(
                    {
                        "segment": segment,
                        "forecast_period": test["period"],
                        "training_quarters": len(training),
                        "route": score.route,
                        "inner_validation_observations": score.inner_validation_observations,
                        "inner_volume_mae_pct": score.inner_volume_mae_pct,
                        "selected": score.route == route,
                    }
                )
            predicted_volume = _predict_route(route, training, test, segment, ridge_penalty)
            price_fit = _ridge(training, ["output_price_yoy_pct"], "price_contribution_pct", ridge_penalty, nonnegative=False)
            cost_fit = _ridge(training, ["dedicated_cost_yoy_pct"], "actual_cost_growth_pct", ridge_penalty, nonnegative=False)
            predicted_price = float(price_fit["intercept"] + price_fit["output_price_yoy_pct"] * test["output_price_yoy_pct"])
            predicted_cost_growth = float(
                cost_fit["intercept"] + cost_fit["dedicated_cost_yoy_pct"] * test["dedicated_cost_yoy_pct"]
            )
            predicted_other = float(training["currency_other_contribution_pct"].median())
            predicted_revenue_growth = predicted_volume + predicted_price + predicted_other
            predicted_sales = float(test["prior_reported_sales_usd"]) * (1.0 + predicted_revenue_growth / 100.0)
            predicted_cost = float(test["prior_reported_cost_usd"]) * (1.0 + predicted_cost_growth / 100.0)
            raw_margin = (predicted_sales - predicted_cost) / predicted_sales * 100.0
            weight, residual_std = _margin_weight(
                training,
                route=route,
                segment=segment,
                price_fit=price_fit,
                cost_fit=cost_fit,
                other=predicted_other,
                penalty=ridge_penalty,
            )
            predicted_margin = float(test["prior_reported_margin_pct"]) + weight * (
                raw_margin - float(test["prior_reported_margin_pct"])
            )
            bridge_cost = predicted_sales * (1.0 - predicted_margin / 100.0)
            gross_component_error = (
                abs(float(test["volume_contribution_pct"]) - predicted_volume)
                + abs(float(test["price_contribution_pct"]) - predicted_price)
                + abs(float(test["actual_cost_growth_pct"]) - predicted_cost_growth)
            )
            raw_margin_error = abs(float(test["actual_margin_pct"]) - raw_margin)
            cancellation_ratio = float(np.clip(1.0 - raw_margin_error / gross_component_error, 0.0, 1.0)) if gross_component_error else 0.0
            interval = 1.6448536269514722 * residual_std
            validation_rows.append(
                {
                    "segment": segment,
                    "period": test["period"],
                    "forecast_as_of": test["forecast_as_of"].date().isoformat(),
                    "actual_available_at": test["actual_available_at_origin"].date().isoformat(),
                    "training_quarters": len(training),
                    "selected_volume_route": route,
                    "retail_reference_period": test["retail_reference_period"],
                    "retail_lag_quarters": test["retail_lag_quarters"],
                    "actual_volume_contribution_pct": test["volume_contribution_pct"],
                    "predicted_volume_contribution_pct": predicted_volume,
                    "naive_lagged_volume_contribution_pct": test["lag_actual_volume_contribution_pct"],
                    "actual_price_contribution_pct": test["price_contribution_pct"],
                    "predicted_price_contribution_pct": predicted_price,
                    "actual_cost_growth_pct": test["actual_cost_growth_pct"],
                    "predicted_cost_growth_pct": predicted_cost_growth,
                    "predicted_other_contribution_pct": predicted_other,
                    "actual_revenue_growth_pct": test["actual_revenue_growth_pct"],
                    "reported_comparable_revenue_growth_pct": test["reported_revenue_growth_pct"],
                    "comparable_basis_gap_pct": test["comparable_basis_gap_pct"],
                    "predicted_revenue_growth_pct": predicted_revenue_growth,
                    "actual_sales_usd": test["sales_usd"],
                    "predicted_sales_usd": predicted_sales,
                    "naive_prior_year_sales_usd": test["prior_reported_sales_usd"],
                    "actual_cost_usd": test["operating_cost_usd"],
                    "raw_predicted_cost_usd": predicted_cost,
                    "bridge_predicted_cost_usd": bridge_cost,
                    "actual_margin_pct": test["actual_margin_pct"],
                    "prior_margin_pct": test["prior_reported_margin_pct"],
                    "raw_bridge_margin_pct": raw_margin,
                    "margin_shrinkage_weight": weight,
                    "predicted_margin_pct": predicted_margin,
                    "predicted_margin_lower_pct": predicted_margin - interval,
                    "predicted_margin_upper_pct": predicted_margin + interval,
                    "revenue_level_ape_pct": abs(predicted_sales / float(test["sales_usd"]) - 1.0) * 100.0,
                    "gross_component_absolute_error_pct": gross_component_error,
                    "raw_margin_absolute_error_pct_points": raw_margin_error,
                    "component_cancellation_ratio": cancellation_ratio,
                    "historical_pit_input": bool(test["historical_pit_input"]),
                    "actual_after_forecast": bool(test["actual_available_at_origin"] > test["forecast_as_of"]),
                    "performance_claim_allowed": True,
                }
            )
    validation = pd.DataFrame(validation_rows).sort_values(["segment", "period"]).reset_index(drop=True)
    scores = pd.DataFrame(score_rows).sort_values(["segment", "forecast_period", "route"]).reset_index(drop=True)
    return {
        "segment_route_panel": panel.drop(columns="quarter"),
        "segment_route_inner_validation": scores,
        "segment_route_walk_forward": validation,
    }
