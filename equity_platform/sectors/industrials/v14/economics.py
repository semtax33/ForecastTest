from __future__ import annotations

import numpy as np
import pandas as pd


def _ridge(frame: pd.DataFrame, features: list[str], target: str, penalty: float, *, nonnegative: bool) -> dict[str, float]:
    x = frame[features].to_numpy(float)
    y = frame[target].to_numpy(float)
    means = x.mean(axis=0)
    scales = x.std(axis=0, ddof=1)
    scales = np.where(scales > 1e-9, scales, 1.0)
    standardized = (x - means) / scales
    design = np.column_stack([np.ones(len(frame)), standardized])
    regularizer = np.eye(design.shape[1]) * penalty
    regularizer[0, 0] = 0.0
    coefficients = np.linalg.solve(design.T @ design + regularizer, design.T @ y)
    slopes = coefficients[1:] / scales
    if nonnegative:
        slopes = np.maximum(slopes, 0.0)
    intercept = float(y.mean() - means @ slopes)
    fitted = intercept + x @ slopes
    result = {"intercept": intercept, "residual_std": float(pd.Series(y - fitted).std(ddof=max(2, len(features) + 1)))}
    result.update({feature: float(value) for feature, value in zip(features, slopes)})
    return result


def _hierarchical_fit(
    segment_train: pd.DataFrame,
    pooled_train: pd.DataFrame,
    *,
    features: list[str],
    target: str,
    penalty: float,
    prior_strength: float,
    nonnegative: bool = True,
) -> dict[str, float]:
    segment = _ridge(segment_train, features, target, penalty, nonnegative=nonnegative)
    pooled = _ridge(pooled_train, features, target, penalty, nonnegative=nonnegative)
    weight = len(segment_train) / (len(segment_train) + prior_strength)
    result = {key: weight * segment[key] + (1.0 - weight) * pooled[key] for key in ["intercept", "residual_std", *features]}
    result["segment_weight"] = weight
    return result


def _predict(fit: dict[str, float], row: pd.Series, features: list[str]) -> float:
    return float(fit["intercept"] + sum(fit[feature] * float(row[feature]) for feature in features))


def _margin_shrinkage_weight(
    training: pd.DataFrame,
    *,
    volume_fit: dict[str, float],
    price_fit: dict[str, float],
    cost_fit: dict[str, float],
    penalty: float,
) -> tuple[float, float]:
    structural_deltas: list[float] = []
    actual_deltas: list[float] = []
    other = float(training["currency_other_contribution_pct"].median())
    for _, row in training.iterrows():
        revenue_growth = (
            _predict(volume_fit, row, ["industry_revenue_signal_pct"])
            + _predict(price_fit, row, ["output_price_yoy_pct"])
            + other
        )
        cost_growth = _predict(cost_fit, row, ["industry_revenue_signal_pct", "dedicated_cost_yoy_pct"])
        sales = float(row["comparable_prior_sales_usd"]) * (1.0 + revenue_growth / 100.0)
        cost = float(row["comparable_prior_operating_cost_usd"]) * (1.0 + cost_growth / 100.0)
        raw_margin = (sales - cost) / sales * 100.0
        structural_deltas.append(raw_margin - float(row["prior_margin_pct"]))
        actual_deltas.append(float(row["margin_delta_pct_points"]))
    x = np.asarray(structural_deltas)
    y = np.asarray(actual_deltas)
    scale = max(float(np.var(x)), 1.0)
    denominator = float(x @ x + penalty * scale)
    weight = float(np.clip((x @ y) / denominator, 0.0, 1.0)) if denominator else 0.0
    residual = y - weight * x
    residual_std = float(pd.Series(residual).std(ddof=1))
    return weight, residual_std


