from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

from equity_platform.core.champion_gate import assess_against_naive
from equity_platform.core.forecast import ridge_predict
from equity_platform.sectors.industrials.common.margin import clip_prediction_to_training_range


RMS_DELIVERY_CATEGORIES = (
    "government_helicopter",
    "commercial_helicopter",
    "international_military_helicopter",
)
AERO_REVENUE_FEATURES = [
    "horizon_adjusted_backlog_yoy_pct",
    "lag_aero_major_program_sales_delta_pct",
    "lag_delivery_yoy_pct",
    "output_price_yoy_pct",
    "lag_revenue_yoy_pct",
]
RMS_REVENUE_FEATURES = [
    "predicted_sikorsky_sales_delta_pct",
    "lag_backlog_yoy_pct",
    "output_price_yoy_pct",
    "lag_revenue_yoy_pct",
]
SPACE_MARGIN_FEATURES = [
    "revenue_driver_pct",
    "lag_margin_pct",
    "output_input_spread_pct",
    "lag_backlog_yoy_pct",
    "lag_space_profit_booking_delta_margin_pp",
    "lag_space_equity_earnings_delta_margin_pp",
]


def _period(value: str) -> pd.Period:
    return pd.Period(value, freq="Q")


def _delivery_category(program: str) -> str | None:
    return {
        "Government helicopter programs": "government_helicopter",
        "Commercial helicopter programs": "commercial_helicopter",
        "International military helicopter programs": "international_military_helicopter",
    }.get(program)


def _rms_delivery_changes(deliveries: pd.DataFrame) -> pd.DataFrame:
    frame = deliveries.copy()
    frame["category"] = frame["delivery_program"].map(_delivery_category)
    frame = frame.loc[frame["category"].notna()].copy()
    frame["delivery_delta_units"] = (
        frame["quarter_deliveries"].fillna(0.0)
        - frame["prior_year_quarter_deliveries"].fillna(0.0)
    )
    periods = sorted(deliveries["period"].unique(), key=_period)
    grid = pd.MultiIndex.from_product(
        [periods, RMS_DELIVERY_CATEGORIES], names=["period", "category"]
    ).to_frame(index=False)
    grouped = frame.groupby(["period", "category"], as_index=False).agg(
        delivery_delta_units=("delivery_delta_units", "sum"),
        filing_date=("filing_date", "first"),
        source_url=("source_url", "first"),
    )
    complete = grid.merge(grouped, on=["period", "category"], how="left", validate="one_to_one")
    complete["delivery_delta_units"] = complete["delivery_delta_units"].fillna(0.0)
    release_dates = deliveries.groupby("period")["filing_date"].first()
    complete["filing_date"] = complete["filing_date"].fillna(complete["period"].map(release_dates))
    pivot = complete.pivot(index="period", columns="category", values="delivery_delta_units").reset_index()
    dates = complete.groupby("period", as_index=False)["filing_date"].first()
    return pivot.merge(dates, on="period", validate="one_to_one")


def _latest_disclosed_backlog(
    backlog: pd.DataFrame,
    horizon: pd.DataFrame,
    *,
    segment: str,
    cutoff: pd.Timestamp,
) -> dict[str, object]:
    history = backlog.loc[
        backlog["segment"].eq(segment)
        & pd.to_datetime(backlog["filing_date"]).le(cutoff)
    ].copy()
    if history.empty:
        return {}
    history["quarter"] = history["period"].map(_period)
    latest = history.sort_values("quarter").iloc[-1]
    prior = history.loc[history["quarter"].eq(latest["quarter"] - 4)]
    if len(prior) != 1:
        return {}
    horizon_frame = horizon.copy()
    horizon_frame["filing_date"] = pd.to_datetime(horizon_frame["filing_date"])

    def known_rate(as_of: pd.Timestamp) -> tuple[float, pd.Timestamp] | None:
        known = horizon_frame.loc[horizon_frame["filing_date"].le(as_of)].sort_values("filing_date")
        if known.empty:
            return None
        row = known.iloc[-1]
        return float(row["backlog_expected_within_12m_pct"]) / 100.0, row["filing_date"]

    latest_rate = known_rate(pd.Timestamp(latest["filing_date"]))
    prior_rate = known_rate(pd.Timestamp(prior.iloc[0]["filing_date"]))
    if latest_rate is None or prior_rate is None:
        return {}
    latest_expected = float(latest["backlog_usd"]) * latest_rate[0]
    prior_expected = float(prior.iloc[0]["backlog_usd"]) * prior_rate[0]
    return {
        "horizon_adjusted_backlog_yoy_pct": latest_expected / prior_expected * 100.0 - 100.0,
        "latest_backlog_period": latest["period"],
        "latest_backlog_available_at": latest["filing_date"],
        "latest_backlog_12m_conversion_pct": latest_rate[0] * 100.0,
        "latest_horizon_available_at": latest_rate[1].date().isoformat(),
    }


