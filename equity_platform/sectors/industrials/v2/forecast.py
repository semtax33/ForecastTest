from __future__ import annotations

import numpy as np
import pandas as pd

from equity_platform.core.forecast import ridge_predict


SEGMENTS = ("engine", "components", "distribution", "power_systems", "accelera")
REVENUE_ROUTES = {
    "engine": ("STRUCTURAL_UNITS_PRICE", ["lag_anchor_yoy_pct", "output_price_yoy_pct", "lag_revenue_yoy_pct"]),
    "components": ("REDUCED_FORM_INDUSTRY", ["lag_revenue_yoy_pct", "output_price_yoy_pct", "input_cost_yoy_pct"]),
    "distribution": ("REDUCED_FORM_COMPANY", ["lag_revenue_yoy_pct", "lag_margin_pct", "output_price_yoy_pct"]),
    "power_systems": ("CONDITIONAL_STRUCTURAL_OR_REDUCED_FORM", ["lag_anchor_yoy_pct", "lag_mix_hhi", "output_price_yoy_pct", "lag_revenue_yoy_pct"]),
    "accelera": ("REDUCED_FORM_REGIME", ["lag_revenue_yoy_pct", "lag_sequential_growth_pct", "output_price_yoy_pct"]),
}
MARGIN_ROUTES = {
    "engine": ("STRUCTURAL_VOLUME_PRICE_COST", ["predicted_revenue_growth_pct", "input_cost_yoy_pct", "lag_margin_pct"]),
    "components": ("REDUCED_FORM_COST_SPREAD", ["output_input_spread_pct", "lag_margin_pct", "lag_revenue_yoy_pct"]),
    "distribution": ("REDUCED_FORM_MARGIN", ["lag_margin_pct", "lag_revenue_yoy_pct", "input_cost_yoy_pct"]),
    "power_systems": ("REDUCED_FORM_PRODUCT_MIX", ["lag_mix_hhi", "lag_margin_pct", "predicted_revenue_growth_pct"]),
    "accelera": ("REDUCED_FORM_LOSS_REGIME", ["lag_margin_pct", "lag_revenue_yoy_pct", "predicted_revenue_growth_pct"]),
}


