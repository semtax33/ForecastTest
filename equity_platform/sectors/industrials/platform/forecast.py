from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .domain import ForecastAuthority, classify_forecast_authority


@dataclass(frozen=True)
class RidgeFit:
    intercept: float
    coefficients: tuple[float, ...]
    residual_std: float


def build_company_forecast_origins(quarterly: pd.DataFrame) -> pd.DataFrame:
    """Build one-quarter-ahead origins using only the previous public filing."""
    rows: list[dict[str, object]] = []
    for (subindustry, ticker), group in quarterly.groupby(
        ["subindustry_code", "ticker"]
    ):
        history = group.sort_values(["report_date", "filing_date"]).drop_duplicates(
            "period", keep="first"
        )
        history = history.reset_index(drop=True)
        for index in range(1, len(history)):
            origin = history.iloc[index - 1]
            target = history.iloc[index]
            origin_period = pd.Period(origin["period"], freq="Q")
            target_period = pd.Period(target["period"], freq="Q")
            if target_period.ordinal - origin_period.ordinal != 1:
                continue
            rows.append(
                {
                    "subindustry_code": subindustry,
                    "ticker": ticker,
                    "period": str(target_period),
                    "origin_period": str(origin_period),
                    "forecast_as_of": origin["filing_date"],
                    "actual_available_at": target["filing_date"],
                    "horizon_quarters": 1,
                    "actual_after_forecast": bool(
                        pd.Timestamp(target["filing_date"])
                        > pd.Timestamp(origin["filing_date"])
                    ),
                }
            )
    return pd.DataFrame(rows)


def _quarter_values(
    selected: pd.DataFrame, series_id: str, quarter: pd.Period
) -> pd.Series:
    months = {
        str(period)
        for period in pd.period_range(quarter.start_time, quarter.end_time, freq="M")
    }
    return selected.loc[
        selected["series_id"].eq(series_id)
        & selected["observation_period"].isin(months),
        "vintage_value",
    ]