def _fit_rms_delivery_values(
    *,
    attribution: pd.DataFrame,
    delivery_changes: pd.DataFrame,
    cutoff: pd.Timestamp,
    penalty: float,
) -> tuple[np.ndarray, int, str | None]:
    rms = attribution.loc[
        attribution["segment"].eq("rotary_mission_systems")
        & attribution["rms_sikorsky_sales_delta_usd"].notna()
    ].copy()
    training = rms.merge(delivery_changes, on="period", how="inner", suffixes=("_attribution", "_delivery"))
    training["filing_date_attribution"] = pd.to_datetime(training["filing_date_attribution"])
    training = training.loc[training["filing_date_attribution"].le(cutoff)]
    if len(training) < 8:
        return np.full(len(RMS_DELIVERY_CATEGORIES), np.nan), len(training), None
    matrix = training[list(RMS_DELIVERY_CATEGORIES)].astype(float).to_numpy()
    target = training["rms_sikorsky_sales_delta_usd"].astype(float).to_numpy()
    augmented_x = np.vstack([matrix, np.sqrt(penalty) * np.eye(len(RMS_DELIVERY_CATEGORIES))])
    augmented_y = np.concatenate([target, np.zeros(len(RMS_DELIVERY_CATEGORIES))])
    coefficients = lsq_linear(augmented_x, augmented_y, bounds=(0.0, np.inf)).x
    max_available = training["filing_date_attribution"].max().date().isoformat()
    return coefficients, len(training), max_available


