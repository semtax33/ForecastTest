from __future__ import annotations

import numpy as np
import pandas as pd

from .revenue import build_revenue_champion_validation


def _margin_summary(
    validation: pd.DataFrame,
    *,
    cancellation_ratio_threshold: float,
    component_gross_mae_threshold_pct: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for segment, group in validation.groupby("segment"):
        model_mae = float((group["actual_margin_pct"] - group["predicted_margin_pct"]).abs().mean())
        naive_mae = float((group["actual_margin_pct"] - group["prior_margin_pct"]).abs().mean())
        v15_mae = float((group["actual_margin_pct"] - group["v1_5_predicted_margin_pct"]).abs().mean())
        mase = model_mae / naive_mae if naive_mae else np.nan
        cancellation = float(group["component_cancellation_ratio"].mean())
        gross_error = float(group["reported_component_gross_error_pct"].mean())
        cancellation_lock = bool(
            mase < 1.0
            and cancellation > cancellation_ratio_threshold
            and gross_error > component_gross_mae_threshold_pct
        )
        perimeter_lock = bool(group["material_recast_or_scope_change"].any() and not group["unexpected_recast_forecasted"].any())
        rows.append(
            {
                "segment": segment,
                "validation_observations": len(group),
                "margin_mae_pct_points": model_mae,
                "prior_margin_mae_pct_points": naive_mae,
                "margin_mase_vs_prior": mase,
                "v1_5_margin_mae_pct_points": v15_mae,
                "margin_mae_change_vs_v1_5_pct": (model_mae / v15_mae - 1.0) * 100.0 if v15_mae else np.nan,
                "mean_reported_component_gross_error_pct": gross_error,
                "mean_component_cancellation_ratio": cancellation,
                "component_cancellation_lock": cancellation_lock,
                "material_recast_rows": int(group["material_recast_or_scope_change"].sum()),
                "cost_perimeter_uncertainty_lock": perimeter_lock,
                "margin_statistical_pass": bool(mase < 1.0),
                "validated_margin_route": bool(mase < 1.0 and not cancellation_lock and not perimeter_lock),
                "historical_pit_input": bool(group["historical_pit_input"].all()),
            }
        )
    return pd.DataFrame(rows)


def build_v16_research(
    *,
    base_validation: pd.DataFrame,
    timing_validation: pd.DataFrame,
    perimeter_audit: pd.DataFrame,
    pit_benchmark_verified: bool,
    reinvestment_summary: pd.DataFrame,
    expected_oos_quarters_per_segment: int,
    maximum_revenue_mase: float,
    minimum_revenue_direction_accuracy_pct: float,
    minimum_segments_margin_validated: int,
    maximum_margin_mase: float,
    cancellation_ratio_threshold: float,
    component_gross_mae_threshold_pct: float,
    minimum_backlog_oos_observations: int,
    production_minimum_live_observations: int,
) -> dict[str, pd.DataFrame]:
    revenue = build_revenue_champion_validation(
        base_validation,
        maximum_mase=maximum_revenue_mase,
        minimum_direction_accuracy_pct=minimum_revenue_direction_accuracy_pct,
    )
    margin = _margin_summary(
        timing_validation,
        cancellation_ratio_threshold=cancellation_ratio_threshold,
        component_gross_mae_threshold_pct=component_gross_mae_threshold_pct,
    )
    fixed_oos = bool(
        base_validation.groupby("segment").size().eq(expected_oos_quarters_per_segment).all()
        and timing_validation.groupby("segment").size().eq(expected_oos_quarters_per_segment).all()
    )
    revenue_ready = bool(revenue["revenue_champion_eligible"].all())
    validated_margin_segments = int(margin["validated_margin_route"].sum())
    worst_margin_pass = bool(margin["margin_mase_vs_prior"].lt(maximum_margin_mase).all())
    perimeter_identity = bool(perimeter_audit.iloc[0]["cost_perimeter_identity_proven"])
    research_freeze_eligible = bool(
        pit_benchmark_verified
        and fixed_oos
        and revenue_ready
        and validated_margin_segments >= minimum_segments_margin_validated
        and worst_margin_pass
        and perimeter_identity
    )
    reinvestment_ready = bool(reinvestment_summary.iloc[0]["reinvestment_bridge_validated"])
    backlog_oos_observations = 2
    backlog_ready = backlog_oos_observations >= minimum_backlog_oos_observations
    terminal_evidence_eligible = bool(research_freeze_eligible and reinvestment_ready and backlog_ready)
    live_observations = 0
    production_promotable = bool(research_freeze_eligible and live_observations >= production_minimum_live_observations)

    research_failed: list[str] = []
    for passed, label in [
        (pit_benchmark_verified, "PIT_DATA_BENCHMARK"),
        (fixed_oos, "FIXED_SIX_QUARTER_OOS"),
        (revenue_ready, "REVENUE_CHAMPION"),
        (validated_margin_segments >= minimum_segments_margin_validated, "VALIDATED_MARGIN_ROUTE_COUNT"),
        (worst_margin_pass, "WORST_MARGIN_MASE"),
        (perimeter_identity, "COST_PERIMETER_IDENTITY"),
    ]:
        if not passed:
            research_failed.append(label)

    gate_layers = pd.DataFrame(
        [
            {
                "gate": "RESEARCH_FREEZE_ELIGIBLE",
                "eligible": research_freeze_eligible,
                "failed_conditions": "|".join(research_failed),
                "independent_of_terminal_and_production": True,
                "status": "ELIGIBLE" if research_freeze_eligible else "HOLD_RESEARCH_UNFROZEN",
            },
            {
                "gate": "TERMINAL_EVIDENCE_ELIGIBLE",
                "eligible": terminal_evidence_eligible,
                "failed_conditions": "" if terminal_evidence_eligible else "RESEARCH_FREEZE|REINVESTMENT_N_GE_3|BACKLOG_OOS_N_GE_3",
                "independent_of_terminal_and_production": False,
                "status": "ELIGIBLE" if terminal_evidence_eligible else "TERMINAL_LOCKED",
            },
            {
                "gate": "PRODUCTION_PROMOTABLE",
                "eligible": production_promotable,
                "failed_conditions": "" if production_promotable else "RESEARCH_FREEZE|LIVE_FORWARD_20_OF_20",
                "independent_of_terminal_and_production": False,
                "status": "PROMOTABLE" if production_promotable else "PRODUCTION_LOCKED",
            },
        ]
    )
    gate = pd.DataFrame(
        [
            {
                "v1_5_pit_data_benchmark_verified": pit_benchmark_verified,
                "forecast_model_parent_frozen": False,
                "fixed_oos_window_unchanged": fixed_oos,
                "oos_quarters_per_segment": expected_oos_quarters_per_segment,
                "revenue_champion_segments": int(revenue["revenue_champion_eligible"].sum()),
                "validated_margin_segments": validated_margin_segments,
                "minimum_validated_margin_segments": minimum_segments_margin_validated,
                "maximum_segment_margin_mase": float(margin["margin_mase_vs_prior"].max()),
                "cost_perimeter_identity_proven": perimeter_identity,
                "research_freeze_eligible": research_freeze_eligible,
                "reinvestment_evidence_observations": int(reinvestment_summary.iloc[0]["validation_observations"]),
                "reinvestment_evidence_gate_pass": reinvestment_ready,
                "backlog_oos_observations": backlog_oos_observations,
                "backlog_evidence_gate_pass": backlog_ready,
                "terminal_evidence_eligible": terminal_evidence_eligible,
                "live_matched_observations": f"{live_observations}/{production_minimum_live_observations}",
                "production_promotable": production_promotable,
                "valuation_update_allowed": False,
                "pdf_parsing_deferred": True,
                "research_complete": True,
                "status": "RESEARCH_FROZEN" if research_freeze_eligible else "HOLD_RESEARCH_UNFROZEN",
            }
        ]
    )
    authority = pd.DataFrame(
        [
            {
                "valuation_update_allowed": False,
                "terminal_evidence_eligible": terminal_evidence_eligible,
                "reason": "TERMINAL_EVIDENCE_GATE_FAILED",
                "v1_3_lite_reference_preserved": True,
                "reference_value_per_share_usd": 399.1175,
                "new_dcf_value_per_share": np.nan,
                "new_reverse_dcf_result": "NOT_RUN_BY_DESIGN",
                "roic_reestimate_allowed": False,
                "terminal_replacement_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return {
        "revenue_champion_validation": revenue,
        "margin_route_validation": margin,
        "v1_6_gate_layers": gate_layers,
        "industrials_v1_6_gate": gate,
        "v1_6_valuation_authority": authority,
    }