def _anchor_features(anchors: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (period, segment), group in anchors.groupby(["period", "segment"]):
        nonfinancial = False
        if segment in {"engine", "power_systems"}:
            unit_group = (
                "ENGINE_UNIT_SHIPMENTS"
                if segment == "engine"
                else "POWER_SYSTEMS_UNIT_SHIPMENTS"
            )
            preferred = group.loc[
                group["anchor_group"].eq(unit_group)
                & group["anchor_item"].eq("Total units")
            ]
            if not preferred.empty:
                anchor_value = float(preferred.iloc[0]["value"])
                mix = group.loc[
                    group["anchor_group"].eq(unit_group)
                    & ~group["anchor_item"].eq("Total units")
                ]
                nonfinancial = True
            else:
                preferred = group.loc[group["anchor_item"].eq("Total sales")]
                anchor_value = float(preferred.iloc[0]["value"]) if not preferred.empty else np.nan
                mix = group.loc[~group["anchor_item"].eq("Total sales")]
        else:
            preferred = group.loc[group["anchor_item"].eq("Total sales")]
            anchor_value = float(preferred.iloc[0]["value"]) if not preferred.empty else np.nan
            mix = group.loc[~group["anchor_item"].eq("Total sales")]
        positive = mix.loc[mix["value"].gt(0.0), "value"].astype(float)
        shares = positive / positive.sum() if not positive.empty else pd.Series(dtype=float)
        rows.append(
            {
                "period": period,
                "segment": segment,
                "anchor_value": anchor_value,
                "mix_hhi": float((shares ** 2).sum()) if not shares.empty else np.nan,
                "anchor_items": int(len(positive)),
                "anchor_source_available": bool(np.isfinite(anchor_value)),
                "nonfinancial_anchor_available": nonfinancial,
            }
        )
    frame = pd.DataFrame(rows)
    complete = pd.MultiIndex.from_product(
        [sorted(anchors["period"].unique()), SEGMENTS], names=["period", "segment"]
    ).to_frame(index=False)
    frame = complete.merge(frame, on=["period", "segment"], how="left")
    frame["quarter"] = pd.PeriodIndex(frame["period"], freq="Q")
    frame = frame.sort_values(["segment", "quarter"])
    frame["anchor_yoy_pct"] = frame.groupby("segment")["anchor_value"].pct_change(4, fill_method=None) * 100.0
    frame["anchor_qoq_pct"] = frame.groupby("segment")["anchor_value"].pct_change(1, fill_method=None) * 100.0
    frame["anchor_source_available"] = frame["anchor_source_available"].eq(True)
    frame["nonfinancial_anchor_available"] = frame["nonfinancial_anchor_available"].eq(True)
    return frame.drop(columns="quarter").reset_index(drop=True)


def _build_panel(
    *,
    history: pd.DataFrame,
    scope_audit: pd.DataFrame,
    scope_events: pd.DataFrame,
    anchors: pd.DataFrame,
    industry_features: pd.DataFrame,
    forecast_origins: pd.DataFrame,
) -> pd.DataFrame:
    frame = history.copy()
    frame["quarter"] = pd.PeriodIndex(frame["period"], freq="Q")
    prior = frame[["quarter", "segment", "total_sales_usd", "ebitda_margin_pct"]].copy()
    prior["quarter"] = prior["quarter"] + 4
    prior = prior.rename(
        columns={
            "total_sales_usd": "prior_year_original_sales_usd",
            "ebitda_margin_pct": "prior_year_original_margin_pct",
        }
    )
    frame = frame.merge(prior, on=["quarter", "segment"], how="left", validate="one_to_one")
    frame["actual_revenue_growth_pct"] = (
        frame["total_sales_usd"] / frame["prior_year_original_sales_usd"] * 100.0 - 100.0
    )
    frame["sequential_revenue_growth_pct"] = frame.groupby("segment")["total_sales_usd"].pct_change(
        fill_method=None
    ) * 100.0
    anchor = _anchor_features(anchors)
    frame = frame.merge(anchor, on=["period", "segment"], how="left", validate="one_to_one")

    lag = frame[
        [
            "quarter", "segment", "actual_revenue_growth_pct", "sequential_revenue_growth_pct",
            "ebitda_margin_pct", "anchor_yoy_pct", "anchor_qoq_pct", "mix_hhi",
            "anchor_source_available", "nonfinancial_anchor_available", "filing_date",
        ]
    ].copy()
    lag["quarter"] = lag["quarter"] + 1
    lag = lag.rename(
        columns={
            "actual_revenue_growth_pct": "lag_revenue_yoy_pct",
            "sequential_revenue_growth_pct": "lag_sequential_growth_pct",
            "ebitda_margin_pct": "lag_margin_pct",
            "anchor_yoy_pct": "lag_anchor_yoy_pct",
            "anchor_qoq_pct": "lag_anchor_qoq_pct",
            "mix_hhi": "lag_mix_hhi",
            "anchor_source_available": "lag_anchor_source_available",
            "nonfinancial_anchor_available": "lag_nonfinancial_anchor_available",
            "filing_date": "lag_source_available_at",
        }
    )
    frame = frame.merge(lag, on=["quarter", "segment"], how="left", validate="one_to_one")
    frame = frame.merge(forecast_origins, on="period", how="inner", validate="many_to_one", suffixes=("", "_origin"))
    frame = frame.merge(
        industry_features.drop(columns=["actual_available_at"], errors="ignore"),
        on=["period", "segment", "forecast_as_of"],
        how="inner",
        validate="one_to_one",
    )
    frame["input_cost_yoy_pct"] = frame["dedicated_cost_yoy_pct"]
    frame["output_input_spread_pct"] = frame["output_price_yoy_pct"] - frame["input_cost_yoy_pct"]
    changes = scope_audit.loc[
        scope_audit["material_scope_change"], ["filing_period", "segment"]
    ].copy()
    changes = changes.rename(columns={"filing_period": "period"}).drop_duplicates()
    changes["cross_release_scope_change"] = True
    frame = frame.merge(changes, on=["period", "segment"], how="left")
    frame["cross_release_scope_change"] = frame["cross_release_scope_change"].eq(True)
    event_keys = set(
        scope_events[["affected_forecast_period", "segment"]].itertuples(
            index=False, name=None
        )
    )
    frame["known_transaction_scope_change"] = [
        (period, segment) in event_keys
        for period, segment in frame[["period", "segment"]].itertuples(index=False, name=None)
    ]
    frame["unforecastable_scope_change"] = (
        frame["cross_release_scope_change"] | frame["known_transaction_scope_change"]
    )
    frame["scope_change_treatment"] = np.where(
        frame["unforecastable_scope_change"],
        "UNFORECASTABLE_SCOPE_CHANGE",
        "COMPARABLE_AND_REPORTED_PERIMETER_ALIGNED",
    )
    frame["forecast_as_of"] = pd.to_datetime(frame["forecast_as_of"])
    frame["filing_date"] = pd.to_datetime(frame["filing_date"])
    frame["lag_source_available_at"] = pd.to_datetime(frame["lag_source_available_at"])
    frame["historical_pit_input"] = (
        frame["historical_pit_eligible"].astype(bool)
        & frame["lag_source_available_at"].le(frame["forecast_as_of"])
        & frame["filing_date"].gt(frame["forecast_as_of"])
    )
    return frame.sort_values(["quarter", "segment"]).reset_index(drop=True)


def build_cmi_portability_forecast(
    *,
    history: pd.DataFrame,
    scope_audit: pd.DataFrame,
    scope_events: pd.DataFrame,
    anchors: pd.DataFrame,
    industry_features: pd.DataFrame,
    forecast_origins: pd.DataFrame,
    validation_start_period: str,
    minimum_training_quarters: int,
    ridge_penalty: float,
) -> dict[str, pd.DataFrame]:
    panel = _build_panel(
        history=history,
        scope_audit=scope_audit,
        scope_events=scope_events,
        anchors=anchors,
        industry_features=industry_features,
        forecast_origins=forecast_origins,
    )
    start = pd.Period(validation_start_period, freq="Q")
    rows: list[dict[str, object]] = []
    for segment, group in panel.groupby("segment"):
        group = group.sort_values("quarter")
        revenue_route, revenue_features = REVENUE_ROUTES[segment]
        margin_route, margin_features = MARGIN_ROUTES[segment]
        for _, test in group.loc[group["quarter"].ge(start)].iterrows():
            training = group.loc[
                group["quarter"].lt(test["quarter"])
                & group["filing_date"].le(test["forecast_as_of"])
                & group["historical_pit_input"]
            ].copy()
            if len(training) < minimum_training_quarters:
                continue
            predicted_growth = ridge_predict(
                training, test, features=revenue_features,
                target="actual_revenue_growth_pct", penalty=ridge_penalty
            )
            predicted_sales = float(test["prior_year_original_sales_usd"]) * (
                1.0 + predicted_growth / 100.0
            )
            training = training.copy()
            training["predicted_revenue_growth_pct"] = [
                ridge_predict(
                    training.loc[training["quarter"].lt(row["quarter"])],
                    row,
                    features=revenue_features,
                    target="actual_revenue_growth_pct",
                    penalty=ridge_penalty,
                )
                if len(training.loc[training["quarter"].lt(row["quarter"])]) >= 4
                else row["lag_revenue_yoy_pct"]
                for _, row in training.iterrows()
            ]
            test_for_margin = test.copy()
            test_for_margin["predicted_revenue_growth_pct"] = predicted_growth
            predicted_margin = ridge_predict(
                training, test_for_margin, features=margin_features,
                target="ebitda_margin_pct", penalty=ridge_penalty
            )
            rows.append(
                {
                    "period": test["period"],
                    "segment": segment,
                    "forecast_as_of": test["forecast_as_of"].date().isoformat(),
                    "actual_available_at": test["filing_date"].date().isoformat(),
                    "training_quarters": len(training),
                    "revenue_route": (
                        "STRUCTURAL_UNITS_PRICE_MIX"
                        if segment == "power_systems" and bool(test["lag_nonfinancial_anchor_available"])
                        else "REDUCED_FORM_PRODUCT_MIX_FALLBACK"
                        if segment == "power_systems"
                        else revenue_route
                    ),
                    "predeclared_revenue_route": revenue_route,
                    "margin_route": margin_route,
                    "actual_sales_usd": test["total_sales_usd"],
                    "naive_prior_year_sales_usd": test["prior_year_original_sales_usd"],
                    "predicted_sales_usd": predicted_sales,
                    "actual_revenue_growth_pct": test["actual_revenue_growth_pct"],
                    "predicted_revenue_growth_pct": predicted_growth,
                    "actual_ebitda_margin_pct": test["ebitda_margin_pct"],
                    "naive_prior_year_margin_pct": test["prior_year_original_margin_pct"],
                    "predicted_ebitda_margin_pct": predicted_margin,
                    "actual_ebitda_usd": test["ebitda_usd"],
                    "predicted_ebitda_usd": predicted_sales * predicted_margin / 100.0,
                    "revenue_absolute_error_usd": abs(test["total_sales_usd"] - predicted_sales),
                    "revenue_naive_absolute_error_usd": abs(test["total_sales_usd"] - test["prior_year_original_sales_usd"]),
                    "revenue_level_ape_pct": abs(predicted_sales / test["total_sales_usd"] - 1.0) * 100.0,
                    "margin_absolute_error_pct_points": abs(test["ebitda_margin_pct"] - predicted_margin),
                    "margin_naive_absolute_error_pct_points": abs(test["ebitda_margin_pct"] - test["prior_year_original_margin_pct"]),
                    "output_price_yoy_pct": test["output_price_yoy_pct"],
                    "input_cost_yoy_pct": test["input_cost_yoy_pct"],
                    "lag_anchor_yoy_pct": test["lag_anchor_yoy_pct"],
                    "lag_mix_hhi": test["lag_mix_hhi"],
                    "lag_anchor_source_available": bool(test["lag_anchor_source_available"]),
                    "lag_nonfinancial_anchor_available": bool(test["lag_nonfinancial_anchor_available"]),
                    "historical_pit_input": bool(test["historical_pit_input"]),
                    "actual_after_forecast": bool(test["filing_date"] > test["forecast_as_of"]),
                    "unforecastable_scope_change": bool(test["unforecastable_scope_change"]),
                    "scope_change_treatment": test["scope_change_treatment"],
                    "performance_claim_allowed": bool(not test["unforecastable_scope_change"]),
                    "revenue_and_margin_champions_separate": True,
                }
            )
    walk = pd.DataFrame(rows).sort_values(["segment", "period"]).reset_index(drop=True)
    summary_rows: list[dict[str, object]] = []
    for segment, group in walk.groupby("segment"):
        clean = group.loc[group["performance_claim_allowed"]]
        revenue_mae = float(clean["revenue_absolute_error_usd"].mean())
        revenue_naive = float(clean["revenue_naive_absolute_error_usd"].mean())
        margin_mae = float(clean["margin_absolute_error_pct_points"].mean())
        margin_naive = float(clean["margin_naive_absolute_error_pct_points"].mean())
        revenue_mase = revenue_mae / revenue_naive if revenue_naive else np.nan
        margin_mase = margin_mae / margin_naive if margin_naive else np.nan
        summary_rows.append(
            {
                "segment": segment,
                "validation_observations": len(group),
                "performance_claim_observations": len(clean),
                "scope_change_rows": int(group["unforecastable_scope_change"].sum()),
                "revenue_route": group.iloc[0]["predeclared_revenue_route"],
                "realized_revenue_routes": "|".join(sorted(group["revenue_route"].unique())),
                "structural_anchor_coverage_pct": float(group["lag_nonfinancial_anchor_available"].mean() * 100.0),
                "revenue_mae_usd": revenue_mae,
                "revenue_mase": revenue_mase,
                "revenue_level_ape_pct": float(clean["revenue_level_ape_pct"].mean()),
                "revenue_champion_eligible": bool(len(clean) >= 4 and revenue_mase < 1.0),
                "margin_route": group.iloc[0]["margin_route"],
                "margin_mae_pct_points": margin_mae,
                "margin_mase": margin_mase,
                "margin_champion_eligible": bool(len(clean) >= 4 and margin_mase < 1.0),
                "joint_champion": bool(len(clean) >= 4 and revenue_mase < 1.0 and margin_mase < 1.0),
                "historical_pit_input_pct": float(group["historical_pit_input"].mean() * 100.0),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values("segment").reset_index(drop=True)
    coverage = pd.DataFrame(
        [
            {
                "segments": walk["segment"].nunique(),
                "validation_rows": len(walk),
                "validation_periods": walk["period"].nunique(),
                "historical_pit_rows": int(walk["historical_pit_input"].sum()),
                "cutoff_violations": int((~walk["actual_after_forecast"]).sum()),
                "revenue_champions": int(summary["revenue_champion_eligible"].sum()),
                "margin_champions": int(summary["margin_champion_eligible"].sum()),
                "joint_champions": int(summary["joint_champion"].sum()),
                "structural_revenue_routes": int(summary["revenue_route"].str.startswith("STRUCTURAL").sum()),
                "structural_margin_routes": int(summary["margin_route"].str.startswith("STRUCTURAL").sum()),
                "revenue_margin_authority_separated": True,
            }
        ]
    )
    return {
        "cmi_portability_feature_panel": panel.drop(columns="quarter"),
        "cmi_portability_walk_forward": walk,
        "cmi_portability_summary": summary,
        "cmi_portability_coverage": coverage,
    }