def build_v31_feature_panel(
    *,
    base_panel: pd.DataFrame,
    attributions: pd.DataFrame,
    deliveries: pd.DataFrame,
    backlog: pd.DataFrame,
    horizon: pd.DataFrame,
    delivery_value_penalty: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = base_panel.copy()
    for column in ("forecast_as_of", "filing_date", "lag_source_available_at"):
        panel[column] = pd.to_datetime(panel[column])
    panel["quarter"] = panel["period"].map(_period)

    attribution = attributions.copy()
    attribution["quarter"] = attribution["period"].map(_period)
    attribution["filing_date"] = pd.to_datetime(attribution["filing_date"])
    attribution = attribution.merge(
        panel[["period", "segment", "sales_usd"]].drop_duplicates(["period", "segment"]),
        on=["period", "segment"],
        how="left",
    )
    attribution["aero_major_program_sales_delta_usd"] = attribution[
        ["aero_f35_sales_delta_usd", "aero_classified_sales_delta_usd"]
    ].sum(axis=1, min_count=1)
    attribution["aero_major_program_sales_delta_pct"] = (
        attribution["aero_major_program_sales_delta_usd"] / attribution["sales_usd"] * 100.0
    )
    attribution["space_profit_booking_delta_margin_pp"] = (
        attribution["space_profit_booking_adjustment_delta_usd"] / attribution["sales_usd"] * 100.0
    )
    attribution["space_equity_earnings_delta_margin_pp"] = (
        attribution["space_equity_earnings_delta_usd"] / attribution["sales_usd"] * 100.0
    )
    lag = attribution[
        [
            "quarter",
            "segment",
            "filing_date",
            "aero_major_program_sales_delta_pct",
            "space_profit_booking_delta_margin_pp",
            "space_equity_earnings_delta_margin_pp",
        ]
    ].copy()
    lag["quarter"] = lag["quarter"] + 1
    lag = lag.rename(
        columns={
            "filing_date": "lag_program_evidence_available_at",
            "aero_major_program_sales_delta_pct": "lag_aero_major_program_sales_delta_pct",
            "space_profit_booking_delta_margin_pp": "lag_space_profit_booking_delta_margin_pp",
            "space_equity_earnings_delta_margin_pp": "lag_space_equity_earnings_delta_margin_pp",
        }
    )
    panel = panel.merge(lag, on=["quarter", "segment"], how="left", validate="one_to_one")

    delivery_changes = _rms_delivery_changes(deliveries)
    delivery_changes["quarter"] = delivery_changes["period"].map(_period)
    weight_rows: list[dict[str, object]] = []
    rms_feature: dict[str, dict[str, object]] = {}
    for _, row in panel.loc[panel["segment"].eq("rotary_mission_systems")].iterrows():
        coefficients, observations, max_available = _fit_rms_delivery_values(
            attribution=attributions,
            delivery_changes=delivery_changes.drop(columns="quarter"),
            cutoff=row["forecast_as_of"],
            penalty=delivery_value_penalty,
        )
        known = delivery_changes.loc[
            pd.to_datetime(delivery_changes["filing_date"]).le(row["forecast_as_of"])
            & delivery_changes["quarter"].lt(row["quarter"])
        ].sort_values("quarter")
        latest = known.iloc[-1] if not known.empty else None
        predicted_delta = (
            float(latest[list(RMS_DELIVERY_CATEGORIES)].astype(float).to_numpy() @ coefficients)
            if latest is not None and np.isfinite(coefficients).all()
            else np.nan
        )
        rms_feature[row["period"]] = {
            "predicted_sikorsky_sales_delta_usd": predicted_delta,
            "predicted_sikorsky_sales_delta_pct": predicted_delta / float(row["prior_year_original_sales_usd"]) * 100.0,
            "rms_program_mix_source_period": latest["period"] if latest is not None else None,
            "rms_program_mix_available_at": latest["filing_date"] if latest is not None else None,
            "rms_delivery_value_training_observations": observations,
            "rms_delivery_value_training_max_available_at": max_available,
        }
        weight_rows.append(
            {
                "forecast_period": row["period"],
                "forecast_as_of": row["forecast_as_of"].date().isoformat(),
                "training_observations": observations,
                "training_max_available_at": max_available,
                **{
                    f"{category}_marginal_revenue_usd_per_delivery": coefficient
                    for category, coefficient in zip(RMS_DELIVERY_CATEGORIES, coefficients)
                },
                "predicted_sikorsky_sales_delta_usd": predicted_delta,
                "coefficient_constraint": "NONNEGATIVE_RIDGE",
            }
        )
    rms_feature_frame = pd.DataFrame(
        [
            {"period": period, "segment": "rotary_mission_systems", **values}
            for period, values in rms_feature.items()
        ]
    )
    panel = panel.merge(
        rms_feature_frame,
        on=["period", "segment"],
        how="left",
        validate="one_to_one",
    )

    horizon_rows: list[dict[str, object]] = []
    for _, row in panel.iterrows():
        evidence = _latest_disclosed_backlog(
            backlog,
            horizon,
            segment=str(row["segment"]),
            cutoff=row["forecast_as_of"],
        )
        horizon_rows.append({"period": row["period"], "segment": row["segment"], **evidence})
    panel = panel.merge(pd.DataFrame(horizon_rows), on=["period", "segment"], how="left", validate="one_to_one")
    panel["program_evidence_cutoff_pass"] = (
        panel["lag_program_evidence_available_at"].isna()
        | panel["lag_program_evidence_available_at"].le(panel["forecast_as_of"])
    )
    panel["backlog_horizon_cutoff_pass"] = (
        pd.to_datetime(panel["latest_horizon_available_at"]).le(panel["forecast_as_of"])
    )
    panel["historical_pit_input"] = (
        panel["historical_pit_input"].astype(bool)
        & panel["program_evidence_cutoff_pass"]
        & panel["backlog_horizon_cutoff_pass"]
    )
    return panel.sort_values(["quarter", "segment"]).reset_index(drop=True), pd.DataFrame(weight_rows)


def build_lmt_v31_forecast(
    *,
    feature_panel: pd.DataFrame,
    parent_walk: pd.DataFrame,
    validation_start_period: str,
    minimum_training_quarters: int,
    ridge_penalty: float,
) -> dict[str, pd.DataFrame]:
    panel = feature_panel.copy()
    panel["quarter"] = panel["period"].map(_period)
    panel["filing_date"] = pd.to_datetime(panel["filing_date"])
    panel["forecast_as_of"] = pd.to_datetime(panel["forecast_as_of"])
    parent = parent_walk.copy().set_index(["period", "segment"])
    start = _period(validation_start_period)
    rows: list[dict[str, object]] = []
    for segment, group in panel.groupby("segment"):
        group = group.sort_values("quarter")
        for _, test in group.loc[group["quarter"].ge(start)].iterrows():
            key = (test["period"], segment)
            parent_row = parent.loc[key]
            base_training = group.loc[
                group["quarter"].lt(test["quarter"])
                & group["filing_date"].le(test["forecast_as_of"])
                & group["historical_pit_input"]
            ].copy()
            revenue_training = base_training.loc[~base_training["unforecastable_scope_change"]]
            margin_training = base_training.loc[~base_training["unforecastable_scope_change"]].copy()
            predicted_sales = float(parent_row["predicted_sales_usd"])
            predicted_growth = float(parent_row["predicted_revenue_growth_pct"])
            revenue_route = str(parent_row["revenue_route"])
            margin_prediction = float(parent_row["predicted_operating_margin_pct"])
            raw_margin_prediction = float(parent_row["raw_predicted_operating_margin_pct"])
            margin_lower = float(parent_row["margin_sanity_lower_pct"])
            margin_upper = float(parent_row["margin_sanity_upper_pct"])
            margin_boundary_hit = bool(parent_row["margin_boundary_hit"])
            margin_route = str(parent_row["margin_route"])
            if len(revenue_training) >= minimum_training_quarters and segment in {"aeronautics", "rotary_mission_systems"}:
                features = AERO_REVENUE_FEATURES if segment == "aeronautics" else RMS_REVENUE_FEATURES
                predicted_growth = ridge_predict(
                    revenue_training,
                    test,
                    features=features,
                    target="actual_revenue_growth_pct",
                    penalty=ridge_penalty,
                )
                predicted_sales = float(test["prior_year_original_sales_usd"]) * (1.0 + predicted_growth / 100.0)
                revenue_route = (
                    "STRUCTURAL_BACKLOG_HORIZON_MAJOR_PROGRAM_MIX"
                    if segment == "aeronautics"
                    else "STRUCTURAL_REVENUE_WEIGHTED_SIKORSKY_PROGRAM_MIX"
                )
            if len(margin_training) >= minimum_training_quarters and segment == "space":
                margin_training["revenue_driver_pct"] = margin_training["actual_revenue_growth_pct"]
                margin_test = test.copy()
                margin_test["revenue_driver_pct"] = predicted_growth
                raw_margin_prediction = ridge_predict(
                    margin_training,
                    margin_test,
                    features=SPACE_MARGIN_FEATURES,
                    target="model_operating_margin_pct",
                    penalty=ridge_penalty,
                )
                margin_prediction, margin_lower, margin_upper, margin_boundary_hit = clip_prediction_to_training_range(
                    raw_margin_prediction, margin_training["model_operating_margin_pct"]
                )
                margin_route = "CONDITIONAL_SPACE_PROFIT_RECOGNITION_BRIDGE"
            row = parent_row.to_dict()
            row.update(
                {
                    "period": test["period"],
                    "segment": segment,
                    "parent_predicted_sales_usd": parent_row["predicted_sales_usd"],
                    "parent_predicted_operating_margin_pct": parent_row["predicted_operating_margin_pct"],
                    "parent_raw_predicted_operating_margin_pct": parent_row["raw_predicted_operating_margin_pct"],
                    "parent_margin_sanity_lower_pct": parent_row["margin_sanity_lower_pct"],
                    "parent_margin_sanity_upper_pct": parent_row["margin_sanity_upper_pct"],
                    "parent_margin_boundary_hit": parent_row["margin_boundary_hit"],
                    "parent_revenue_route": parent_row["revenue_route"],
                    "parent_margin_route": parent_row["margin_route"],
                    "predicted_revenue_growth_pct": predicted_growth,
                    "predicted_sales_usd": predicted_sales,
                    "revenue_route": revenue_route,
                    "predicted_operating_margin_pct": margin_prediction,
                    "raw_predicted_operating_margin_pct": raw_margin_prediction,
                    "margin_sanity_lower_pct": margin_lower,
                    "margin_sanity_upper_pct": margin_upper,
                    "margin_boundary_hit": margin_boundary_hit,
                    "margin_route": margin_route,
                    "predicted_operating_profit_usd": predicted_sales * margin_prediction / 100.0,
                    "revenue_absolute_error_usd": abs(float(test["sales_usd"]) - predicted_sales),
                    "revenue_naive_absolute_error_usd": abs(
                        float(test["sales_usd"]) - float(test["prior_year_original_sales_usd"])
                    ),
                    "revenue_level_ape_pct": abs(predicted_sales / float(test["sales_usd"]) - 1.0) * 100.0,
                    "margin_absolute_error_pct_points": abs(float(test["operating_margin_pct"]) - margin_prediction),
                    "margin_naive_absolute_error_pct_points": abs(
                        float(test["operating_margin_pct"]) - float(test["prior_year_original_margin_pct"])
                    ),
                    "v31_revenue_route_changed": segment in {"aeronautics", "rotary_mission_systems"},
                    "v31_margin_route_changed": segment == "space",
                }
            )
            rows.append(row)
    challenger_walk = pd.DataFrame(rows).sort_values(["segment", "period"]).reset_index(drop=True)

    def summarize(frame: pd.DataFrame, *, compare_parent: bool) -> pd.DataFrame:
        summary_rows: list[dict[str, object]] = []
        for segment, group in frame.groupby("segment"):
            revenue_clean = group.loc[group["revenue_performance_claim_allowed"].astype(bool)]
            margin_clean = group.loc[group["margin_performance_claim_allowed"].astype(bool)]
            revenue = assess_against_naive(
                actual=revenue_clean["actual_sales_usd"],
                prediction=revenue_clean["predicted_sales_usd"],
                naive=revenue_clean["naive_prior_year_sales_usd"],
            )
            margin = assess_against_naive(
                actual=margin_clean["actual_operating_margin_pct"],
                prediction=margin_clean["predicted_operating_margin_pct"],
                naive=margin_clean["naive_prior_year_margin_pct"],
            )
            parent_revenue = assess_against_naive(
                actual=revenue_clean["actual_sales_usd"],
                prediction=revenue_clean["parent_predicted_sales_usd"],
                naive=revenue_clean["naive_prior_year_sales_usd"],
            )
            parent_margin = assess_against_naive(
                actual=margin_clean["actual_operating_margin_pct"],
                prediction=margin_clean["parent_predicted_operating_margin_pct"],
                naive=margin_clean["naive_prior_year_margin_pct"],
            )
            summary_rows.append(
                {
                    "segment": segment,
                    "validation_observations": len(group),
                    "revenue_claim_observations": len(revenue_clean),
                    "margin_claim_observations": len(margin_clean),
                    "revenue_route": group.iloc[0]["revenue_route"],
                    "revenue_mase": revenue.mase,
                    "parent_revenue_mase": parent_revenue.mase,
                    "revenue_mase_change": revenue.mase - parent_revenue.mase if compare_parent else 0.0,
                    "revenue_level_ape_pct": float(revenue_clean["revenue_level_ape_pct"].mean()),
                    "revenue_champion_eligible": revenue.eligible,
                    "margin_route": group.iloc[0]["margin_route"],
                    "margin_mase": margin.mase,
                    "parent_margin_mase": parent_margin.mase,
                    "margin_mase_change": margin.mase - parent_margin.mase if compare_parent else 0.0,
                    "margin_champion_eligible": margin.eligible,
                    "joint_champion": bool(revenue.eligible and margin.eligible),
                    "margin_boundary_hits": int(group["margin_boundary_hit"].sum()),
                    "historical_pit_input_pct": float(
                        feature_panel.loc[
                            feature_panel["segment"].eq(segment), "historical_pit_input"
                        ].mean()
                        * 100.0
                    ),
                }
            )
        return pd.DataFrame(summary_rows).sort_values("segment").reset_index(drop=True)

    challenger_summary = summarize(challenger_walk, compare_parent=True)
    decisions: list[dict[str, object]] = []
    for _, row in challenger_summary.iterrows():
        segment = str(row["segment"])
        revenue_tested = segment in {"aeronautics", "rotary_mission_systems"}
        margin_tested = segment == "space"
        decisions.append(
            {
                "segment": segment,
                "revenue_challenger_tested": revenue_tested,
                "revenue_challenger_accepted": bool(
                    revenue_tested
                    and row["revenue_mase"] < row["parent_revenue_mase"]
                    and row["revenue_mase"] < 1.0
                ),
                "revenue_challenger_mase": row["revenue_mase"],
                "parent_revenue_mase": row["parent_revenue_mase"],
                "margin_challenger_tested": margin_tested,
                "margin_challenger_accepted": bool(
                    margin_tested
                    and row["margin_mase"] < row["parent_margin_mase"]
                    and row["margin_mase"] < 1.0
                ),
                "margin_challenger_mase": row["margin_mase"],
                "parent_margin_mase": row["parent_margin_mase"],
                "selection_policy": "CHALLENGER_MUST_BEAT_PARENT_AND_NAIVE_ON_FIXED_OOS",
            }
        )
    decisions_frame = pd.DataFrame(decisions)
    selected_walk = challenger_walk.copy()
    for _, decision in decisions_frame.iterrows():
        mask = selected_walk["segment"].eq(decision["segment"])
        selected_walk.loc[mask, "challenger_predicted_sales_usd"] = selected_walk.loc[
            mask, "predicted_sales_usd"
        ]
        selected_walk.loc[mask, "challenger_predicted_operating_margin_pct"] = selected_walk.loc[
            mask, "predicted_operating_margin_pct"
        ]
        selected_walk.loc[mask, "challenger_revenue_route"] = selected_walk.loc[mask, "revenue_route"]
        selected_walk.loc[mask, "challenger_margin_route"] = selected_walk.loc[mask, "margin_route"]
        if not decision["revenue_challenger_accepted"]:
            selected_walk.loc[mask, "predicted_sales_usd"] = selected_walk.loc[
                mask, "parent_predicted_sales_usd"
            ]
            selected_walk.loc[mask, "predicted_revenue_growth_pct"] = (
                selected_walk.loc[mask, "predicted_sales_usd"]
                / selected_walk.loc[mask, "naive_prior_year_sales_usd"]
                * 100.0
                - 100.0
            )
            selected_walk.loc[mask, "revenue_route"] = selected_walk.loc[mask, "parent_revenue_route"]
        if not decision["margin_challenger_accepted"]:
            selected_walk.loc[mask, "predicted_operating_margin_pct"] = selected_walk.loc[
                mask, "parent_predicted_operating_margin_pct"
            ]
            selected_walk.loc[mask, "raw_predicted_operating_margin_pct"] = selected_walk.loc[
                mask, "parent_raw_predicted_operating_margin_pct"
            ]
            selected_walk.loc[mask, "margin_sanity_lower_pct"] = selected_walk.loc[
                mask, "parent_margin_sanity_lower_pct"
            ]
            selected_walk.loc[mask, "margin_sanity_upper_pct"] = selected_walk.loc[
                mask, "parent_margin_sanity_upper_pct"
            ]
            selected_walk.loc[mask, "margin_boundary_hit"] = selected_walk.loc[
                mask, "parent_margin_boundary_hit"
            ]
            selected_walk.loc[mask, "margin_route"] = selected_walk.loc[mask, "parent_margin_route"]
        selected_walk.loc[mask, "revenue_challenger_accepted"] = bool(
            decision["revenue_challenger_accepted"]
        )
        selected_walk.loc[mask, "margin_challenger_accepted"] = bool(
            decision["margin_challenger_accepted"]
        )

    selected_walk["predicted_operating_profit_usd"] = (
        selected_walk["predicted_sales_usd"]
        * selected_walk["predicted_operating_margin_pct"]
        / 100.0
    )
    selected_walk["revenue_absolute_error_usd"] = (
        selected_walk["actual_sales_usd"] - selected_walk["predicted_sales_usd"]
    ).abs()
    selected_walk["revenue_level_ape_pct"] = (
        selected_walk["predicted_sales_usd"] / selected_walk["actual_sales_usd"] - 1.0
    ).abs() * 100.0
    selected_walk["margin_absolute_error_pct_points"] = (
        selected_walk["actual_operating_margin_pct"]
        - selected_walk["predicted_operating_margin_pct"]
    ).abs()
    selected_summary = summarize(selected_walk, compare_parent=False)

    parent_summary_rows: list[dict[str, object]] = []
    for segment, group in selected_walk.groupby("segment"):
        parent_summary_rows.append(
            {
                "segment": segment,
                "mfc_all_predictions_preserved": bool(
                    segment != "missiles_fire_control"
                    or (
                        np.allclose(group["predicted_sales_usd"], group["parent_predicted_sales_usd"])
                        and np.allclose(
                            group["predicted_operating_margin_pct"],
                            group["parent_predicted_operating_margin_pct"],
                        )
                    )
                ),
                "space_revenue_preserved": bool(
                    segment != "space"
                    or np.allclose(group["predicted_sales_usd"], group["parent_predicted_sales_usd"])
                ),
                "non_space_margin_preserved": bool(
                    segment == "space"
                    or np.allclose(
                        group["predicted_operating_margin_pct"],
                        group["parent_predicted_operating_margin_pct"],
                    )
                ),
            }
        )
    preservation = pd.DataFrame(parent_summary_rows).sort_values("segment").reset_index(drop=True)
    coverage = pd.DataFrame(
        [
            {
                "validation_rows": len(selected_walk),
                "validation_periods": selected_walk["period"].nunique(),
                "fixed_window_first_period": selected_walk["period"].min(),
                "fixed_window_last_period": selected_walk["period"].max(),
                "cutoff_violations": int((~feature_panel["historical_pit_input"].astype(bool)).sum()),
                "revenue_champions": int(selected_summary["revenue_champion_eligible"].sum()),
                "margin_champions": int(selected_summary["margin_champion_eligible"].sum()),
                "joint_champions": int(selected_summary["joint_champion"].sum()),
                "revenue_challengers_accepted": int(decisions_frame["revenue_challenger_accepted"].sum()),
                "margin_challengers_accepted": int(decisions_frame["margin_challenger_accepted"].sum()),
                "parent_routes_preserved": bool(
                    preservation[
                        ["mfc_all_predictions_preserved", "space_revenue_preserved", "non_space_margin_preserved"]
                    ].all().all()
                ),
            }
        ]
    )
    return {
        "lmt_v31_feature_panel": feature_panel.drop(columns="quarter", errors="ignore"),
        "lmt_v31_challenger_walk_forward": challenger_walk,
        "lmt_v31_challenger_summary": challenger_summary,
        "lmt_v31_walk_forward": selected_walk,
        "lmt_v31_summary": selected_summary,
        "lmt_v31_route_decisions": decisions_frame,
        "lmt_v31_parent_preservation": preservation,
        "lmt_v31_coverage": coverage,
    }
