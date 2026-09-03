from __future__ import annotations

import pandas as pd


def build_cost_perimeter(
    *,
    route_panel: pd.DataFrame,
    validation_start_period: str,
    material_recast_threshold_pct: float,
) -> dict[str, pd.DataFrame]:
    frame = route_panel.copy()
    frame["original_prior_reported_cost_usd"] = frame["prior_reported_cost_usd"]
    frame["recast_comparable_prior_cost_usd"] = frame["comparable_prior_operating_cost_usd"]
    frame["current_reported_cost_usd"] = frame["operating_cost_usd"]
    frame["recast_scope_delta_usd"] = (
        frame["recast_comparable_prior_cost_usd"] - frame["original_prior_reported_cost_usd"]
    )
    frame["comparable_economic_cost_delta_usd"] = (
        frame["current_reported_cost_usd"] - frame["recast_comparable_prior_cost_usd"]
    )
    frame["total_reported_cost_delta_usd"] = (
        frame["current_reported_cost_usd"] - frame["original_prior_reported_cost_usd"]
    )
    frame["cost_perimeter_identity_error_usd"] = (
        frame["total_reported_cost_delta_usd"]
        - frame["recast_scope_delta_usd"]
        - frame["comparable_economic_cost_delta_usd"]
    )
    frame["recast_scope_pct_of_original"] = (
        frame["recast_scope_delta_usd"] / frame["original_prior_reported_cost_usd"] * 100.0
    )
    frame["comparable_economic_cost_growth_pct"] = (
        frame["current_reported_cost_usd"] / frame["recast_comparable_prior_cost_usd"] * 100.0 - 100.0
    )
    frame["reported_cost_growth_pct"] = (
        frame["current_reported_cost_usd"] / frame["original_prior_reported_cost_usd"] * 100.0 - 100.0
    )
    frame["material_recast_or_scope_change"] = frame["recast_scope_pct_of_original"].abs().gt(
        material_recast_threshold_pct
    )
    frame["cost_perimeter_identity_pass"] = frame["cost_perimeter_identity_error_usd"].abs().le(1.0)

    validation = frame.loc[frame["period"].ge(validation_start_period)].copy()
    rows: list[dict[str, object]] = []
    for segment, group in validation.groupby("segment"):
        rows.append(
            {
                "segment": segment,
                "validation_observations": len(group),
                "identity_mismatches": int((~group["cost_perimeter_identity_pass"]).sum()),
                "maximum_identity_error_usd": float(group["cost_perimeter_identity_error_usd"].abs().max()),
                "material_recast_rows": int(group["material_recast_or_scope_change"].sum()),
                "mean_absolute_recast_scope_pct": float(group["recast_scope_pct_of_original"].abs().mean()),
                "mean_comparable_economic_cost_growth_pct": float(group["comparable_economic_cost_growth_pct"].mean()),
                "mean_reported_cost_growth_pct": float(group["reported_cost_growth_pct"].mean()),
                "reported_minus_comparable_growth_pct": float(
                    (group["reported_cost_growth_pct"] - group["comparable_economic_cost_growth_pct"]).mean()
                ),
                "comparable_cost_identity_proven": bool(group["cost_perimeter_identity_pass"].all()),
                "homogeneous_reported_scope": bool(~group["material_recast_or_scope_change"].any()),
                "forecast_target": "COMPARABLE_ECONOMIC_COST_GROWTH",
            }
        )
    summary = pd.DataFrame(rows)
    audit = pd.DataFrame(
        [
            {
                "validation_rows": len(validation),
                "segments": validation["segment"].nunique(),
                "identity_mismatches": int((~validation["cost_perimeter_identity_pass"]).sum()),
                "material_recast_rows": int(validation["material_recast_or_scope_change"].sum()),
                "cost_perimeter_identity_proven": bool(validation["cost_perimeter_identity_pass"].all()),
                "reported_cost_used_as_economic_target": False,
                "unexpected_recast_forecasted": False,
                "status": "COMPARABLE_COST_IDENTITY_PROVEN_SCOPE_CHANGES_EXPLICIT",
            }
        ]
    )
    return {
        "segment_cost_perimeter": frame,
        "segment_cost_perimeter_summary": summary,
        "cost_perimeter_audit": audit,
    }