def _build_panel(
    *,
    pq_bridge: pd.DataFrame,
    ir_history: pd.DataFrame,
    segment_sensors: pd.DataFrame,
    industry_signals: pd.DataFrame,
) -> pd.DataFrame:
    history = ir_history.loc[ir_history["segment"].isin(["construction", "resource", "power_energy"])].copy()
    history["prior_margin_pct"] = history["comparable_prior_segment_profit_usd"] / history["comparable_prior_sales_usd"] * 100.0
    history["margin_delta_pct_points"] = history["segment_margin_pct"] - history["prior_margin_pct"]
    history["actual_cost_growth_pct"] = history["operating_cost_usd"] / history["comparable_prior_operating_cost_usd"] * 100.0 - 100.0
    columns = [
        "period", "segment", "sales_usd", "segment_profit_usd", "operating_cost_usd",
        "comparable_prior_sales_usd", "comparable_prior_segment_profit_usd", "comparable_prior_operating_cost_usd",
        "segment_margin_pct", "prior_margin_pct", "margin_delta_pct_points", "actual_cost_growth_pct",
    ]
    panel = history[columns].merge(
        pq_bridge[["period", "segment", "volume_contribution_pct", "price_contribution_pct", "currency_other_contribution_pct", "reported_revenue_growth_pct"]],
        on=["period", "segment"], how="inner", validate="one_to_one",
    )
    panel = panel.merge(segment_sensors, on=["period", "segment"], how="inner", validate="one_to_one")
    panel = panel.merge(
        industry_signals[["period", "segment", "industry_revenue_signal_pct"]],
        on=["period", "segment"], how="inner", validate="one_to_one",
    )
    panel["historical_pit_input"] = False
    return panel.sort_values(["period", "segment"]).reset_index(drop=True)


