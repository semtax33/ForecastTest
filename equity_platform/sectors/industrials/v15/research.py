from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator and np.isfinite(denominator) else np.nan


def _validation_summary(
    validation: pd.DataFrame,
    *,
    v14_components: pd.DataFrame,
    maximum_revenue_regression_pct: float,
    cancellation_ratio_threshold: float,
    component_gross_mae_threshold_pct: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    segment_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    for segment, group in validation.groupby("segment"):
        margin_mae = float((group["actual_margin_pct"] - group["predicted_margin_pct"]).abs().mean())
        naive_margin_mae = float((group["actual_margin_pct"] - group["prior_margin_pct"]).abs().mean())
        revenue_mae = float((group["actual_sales_usd"] - group["predicted_sales_usd"]).abs().mean())
        naive_revenue_mae = float((group["actual_sales_usd"] - group["naive_prior_year_sales_usd"]).abs().mean())
        gross_component_mae = float(group["gross_component_absolute_error_pct"].mean())
        cancellation_ratio = float(group["component_cancellation_ratio"].mean())
        margin_mase = _safe_ratio(margin_mae, naive_margin_mae)
        revenue_regression = (_safe_ratio(revenue_mae, naive_revenue_mae) - 1.0) * 100.0
        cancellation_lock = bool(
            margin_mase < 1.0
            and cancellation_ratio > cancellation_ratio_threshold
            and gross_component_mae > component_gross_mae_threshold_pct
        )
        routes = group["selected_volume_route"].value_counts()
        segment_rows.append(
            {
                "segment": segment,
                "validation_observations": len(group),
                "first_validation_period": group["period"].min(),
                "last_validation_period": group["period"].max(),
                "champion_volume_route": routes.index[0],
                "champion_route_selection_share_pct": float(routes.iloc[0] / len(group) * 100.0),
                "margin_mae_pct_points": margin_mae,
                "prior_margin_mae_pct_points": naive_margin_mae,
                "margin_mase_vs_prior": margin_mase,
                "revenue_level_mae_usd": revenue_mae,
                "naive_prior_year_revenue_mae_usd": naive_revenue_mae,
                "revenue_mae_regression_vs_naive_pct": revenue_regression,
                "revenue_no_material_regression": bool(revenue_regression <= maximum_revenue_regression_pct),
                "mean_revenue_level_ape_pct": float(group["revenue_level_ape_pct"].mean()),
                "gross_component_mae_pct": gross_component_mae,
                "mean_component_cancellation_ratio": cancellation_ratio,
                "component_cancellation_lock": cancellation_lock,
                "historical_pit_input_pct": float(group["historical_pit_input"].mean() * 100.0),
                "actual_after_forecast_pct": float(group["actual_after_forecast"].mean() * 100.0),
                "performance_claim_allowed": bool(group["historical_pit_input"].all() and group["actual_after_forecast"].all()),
            }
        )
        for component, actual, predicted in [
            ("VOLUME", "actual_volume_contribution_pct", "predicted_volume_contribution_pct"),
            ("PRICE", "actual_price_contribution_pct", "predicted_price_contribution_pct"),
            ("COST", "actual_cost_growth_pct", "predicted_cost_growth_pct"),
        ]:
            mae = float((group[actual] - group[predicted]).abs().mean())
            prior_row = v14_components.loc[
                v14_components["segment"].eq(segment) & v14_components["component"].eq(component)
            ]
            prior_mae = float(prior_row.iloc[0]["mae_pct"]) if not prior_row.empty else np.nan
            component_rows.append(
                {
                    "segment": segment,
                    "component": component,
                    "validation_observations": len(group),
                    "v1_5_historical_pit_mae_pct": mae,
                    "v1_4_calibration_mae_pct": prior_mae,
                    "mae_change_vs_v1_4_pct": (mae / prior_mae - 1.0) * 100.0 if prior_mae else np.nan,
                    "actual_mean_pct": float(group[actual].mean()),
                    "predicted_mean_pct": float(group[predicted].mean()),
                    "historical_pit_input": bool(group["historical_pit_input"].all()),
                }
            )
    return pd.DataFrame(segment_rows), pd.DataFrame(component_rows)


def _full_chain_reinvestment_validation(
    validation: pd.DataFrame,
    annual_history: pd.DataFrame,
    minimum_observations: int,
    maximum_mase: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = validation.copy()
    frame["fiscal_year"] = frame["period"].str[:4].astype(int)
    annual = annual_history.sort_values("fiscal_year").reset_index(drop=True).copy()
    annual["actual_delta_invested_capital_usd"] = annual["mpe_invested_capital_usd"].diff()
    rows: list[dict[str, object]] = []
    for fiscal_year, group in frame.groupby("fiscal_year"):
        if group["period"].nunique() != 4 or len(group) != 12:
            continue
        current = annual.loc[annual["fiscal_year"].eq(fiscal_year)]
        prior = annual.loc[annual["fiscal_year"].eq(fiscal_year - 1)]
        training = annual.loc[annual["fiscal_year"].lt(fiscal_year)].copy()
        if current.empty or prior.empty or len(training) < 2:
            continue
        current_row = current.iloc[0]
        prior_row = prior.iloc[0]
        sales_to_capital = float((training["mpe_total_revenue_usd"] / training["mpe_invested_capital_usd"]).median())
        prior_core_sales = float(group["naive_prior_year_sales_usd"].sum())
        core_to_mpe_scale = float(prior_row["mpe_total_revenue_usd"] / prior_core_sales)
        predicted_core_sales = float(group["predicted_sales_usd"].sum())
        actual_core_sales = float(group["actual_sales_usd"].sum())
        predicted_mpe_revenue = predicted_core_sales * core_to_mpe_scale
        predicted_reinvestment = (predicted_mpe_revenue - float(prior_row["mpe_total_revenue_usd"])) / sales_to_capital
        actual_reinvestment = float(current_row["actual_delta_invested_capital_usd"])
        prior_deltas = training["actual_delta_invested_capital_usd"].dropna()
        naive_reinvestment = float(prior_deltas.iloc[-1]) if not prior_deltas.empty else np.nan
        tax_rate = float(training["mpe_effective_tax_rate_pct"].median())
        predicted_core_ebit = float((group["predicted_sales_usd"] - group["bridge_predicted_cost_usd"]).sum())
        actual_core_ebit = float((group["actual_sales_usd"] - group["actual_cost_usd"]).sum())
        rows.append(
            {
                "fiscal_year": fiscal_year,
                "forecast_quarter_rows": len(group),
                "training_annual_years": len(training),
                "predicted_core_revenue_usd": predicted_core_sales,
                "actual_core_revenue_usd": actual_core_sales,
                "core_revenue_ape_pct": abs(predicted_core_sales / actual_core_sales - 1.0) * 100.0,
                "predicted_core_ebit_usd": predicted_core_ebit,
                "actual_core_ebit_usd": actual_core_ebit,
                "predicted_core_nopat_usd": predicted_core_ebit * (1.0 - tax_rate / 100.0),
                "actual_core_nopat_usd": actual_core_ebit * (1.0 - tax_rate / 100.0),
                "prior_core_to_mpe_revenue_scale": core_to_mpe_scale,
                "predicted_mpe_revenue_usd": predicted_mpe_revenue,
                "prior_median_sales_to_capital": sales_to_capital,
                "predicted_reinvestment_usd": predicted_reinvestment,
                "actual_delta_invested_capital_usd": actual_reinvestment,
                "naive_prior_delta_invested_capital_usd": naive_reinvestment,
                "absolute_error_usd": abs(predicted_reinvestment - actual_reinvestment),
                "naive_absolute_error_usd": abs(naive_reinvestment - actual_reinvestment),
                "pipeline": "PIT_INDUSTRY_SENSORS_TO_SEGMENT_ROUTES_TO_MARGIN_TO_NOPAT_TO_REINVESTMENT",
                "perimeter_status": "CORE_SEGMENTS_SCALED_TO_MPE_USING_PRIOR_YEAR_REPORTED_RATIO",
                "historical_pit_input": bool(group["historical_pit_input"].all()),
                "performance_claim_allowed": bool(group["historical_pit_input"].all()),
            }
        )
    result = pd.DataFrame(rows)
    model_mae = float(result["absolute_error_usd"].mean()) if not result.empty else np.nan
    naive_mae = float(result["naive_absolute_error_usd"].mean()) if not result.empty else np.nan
    mase = _safe_ratio(model_mae, naive_mae)
    enough = len(result) >= minimum_observations
    beat_naive = bool(np.isfinite(mase) and mase < maximum_mase)
    validated = bool(enough and beat_naive and not result.empty and result["historical_pit_input"].all())
    failed: list[str] = []
    if not enough:
        failed.append("INSUFFICIENT_PIT_OOS_YEARS")
    if not beat_naive:
        failed.append("REINVESTMENT_MASE_NOT_BELOW_ONE")
    summary = pd.DataFrame(
        [
            {
                "validation_observations": len(result),
                "minimum_observations_required": minimum_observations,
                "minimum_observations_met": enough,
                "full_chain_model_mae_usd": model_mae,
                "naive_prior_delta_mae_usd": naive_mae,
                "full_chain_reinvestment_mase": mase,
                "maximum_reinvestment_mase": maximum_mase,
                "upstream_forecast_errors_propagated": True,
                "historical_pit_vintages_available": bool(not result.empty and result["historical_pit_input"].all()),
                "perimeter_exact": False,
                "full_forecast_oos_validated": validated,
                "reinvestment_bridge_validated": validated,
                "failed_gates": "|".join(failed),
                "status": "PIT_OOS_VALIDATED" if validated else "FAIL_CLOSED_PIT_OOS_GATE",
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return result, summary


def build_v15_research(
    *,
    validation: pd.DataFrame,
    v14_components: pd.DataFrame,
    annual_history: pd.DataFrame,
    pit_archive_audit: pd.DataFrame,
    pit_feature_summary: pd.DataFrame,
    parent_architecture_verified: bool,
    minimum_segments_below_one: int,
    worst_segment_margin_mase: float,
    maximum_revenue_regression_pct: float,
    cancellation_ratio_threshold: float,
    component_gross_mae_threshold_pct: float,
    minimum_reinvestment_oos_years: int,
    maximum_reinvestment_mase: float,
) -> dict[str, pd.DataFrame]:
    summary, components = _validation_summary(
        validation,
        v14_components=v14_components,
        maximum_revenue_regression_pct=maximum_revenue_regression_pct,
        cancellation_ratio_threshold=cancellation_ratio_threshold,
        component_gross_mae_threshold_pct=component_gross_mae_threshold_pct,
    )
    reinvestment, reinvestment_summary = _full_chain_reinvestment_validation(
        validation,
        annual_history,
        minimum_reinvestment_oos_years,
        maximum_reinvestment_mase,
    )
    segments_below_one = int(summary["margin_mase_vs_prior"].lt(1.0).sum())
    no_worst_regression = bool(summary["margin_mase_vs_prior"].lt(worst_segment_margin_mase).all())
    revenue_gate = bool(summary["revenue_no_material_regression"].all())
    cancellation_gate = bool(~summary["component_cancellation_lock"].any())
    archive_ready = bool(pit_archive_audit.iloc[0]["historical_pit_ready"])
    features_ready = bool(pit_feature_summary.iloc[0]["historical_pit_ready"])
    validation_ready = bool(summary["performance_claim_allowed"].all())
    reinvestment_ready = bool(reinvestment_summary.iloc[0]["reinvestment_bridge_validated"])
    backlog_ready = False
    terminal_locked = True
    production_ready = False
    freeze_ready = bool(
        parent_architecture_verified
        and archive_ready
        and features_ready
        and validation_ready
        and segments_below_one >= minimum_segments_below_one
        and no_worst_regression
        and revenue_gate
        and cancellation_gate
        and reinvestment_ready
        and backlog_ready
        and not terminal_locked
        and production_ready
    )
    failed: list[str] = []
    checks = [
        (archive_ready and features_ready and validation_ready, "HISTORICAL_PIT"),
        (segments_below_one >= minimum_segments_below_one, "MARGIN_MASE_SEGMENT_COUNT"),
        (no_worst_regression, "WORST_SEGMENT_MARGIN_MASE"),
        (revenue_gate, "SEGMENT_REVENUE_REGRESSION"),
        (cancellation_gate, "COMPONENT_ERROR_CANCELLATION"),
        (reinvestment_ready, "REINVESTMENT_PIT_OOS"),
        (backlog_ready, "BACKLOG_OOS"),
        (not terminal_locked, "TERMINAL_UNLOCK"),
        (production_ready, "PRODUCTION_LIVE_FORWARD"),
    ]
    failed.extend(name for passed, name in checks if not passed)
    freeze = pd.DataFrame(
        [
            {
                "historical_pit_archive_ready": archive_ready,
                "historical_pit_features_ready": features_ready,
                "historical_pit_validation_ready": validation_ready,
                "segments_with_margin_mase_below_one": segments_below_one,
                "minimum_segments_required": minimum_segments_below_one,
                "maximum_segment_margin_mase": float(summary["margin_mase_vs_prior"].max()),
                "worst_segment_margin_mase_threshold": worst_segment_margin_mase,
                "no_worst_segment_margin_regression": no_worst_regression,
                "all_segments_revenue_no_material_regression": revenue_gate,
                "component_cancellation_gate_pass": cancellation_gate,
                "reinvestment_pit_oos_gate_pass": reinvestment_ready,
                "backlog_oos_gate_pass": backlog_ready,
                "terminal_unlocked": not terminal_locked,
                "production_live_forward_gate_pass": production_ready,
                "freeze_ready": freeze_ready,
                "failed_gates": "|".join(failed),
                "status": "RESEARCH_FROZEN" if freeze_ready else "HOLD_RESEARCH_UNFROZEN",
            }
        ]
    )
    gate = pd.DataFrame(
        [
            {
                "parent_v1_2_architecture_verified": parent_architecture_verified,
                "v1_4_original_code_changed": False,
                "official_bls_historical_vintages_available": archive_ready,
                "cat_retail_ir_historical_vintages_available": True,
                "segment_route_selection_independent": True,
                "component_cancellation_audited": True,
                "historical_pit_performance_claim_allowed": validation_ready,
                "freeze_gate_pass": freeze_ready,
                "reinvestment_full_chain_observations": int(reinvestment_summary.iloc[0]["validation_observations"]),
                "backlog_oos_observations": 2,
                "valuation_update_allowed": False,
                "pdf_parsing_deferred": True,
                "research_complete": bool(parent_architecture_verified and archive_ready and features_ready and validation_ready),
                "terminal_input_allowed": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
    valuation = pd.DataFrame(
        [
            {
                "valuation_update_allowed": False,
                "reason": "V1_5_FREEZE_GATE_FAILED_AND_TERMINAL_ECONOMICS_REMAIN_LOCKED",
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
        "segment_route_validation_summary": summary,
        "segment_component_pit_validation_summary": components,
        "reinvestment_pit_full_chain_walk_forward": reinvestment,
        "reinvestment_pit_full_chain_summary": reinvestment_summary,
        "v1_5_freeze_readiness": freeze,
        "industrials_v1_5_gate": gate,
        "v1_5_valuation_authority": valuation,
    }