def build_company_pit_industry_features(
    *,
    vintages: pd.DataFrame,
    sensor_map: pd.DataFrame,
    origins: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Select the latest BLS vintage known at each company forecast origin.

    Features are company/subindustry specific. Missing cost proxies do not erase
    a valid output-price observation; they explicitly disable the structural
    price-cost claim instead.
    """
    source = vintages.copy()
    source["release_date"] = pd.to_datetime(source["release_date"])
    feature_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []
    for origin in origins.itertuples(index=False):
        target = pd.Period(origin.period, freq="Q")
        as_of = pd.Timestamp(origin.forecast_as_of)
        sensors = sensor_map.loc[
            sensor_map["segment"].eq(origin.subindustry_code)
        ].copy()
        available = source.loc[
            source["release_date"].le(as_of)
            & source["series_id"].isin(sensors["series_id"])
        ].copy()
        if available.empty or sensors.empty:
            continue
        selected = available.loc[
            available.groupby(["series_id", "observation_period"])[
                "release_date"
            ].idxmax()
        ]
        required_output = sensors.loc[sensors["role"].eq("output_price")]
        reference: pd.Period | None = None
        for lag in range(1, 5):
            candidate = target - lag
            if all(
                len(_quarter_values(selected, series_id, candidate)) == 3
                and len(_quarter_values(selected, series_id, candidate - 4)) == 3
                for series_id in required_output["series_id"].unique()
            ):
                reference = candidate
                break
        if reference is None:
            continue
        yoy: dict[str, float] = {}
        for series_id in sensors["series_id"].unique():
            current = _quarter_values(selected, series_id, reference)
            prior = _quarter_values(selected, series_id, reference - 4)
            if len(current) != 3 or len(prior) != 3 or prior.mean() == 0:
                continue
            yoy[series_id] = float(current.mean() / prior.mean() * 100.0 - 100.0)
            selected_months = {
                str(period)
                for period in pd.period_range(
                    (reference - 4).start_time, reference.end_time, freq="M"
                )
            }
            chosen = selected.loc[
                selected["series_id"].eq(series_id)
                & selected["observation_period"].isin(selected_months)
            ]
            selection_rows.append(
                {
                    "ticker": origin.ticker,
                    "subindustry_code": origin.subindustry_code,
                    "period": origin.period,
                    "forecast_as_of": as_of.date().isoformat(),
                    "feature_reference_quarter": str(reference),
                    "series_id": series_id,
                    "selected_vintage_rows": len(chosen),
                    "latest_selected_release_date": (
                        chosen["release_date"].max().date().isoformat()
                    ),
                    "cutoff_respected": bool(
                        chosen["release_date"].le(as_of).all()
                    ),
                }
            )
        output_rows = required_output.loc[
            required_output["series_id"].isin(yoy)
        ]
        if output_rows.empty:
            continue
        output_price = float(
            sum(row.weight * yoy[row.series_id] for row in output_rows.itertuples())
            / output_rows["weight"].sum()
        )
        cost_rows = sensors.loc[
            sensors["role"].eq("input_cost") & sensors["series_id"].isin(yoy)
        ]
        cost = (
            float(
                sum(row.weight * yoy[row.series_id] for row in cost_rows.itertuples())
                / cost_rows["weight"].sum()
            )
            if not cost_rows.empty
            else np.nan
        )
        expected_cost_weight = float(
            sensors.loc[sensors["role"].eq("input_cost"), "weight"].sum()
        )
        observed_cost_weight = float(cost_rows["weight"].sum())
        structural_cost = bool(
            not cost_rows.empty
            and observed_cost_weight >= expected_cost_weight - 1e-9
            and cost_rows["structural_cost_claim_allowed"].all()
        )
        feature_rows.append(
            {
                "ticker": origin.ticker,
                "subindustry_code": origin.subindustry_code,
                "period": origin.period,
                "forecast_as_of": as_of.date().isoformat(),
                "feature_reference_quarter": str(reference),
                "feature_lag_quarters": target.ordinal - reference.ordinal,
                "output_price_yoy_pct": output_price,
                "input_cost_yoy_pct": cost,
                "price_cost_spread_pct": output_price - cost,
                "ppi_series_coverage_pct": (
                    sensors["series_id"].drop_duplicates().isin(yoy).mean()
                    * 100.0
                ),
                "structural_price_cost_claim_allowed": structural_cost,
                "historical_pit_eligible": True,
            }
        )
    features = pd.DataFrame(feature_rows)
    selections = pd.DataFrame(selection_rows)
    if not features.empty:
        features = features.sort_values(["ticker", "period"]).reset_index(drop=True)
    if not selections.empty:
        selections = selections.drop_duplicates().sort_values(
            ["ticker", "period", "series_id"]
        ).reset_index(drop=True)
    return {
        "subindustry_pit_industry_features": features,
        "subindustry_pit_vintage_selection_audit": selections,
    }


def _ridge_fit(
    frame: pd.DataFrame, features: list[str], target: str, penalty: float
) -> RidgeFit:
    x = frame[features].to_numpy(float)
    y = frame[target].to_numpy(float)
    means = x.mean(axis=0)
    scales = x.std(axis=0, ddof=1)
    scales = np.where(scales > 1e-9, scales, 1.0)
    standardized = (x - means) / scales
    design = np.column_stack([np.ones(len(frame)), standardized])
    regularizer = np.eye(design.shape[1]) * penalty
    regularizer[0, 0] = 0.0
    coefficients = np.linalg.solve(
        design.T @ design + regularizer, design.T @ y
    )
    slopes = coefficients[1:] / scales
    intercept = float(y.mean() - means @ slopes)
    fitted = intercept + x @ slopes
    residual_std = float(pd.Series(y - fitted).std(ddof=1))
    return RidgeFit(intercept, tuple(float(value) for value in slopes), residual_std)


def _predict(fit: RidgeFit, row: pd.Series, features: list[str]) -> float:
    return float(
        fit.intercept
        + sum(
            coefficient * float(row[feature])
            for coefficient, feature in zip(fit.coefficients, features)
        )
    )


def build_company_forecast_panel(
    *,
    quarterly: pd.DataFrame,
    origins: pd.DataFrame,
    industry_features: pd.DataFrame,
) -> pd.DataFrame:
    financial = quarterly.copy()
    financial["period_q"] = pd.PeriodIndex(financial["period"], freq="Q")
    financial = financial.sort_values(["ticker", "period_q", "filing_date"])
    financial = financial.drop_duplicates(["ticker", "period_q"], keep="first")
    rows: list[dict[str, object]] = []
    for origin in origins.itertuples(index=False):
        history = financial.loc[financial["ticker"].eq(origin.ticker)].set_index(
            "period_q"
        )
        target_period = pd.Period(origin.period, freq="Q")
        origin_period = pd.Period(origin.origin_period, freq="Q")
        required = [target_period, origin_period, target_period - 4, origin_period - 4]
        if not all(period in history.index for period in required):
            continue
        target = history.loc[target_period]
        prior = history.loc[target_period - 4]
        lag = history.loc[origin_period]
        lag_year = history.loc[origin_period - 4]
        if isinstance(target, pd.DataFrame) or isinstance(lag, pd.DataFrame):
            continue
        industry = industry_features.loc[
            industry_features["ticker"].eq(origin.ticker)
            & industry_features["period"].eq(origin.period)
        ]
        if industry.empty:
            continue
        industry_row = industry.iloc[0]
        revenue_values = [
            target["revenue_usd"],
            prior["revenue_usd"],
            lag["revenue_usd"],
            lag_year["revenue_usd"],
        ]
        if not all(pd.notna(value) and float(value) > 0 for value in revenue_values):
            continue
        target_margin = target["model_profit_margin_pct"]
        lag_margin = lag["model_profit_margin_pct"]
        if pd.isna(target_margin) or pd.isna(lag_margin):
            continue
        lag_rpo_yoy = np.nan
        if (
            pd.notna(lag["remaining_performance_obligation_usd"])
            and pd.notna(lag_year["remaining_performance_obligation_usd"])
            and float(lag_year["remaining_performance_obligation_usd"]) > 0
        ):
            lag_rpo_yoy = (
                float(lag["remaining_performance_obligation_usd"])
                / float(lag_year["remaining_performance_obligation_usd"])
                * 100.0
                - 100.0
            )
        rows.append(
            {
                "ticker": origin.ticker,
                "subindustry_code": origin.subindustry_code,
                "period": origin.period,
                "forecast_as_of": pd.Timestamp(origin.forecast_as_of),
                "actual_available_at": pd.Timestamp(origin.actual_available_at),
                "actual_revenue_usd": float(target["revenue_usd"]),
                "seasonal_naive_revenue_usd": float(prior["revenue_usd"]),
                "actual_revenue_yoy_pct": float(target["revenue_usd"])
                / float(prior["revenue_usd"])
                * 100.0
                - 100.0,
                "lag_revenue_yoy_pct": float(lag["revenue_usd"])
                / float(lag_year["revenue_usd"])
                * 100.0
                - 100.0,
                "actual_profit_margin_pct": float(target_margin),
                "lag_profit_margin_pct": float(lag_margin),
                "actual_margin_delta_pct_points": float(target_margin)
                - float(lag_margin),
                "profit_target_definition": target[
                    "model_profit_target_definition"
                ],
                "profit_target_authority": target[
                    "model_profit_target_authority"
                ],
                "lag_rpo_yoy_pct": lag_rpo_yoy,
                "output_price_yoy_pct": float(
                    industry_row["output_price_yoy_pct"]
                ),
                "input_cost_yoy_pct": float(industry_row["input_cost_yoy_pct"]),
                "price_cost_spread_pct": float(
                    industry_row["price_cost_spread_pct"]
                ),
                "structural_price_cost_claim_allowed": bool(
                    industry_row["structural_price_cost_claim_allowed"]
                ),
                "industry_feature_reference_quarter": industry_row[
                    "feature_reference_quarter"
                ],
                "historical_pit_eligible": True,
                "leakage_check_pass": bool(
                    pd.Timestamp(origin.actual_available_at)
                    > pd.Timestamp(origin.forecast_as_of)
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["ticker", "period"]).reset_index(
        drop=True
    )


def run_fixed_oos_company_forecasts(
    panel: pd.DataFrame,
    *,
    oos_start: pd.Timestamp = pd.Timestamp("2025-01-01"),
    minimum_training_observations: int = 6,
    ridge_penalty: float = 5.0,
) -> dict[str, pd.DataFrame]:
    predictions: list[dict[str, object]] = []
    routes: list[dict[str, object]] = []
    for ticker, group in panel.groupby("ticker"):
        group = group.sort_values("actual_available_at").reset_index(drop=True)
        initial_training = group.loc[group["actual_available_at"].lt(oos_start)]
        ppi_ready = initial_training["output_price_yoy_pct"].notna().mean() >= 0.80
        rpo_ready = initial_training["lag_rpo_yoy_pct"].notna().mean() >= 0.60
        structural_cost = bool(
            initial_training["structural_price_cost_claim_allowed"].mean() >= 0.80
        )
        revenue_features = ["lag_revenue_yoy_pct"]
        margin_features: list[str] = []
        route = "FINANCIAL_ONLY"
        if ppi_ready:
            revenue_features.append("output_price_yoy_pct")
            margin_features.append("output_price_yoy_pct")
            route = "PIT_INDUSTRY_PRICE"
        if structural_cost:
            margin_features.append("price_cost_spread_pct")
            route += "_COST"
        if rpo_ready:
            revenue_features.append("lag_rpo_yoy_pct")
            route += "_RPO_QUANTITY"
        routes.append(
            {
                "ticker": ticker,
                "subindustry_code": group["subindustry_code"].iloc[0],
                "route": route,
                "revenue_features": "|".join(revenue_features),
                "margin_features": "|".join(margin_features)
                if margin_features
                else "INTERCEPT_ONLY_SHRINKAGE",
                "initial_training_observations": len(initial_training),
                "ppi_route_ready": bool(ppi_ready),
                "rpo_quantity_route_ready": bool(rpo_ready),
                "structural_cost_route_ready": bool(structural_cost),
                "route_selected_before_oos": True,
                "post_hoc_route_reselection_allowed": False,
            }
        )
        for index, test in group.loc[group["actual_available_at"].ge(oos_start)].iterrows():
            train = group.loc[
                group["actual_available_at"].lt(test["forecast_as_of"])
            ].copy()
            required = list(dict.fromkeys(revenue_features + margin_features))
            train = train.dropna(
                subset=required
                + ["actual_revenue_yoy_pct", "actual_margin_delta_pct_points"]
            )
            if len(train) < minimum_training_observations:
                continue
            prediction_row = test.copy()
            imputed_features: list[str] = []
            for feature in required:
                if pd.isna(prediction_row[feature]):
                    prediction_row[feature] = float(train[feature].median())
                    imputed_features.append(feature)
            revenue_fit = _ridge_fit(
                train, revenue_features, "actual_revenue_yoy_pct", ridge_penalty
            )
            predicted_growth = _predict(
                revenue_fit, prediction_row, revenue_features
            )
            predicted_revenue = float(test["seasonal_naive_revenue_usd"]) * (
                1.0 + predicted_growth / 100.0
            )
            if margin_features:
                margin_fit = _ridge_fit(
                    train,
                    margin_features,
                    "actual_margin_delta_pct_points",
                    ridge_penalty,
                )
                raw_predicted_delta = _predict(
                    margin_fit, prediction_row, margin_features
                )
                # Fixed ex-ante shrinkage keeps noisy price/cost proxies from
                # overwhelming the highly competitive no-change margin baseline.
                margin_shrinkage_weight = 0.50
                predicted_delta = margin_shrinkage_weight * raw_predicted_delta
                fitted_delta = train[margin_features].apply(
                    lambda row: _predict(margin_fit, row, margin_features), axis=1
                )
                margin_std = float(
                    (
                        train["actual_margin_delta_pct_points"]
                        - margin_shrinkage_weight * fitted_delta
                    ).std(ddof=1)
                )
            else:
                margin_shrinkage_weight = 0.0
                predicted_delta = float(
                    train["actual_margin_delta_pct_points"].mean()
                ) * 0.0
                margin_std = float(
                    train["actual_margin_delta_pct_points"].std(ddof=1)
                )
            predicted_margin = float(test["lag_profit_margin_pct"]) + predicted_delta
            z90 = 1.6448536269514722
            revenue_interval_usd = (
                float(test["seasonal_naive_revenue_usd"])
                * z90
                * revenue_fit.residual_std
                / 100.0
            )
            predictions.append(
                {
                    "ticker": ticker,
                    "subindustry_code": test["subindustry_code"],
                    "period": test["period"],
                    "forecast_as_of": test["forecast_as_of"],
                    "actual_available_at": test["actual_available_at"],
                    "training_observations": len(train),
                    "fixed_route": route,
                    "imputed_feature_count": len(imputed_features),
                    "imputed_features": "|".join(imputed_features),
                    "actual_revenue_usd": test["actual_revenue_usd"],
                    "predicted_revenue_usd": predicted_revenue,
                    "predicted_revenue_yoy_pct": predicted_growth,
                    "seasonal_naive_revenue_usd": test[
                        "seasonal_naive_revenue_usd"
                    ],
                    "predicted_revenue_lower_90_usd": predicted_revenue
                    - revenue_interval_usd,
                    "predicted_revenue_upper_90_usd": predicted_revenue
                    + revenue_interval_usd,
                    "revenue_level_ape_pct": abs(
                        predicted_revenue / float(test["actual_revenue_usd"]) - 1.0
                    )
                    * 100.0,
                    "actual_profit_margin_pct": test[
                        "actual_profit_margin_pct"
                    ],
                    "predicted_profit_margin_pct": predicted_margin,
                    "margin_shrinkage_weight": margin_shrinkage_weight,
                    "naive_profit_margin_pct": test["lag_profit_margin_pct"],
                    "predicted_profit_margin_lower_90_pct": predicted_margin
                    - z90 * margin_std,
                    "predicted_profit_margin_upper_90_pct": predicted_margin
                    + z90 * margin_std,
                    "profit_target_definition": test[
                        "profit_target_definition"
                    ],
                    "profit_target_authority": test["profit_target_authority"],
                    "historical_pit_eligible": test["historical_pit_eligible"],
                    "leakage_check_pass": test["leakage_check_pass"],
                    "performance_claim_allowed": True,
                }
            )
    validation = pd.DataFrame(predictions)
    summaries: list[dict[str, object]] = []
    if not validation.empty:
        for (subindustry, ticker), group in validation.groupby(
            ["subindustry_code", "ticker"]
        ):
            revenue_mae = float(
                (group["predicted_revenue_usd"] - group["actual_revenue_usd"])
                .abs()
                .mean()
            )
            revenue_naive_mae = float(
                (
                    group["seasonal_naive_revenue_usd"]
                    - group["actual_revenue_usd"]
                )
                .abs()
                .mean()
            )
            margin_mae = float(
                (
                    group["predicted_profit_margin_pct"]
                    - group["actual_profit_margin_pct"]
                )
                .abs()
                .mean()
            )
            margin_naive_mae = float(
                (
                    group["naive_profit_margin_pct"]
                    - group["actual_profit_margin_pct"]
                )
                .abs()
                .mean()
            )
            revenue_mase = (
                revenue_mae / revenue_naive_mae if revenue_naive_mae else np.nan
            )
            margin_mase = (
                margin_mae / margin_naive_mae if margin_naive_mae else np.nan
            )
            authority = classify_forecast_authority(
                revenue_mase=revenue_mase if np.isfinite(revenue_mase) else None,
                margin_mase=margin_mase if np.isfinite(margin_mase) else None,
            )
            if len(group) < 4:
                authority = ForecastAuthority.NOT_TESTED
            profit_authority = group["profit_target_authority"].mode().iloc[0]
            if (
                authority == ForecastAuthority.STRONG
                and profit_authority != "REPORTED_STANDARD_TAG"
            ):
                authority = ForecastAuthority.MIXED
            summaries.append(
                {
                    "subindustry_code": subindustry,
                    "ticker": ticker,
                    "oos_observations": len(group),
                    "revenue_mae_usd": revenue_mae,
                    "seasonal_naive_revenue_mae_usd": revenue_naive_mae,
                    "revenue_mase": revenue_mase,
                    "mean_revenue_level_ape_pct": float(
                        group["revenue_level_ape_pct"].mean()
                    ),
                    "revenue_interval_90_coverage_pct": float(
                        (
                            group["actual_revenue_usd"].between(
                                group["predicted_revenue_lower_90_usd"],
                                group["predicted_revenue_upper_90_usd"],
                            )
                        ).mean()
                        * 100.0
                    ),
                    "profit_margin_mae_pct_points": margin_mae,
                    "naive_profit_margin_mae_pct_points": margin_naive_mae,
                    "profit_margin_mase": margin_mase,
                    "profit_margin_interval_90_coverage_pct": float(
                        (
                            group["actual_profit_margin_pct"].between(
                                group[
                                    "predicted_profit_margin_lower_90_pct"
                                ],
                                group[
                                    "predicted_profit_margin_upper_90_pct"
                                ],
                            )
                        ).mean()
                        * 100.0
                    ),
                    "uncertainty_authority": (
                        "PRELIMINARY_90_INTERVAL_COVERAGE_PASS"
                        if len(group) >= 6
                        and 75.0
                        <= float(
                            group["actual_revenue_usd"].between(
                                group["predicted_revenue_lower_90_usd"],
                                group["predicted_revenue_upper_90_usd"],
                            ).mean()
                            * 100.0
                        )
                        <= 100.0
                        and 75.0
                        <= float(
                            group["actual_profit_margin_pct"].between(
                                group[
                                    "predicted_profit_margin_lower_90_pct"
                                ],
                                group[
                                    "predicted_profit_margin_upper_90_pct"
                                ],
                            ).mean()
                            * 100.0
                        )
                        <= 100.0
                        else "NOT_CALIBRATED"
                    ),
                    "profit_target_definition": group[
                        "profit_target_definition"
                    ].mode().iloc[0],
                    "forecast_authority": authority.value,
                    "oos_cutoff": oos_start.date().isoformat(),
                    "fixed_oos": True,
                    "all_cutoffs_respected": bool(
                        group["leakage_check_pass"].all()
                    ),
                    "fair_value_authority": False,
                    "production_authority": False,
                }
            )
    return {
        "subindustry_forecast_routes": pd.DataFrame(routes),
        "subindustry_fixed_oos_forecasts": validation,
        "subindustry_forecast_performance": pd.DataFrame(summaries),
    }