def _walk_forward(
    panel: pd.DataFrame,
    *,
    minimum_training_quarters: int,
    penalty: float,
    prior_strength: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    volume_features = ["industry_revenue_signal_pct"]
    price_features = ["output_price_yoy_pct"]
    cost_features = ["industry_revenue_signal_pct", "dedicated_cost_yoy_pct"]
    for segment, group in panel.groupby("segment"):
        group = group.sort_values("period").reset_index(drop=True)
        for index in range(minimum_training_quarters, len(group)):
            test = group.iloc[index]
            earlier = set(group.iloc[:index]["period"])
            pooled = panel.loc[panel["period"].isin(earlier)]
            training = group.iloc[:index]
            volume_fit = _hierarchical_fit(training, pooled, features=volume_features, target="volume_contribution_pct", penalty=penalty, prior_strength=prior_strength)
            price_fit = _hierarchical_fit(training, pooled, features=price_features, target="price_contribution_pct", penalty=penalty, prior_strength=prior_strength)
            cost_fit = _hierarchical_fit(training, pooled, features=cost_features, target="actual_cost_growth_pct", penalty=penalty, prior_strength=prior_strength)
            predicted_volume = _predict(volume_fit, test, volume_features)
            predicted_price = _predict(price_fit, test, price_features)
            predicted_other = float(training["currency_other_contribution_pct"].median())
            predicted_revenue_growth = predicted_volume + predicted_price + predicted_other
            predicted_cost_growth = _predict(cost_fit, test, cost_features)
            prior_sales = float(test["comparable_prior_sales_usd"])
            prior_cost = float(test["comparable_prior_operating_cost_usd"])
            predicted_sales = prior_sales * (1.0 + predicted_revenue_growth / 100.0)
            raw_predicted_cost = prior_cost * (1.0 + predicted_cost_growth / 100.0)
            raw_predicted_margin = (predicted_sales - raw_predicted_cost) / predicted_sales * 100.0
            margin_weight, margin_residual_std = _margin_shrinkage_weight(
                training,
                volume_fit=volume_fit,
                price_fit=price_fit,
                cost_fit=cost_fit,
                penalty=penalty,
            )
            predicted_margin = float(test["prior_margin_pct"]) + margin_weight * (raw_predicted_margin - float(test["prior_margin_pct"]))
            bridge_predicted_cost = predicted_sales * (1.0 - predicted_margin / 100.0)
            interval = 1.6448536269514722 * margin_residual_std
            rows.append(
                {
                    "segment": segment,
                    "period": test["period"],
                    "training_quarters": index,
                    "actual_volume_contribution_pct": test["volume_contribution_pct"],
                    "predicted_volume_contribution_pct": predicted_volume,
                    "actual_price_contribution_pct": test["price_contribution_pct"],
                    "predicted_price_contribution_pct": predicted_price,
                    "predicted_other_contribution_pct": predicted_other,
                    "actual_revenue_growth_pct": test["reported_revenue_growth_pct"],
                    "predicted_revenue_growth_pct": predicted_revenue_growth,
                    "unit_capture_revenue_growth_pct": test["industry_revenue_signal_pct"],
                    "actual_cost_growth_pct": test["actual_cost_growth_pct"],
                    "predicted_cost_growth_pct": predicted_cost_growth,
                    "actual_margin_pct": test["segment_margin_pct"],
                    "prior_margin_pct": test["prior_margin_pct"],
                    "raw_bridge_margin_pct": raw_predicted_margin,
                    "margin_shrinkage_weight": margin_weight,
                    "predicted_margin_pct": predicted_margin,
                    "predicted_margin_lower_pct": predicted_margin - interval,
                    "predicted_margin_upper_pct": predicted_margin + interval,
                    "actual_sales_usd": test["sales_usd"],
                    "predicted_sales_usd": predicted_sales,
                    "comparable_prior_sales_usd": prior_sales,
                    "actual_cost_usd": test["operating_cost_usd"],
                    "predicted_cost_usd": raw_predicted_cost,
                    "bridge_predicted_cost_usd": bridge_predicted_cost,
                    "comparable_prior_cost_usd": prior_cost,
                    "revenue_level_ape_pct": abs(predicted_sales / float(test["sales_usd"]) - 1.0) * 100.0,
                    "dedicated_cost_yoy_pct": test["dedicated_cost_yoy_pct"],
                    "historical_pit_input": False,
                    "performance_claim_allowed": False,
                }
            )
    return pd.DataFrame(rows)


def _summaries(validation: pd.DataFrame, v13_validation: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    for segment, group in validation.groupby("segment"):
        margin_mae = float((group["actual_margin_pct"] - group["predicted_margin_pct"]).abs().mean())
        naive_margin_mae = float((group["actual_margin_pct"] - group["prior_margin_pct"]).abs().mean())
        revenue_mae = float((group["actual_revenue_growth_pct"] - group["predicted_revenue_growth_pct"]).abs().mean())
        unit_mae = float((group["actual_revenue_growth_pct"] - group["unit_capture_revenue_growth_pct"]).abs().mean())
        common = group.merge(
            v13_validation.loc[v13_validation["segment"].eq(segment), ["period", "predicted_margin_pct"]].rename(columns={"predicted_margin_pct": "v13_predicted_margin_pct"}),
            on="period", how="inner",
        )
        v14_common_mae = float((common["actual_margin_pct"] - common["predicted_margin_pct"]).abs().mean()) if not common.empty else np.nan
        v13_common_mae = float((common["actual_margin_pct"] - common["v13_predicted_margin_pct"]).abs().mean()) if not common.empty else np.nan
        summary_rows.append(
            {
                "segment": segment,
                "validation_observations": len(group),
                "margin_mae_pct_points": margin_mae,
                "prior_margin_mae_pct_points": naive_margin_mae,
                "margin_mase_vs_prior": margin_mae / naive_margin_mae if naive_margin_mae else np.nan,
                "common_v13_observations": len(common),
                "v14_common_margin_mae_pct_points": v14_common_mae,
                "v13_common_margin_mae_pct_points": v13_common_mae,
                "margin_mae_improvement_vs_v13_pct": (1.0 - v14_common_mae / v13_common_mae) * 100.0 if v13_common_mae else np.nan,
                "revenue_mae_pct": revenue_mae,
                "unit_capture_revenue_mae_pct": unit_mae,
                "revenue_mae_improvement_vs_unit_pct": (1.0 - revenue_mae / unit_mae) * 100.0 if unit_mae else np.nan,
                "mean_revenue_level_ape_pct": float(group["revenue_level_ape_pct"].mean()),
                "historical_pit_vintages_available": False,
                "margin_model_validated": False,
                "performance_claim_allowed": False,
            }
        )
        for component, actual, predicted in [
            ("VOLUME", "actual_volume_contribution_pct", "predicted_volume_contribution_pct"),
            ("PRICE", "actual_price_contribution_pct", "predicted_price_contribution_pct"),
            ("COST", "actual_cost_growth_pct", "predicted_cost_growth_pct"),
        ]:
            component_rows.append(
                {
                    "segment": segment,
                    "component": component,
                    "validation_observations": len(group),
                    "mae_pct": float((group[actual] - group[predicted]).abs().mean()),
                    "actual_mean_pct": float(group[actual].mean()),
                    "predicted_mean_pct": float(group[predicted].mean()),
                    "historical_pit_vintages_available": False,
                }
            )
    return pd.DataFrame(summary_rows), pd.DataFrame(component_rows)


def _final_coefficients(panel: pd.DataFrame, penalty: float, prior_strength: float) -> pd.DataFrame:
    specs = [
        ("VOLUME", ["industry_revenue_signal_pct"], "volume_contribution_pct"),
        ("PRICE", ["output_price_yoy_pct"], "price_contribution_pct"),
        ("COST", ["industry_revenue_signal_pct", "dedicated_cost_yoy_pct"], "actual_cost_growth_pct"),
    ]
    rows: list[dict[str, object]] = []
    for segment, group in panel.groupby("segment"):
        for component, features, target in specs:
            fit = _hierarchical_fit(group, panel, features=features, target=target, penalty=penalty, prior_strength=prior_strength)
            rows.append(
                {
                    "segment": segment,
                    "component": component,
                    "observations": len(group),
                    "intercept_pct": fit["intercept"],
                    "industry_activity_beta": fit.get("industry_revenue_signal_pct", np.nan),
                    "output_price_beta": fit.get("output_price_yoy_pct", np.nan),
                    "dedicated_cost_beta": fit.get("dedicated_cost_yoy_pct", np.nan),
                    "hierarchical_segment_weight": fit["segment_weight"],
                    "residual_std_pct": fit["residual_std"],
                    "structural_parameter_claim_allowed": False,
                }
            )
    return pd.DataFrame(rows)


def build_segment_margin_research(
    *,
    pq_bridge: pd.DataFrame,
    ir_history: pd.DataFrame,
    segment_sensors: pd.DataFrame,
    industry_signals: pd.DataFrame,
    v13_validation: pd.DataFrame,
    minimum_training_quarters: int,
    ridge_penalty: float,
    prior_strength: float,
) -> dict[str, pd.DataFrame]:
    panel = _build_panel(pq_bridge=pq_bridge, ir_history=ir_history, segment_sensors=segment_sensors, industry_signals=industry_signals)
    validation = _walk_forward(panel, minimum_training_quarters=minimum_training_quarters, penalty=ridge_penalty, prior_strength=prior_strength)
    summary, components = _summaries(validation, v13_validation)
    coefficients = _final_coefficients(panel, ridge_penalty, prior_strength)
    return {
        "segment_cost_economics_panel": panel,
        "segment_margin_walk_forward": validation,
        "segment_margin_validation_summary": summary,
        "segment_component_validation_summary": components,
        "segment_cost_economics_coefficients": coefficients,
    }
