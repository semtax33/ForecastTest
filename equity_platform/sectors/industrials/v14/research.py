from __future__ import annotations

import numpy as np
import pandas as pd


def _full_chain_reinvestment_validation(
    margin_walk_forward: pd.DataFrame,
    annual_history: pd.DataFrame,
    minimum_observations: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    validation = margin_walk_forward.copy()
    validation["fiscal_year"] = validation["period"].str[:4].astype(int)
    annual = annual_history.sort_values("fiscal_year").reset_index(drop=True).copy()
    annual["actual_delta_invested_capital_usd"] = annual["mpe_invested_capital_usd"].diff()
    rows: list[dict[str, object]] = []
    for fiscal_year, group in validation.groupby("fiscal_year"):
        if group["period"].nunique() != 4 or len(group) != 12:
            continue
        current = annual.loc[annual["fiscal_year"].eq(fiscal_year)]
        prior_year = annual.loc[annual["fiscal_year"].eq(fiscal_year - 1)]
        training = annual.loc[annual["fiscal_year"].lt(fiscal_year)].copy()
        if current.empty or prior_year.empty or len(training) < 2:
            continue
        current_row = current.iloc[0]
        prior_row = prior_year.iloc[0]
        sales_to_capital = float((training["mpe_total_revenue_usd"] / training["mpe_invested_capital_usd"]).median())
        prior_core_sales = float(group["comparable_prior_sales_usd"].sum())
        core_to_mpe_scale = float(prior_row["mpe_total_revenue_usd"] / prior_core_sales)
        predicted_core_sales = float(group["predicted_sales_usd"].sum())
        actual_core_sales = float(group["actual_sales_usd"].sum())
        predicted_mpe_revenue = predicted_core_sales * core_to_mpe_scale
        predicted_reinvestment = (predicted_mpe_revenue - float(prior_row["mpe_total_revenue_usd"])) / sales_to_capital
        actual_reinvestment = float(current_row["actual_delta_invested_capital_usd"])
        prior_deltas = training["actual_delta_invested_capital_usd"].dropna()
        naive_reinvestment = float(prior_deltas.iloc[-1]) if not prior_deltas.empty else np.nan
        predicted_core_ebit = float((group["predicted_sales_usd"] - group["bridge_predicted_cost_usd"]).sum())
        actual_core_ebit = float((group["actual_sales_usd"] - group["actual_cost_usd"]).sum())
        tax_rate = float(training["mpe_effective_tax_rate_pct"].median())
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
                "pipeline": "INDUSTRY_SENSORS_TO_PQ_TO_MARGIN_TO_NOPAT_TO_REINVESTMENT",
                "perimeter_status": "CORE_SEGMENTS_SCALED_TO_MPE_USING_PRIOR_YEAR_REPORTED_RATIO",
                "historical_pit_input": False,
                "performance_claim_allowed": False,
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        model_mae = naive_mae = mase = np.nan
    else:
        model_mae = float(result["absolute_error_usd"].mean())
        naive_mae = float(result["naive_absolute_error_usd"].mean())
        mase = model_mae / naive_mae if naive_mae else np.nan
    summary = pd.DataFrame(
        [
            {
                "validation_observations": len(result),
                "minimum_observations_required": minimum_observations,
                "minimum_observations_met": len(result) >= minimum_observations,
                "full_chain_model_mae_usd": model_mae,
                "naive_prior_delta_mae_usd": naive_mae,
                "full_chain_reinvestment_mase": mase,
                "upstream_forecast_errors_propagated": True,
                "historical_pit_vintages_available": False,
                "perimeter_exact": False,
                "full_forecast_oos_validated": False,
                "reinvestment_bridge_validated": False,
                "status": "FAIL_CLOSED_INSUFFICIENT_NON_PIT_FULL_CHAIN_OBSERVATIONS",
                "terminal_input_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return result, summary


def _freeze_readiness(
    margin_summary: pd.DataFrame,
    *,
    minimum_segments_below_one: int,
    catastrophic_margin_mase: float,
    minimum_capture_improvement_pct: float,
) -> pd.DataFrame:
    mase = margin_summary["margin_mase_vs_prior"]
    improvements = margin_summary["revenue_mae_improvement_vs_unit_pct"]
    segments_below_one = int(mase.lt(1.0).sum())
    no_catastrophic = bool(mase.lt(catastrophic_margin_mase).all())
    capture_improved = bool(improvements.median() > minimum_capture_improvement_pct)
    pit_resolved_or_explicit = True
    ready = bool(
        segments_below_one >= minimum_segments_below_one
        and no_catastrophic
        and capture_improved
        and pit_resolved_or_explicit
    )
    failed = []
    if segments_below_one < minimum_segments_below_one:
        failed.append("MARGIN_MASE_SEGMENT_COUNT")
    if not no_catastrophic:
        failed.append("CATASTROPHIC_SEGMENT_REGRESSION")
    if not capture_improved:
        failed.append("CAPTURE_NOT_IMPROVED_VS_UNIT")
    return pd.DataFrame(
        [
            {
                "segments_with_margin_mase_below_one": segments_below_one,
                "minimum_segments_required": minimum_segments_below_one,
                "maximum_segment_margin_mase": float(mase.max()),
                "catastrophic_margin_mase_threshold": catastrophic_margin_mase,
                "no_catastrophic_segment_regression": no_catastrophic,
                "median_revenue_capture_improvement_vs_unit_pct": float(improvements.median()),
                "minimum_capture_improvement_pct": minimum_capture_improvement_pct,
                "capture_improved_vs_unit": capture_improved,
                "historical_pit_resolved": False,
                "explicit_calibration_only_disposition": pit_resolved_or_explicit,
                "v1_3_lite_freeze_ready": ready,
                "failed_gates": "|".join(failed),
                "status": "FREEZE_READY_CALIBRATION_ONLY" if ready else "HOLD_RESEARCH_UNFROZEN",
            }
        ]
    )


def build_v14_research(
    *,
    margin_results: dict[str, pd.DataFrame],
    pq_results: dict[str, pd.DataFrame],
    vintage_results: dict[str, pd.DataFrame],
    annual_history: pd.DataFrame,
    parent_architecture_verified: bool,
    minimum_validation_observations: int,
    minimum_segments_below_one: int,
    catastrophic_margin_mase: float,
    minimum_capture_improvement_pct: float,
) -> dict[str, pd.DataFrame]:
    full_chain, full_chain_summary = _full_chain_reinvestment_validation(
        margin_results["segment_margin_walk_forward"], annual_history, minimum_validation_observations
    )
    freeze = _freeze_readiness(
        margin_results["segment_margin_validation_summary"],
        minimum_segments_below_one=minimum_segments_below_one,
        catastrophic_margin_mase=catastrophic_margin_mase,
        minimum_capture_improvement_pct=minimum_capture_improvement_pct,
    )
    freeze_row = freeze.iloc[0]
    pq_pass = bool(pq_results["ir_segment_pq_summary"].iloc[0]["pq_bridge_gate_pass"])
    schema_pass = bool(vintage_results["pit_vintage_schema_audit"].iloc[0]["schema_columns_complete"])
    gate = pd.DataFrame(
        [
            {
                "parent_v1_2_architecture_verified": parent_architecture_verified,
                "v1_3_lite_original_code_changed": False,
                "dedicated_segment_sensor_roles_complete": True,
                "ir_pq_bridge_gate_pass": pq_pass,
                "pit_canonical_schema_ready": schema_pass,
                "historical_pit_vintages_available": False,
                "explicit_calibration_only": True,
                "margin_freeze_gate_pass": bool(freeze_row["v1_3_lite_freeze_ready"]),
                "reinvestment_full_chain_observations": int(full_chain_summary.iloc[0]["validation_observations"]),
                "reinvestment_bridge_validated": False,
                "roic_model_changed": False,
                "valuation_update_allowed": False,
                "backlog_model_changed": False,
                "backlog_oos_observations": 2,
                "pdf_parsing_deferred": True,
                "research_complete": bool(parent_architecture_verified and pq_pass and schema_pass),
                "terminal_input_allowed": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
    valuation_authority = pd.DataFrame(
        [
            {
                "valuation_update_allowed": False,
                "reason": "MARGIN_BRANCH_REMAINS_CALIBRATION_ONLY_AND_TERMINAL_INPUT_IS_LOCKED",
                "v1_3_lite_reference_preserved": True,
                "new_dcf_value_per_share": np.nan,
                "new_reverse_dcf_result": "NOT_RUN_BY_DESIGN",
                "roic_reestimate_allowed": False,
                "terminal_replacement_allowed": False,
                "production_eligible": False,
            }
        ]
    )
    return {
        "v1_3_lite_freeze_readiness": freeze,
        "reinvestment_full_chain_walk_forward": full_chain,
        "reinvestment_full_chain_summary": full_chain_summary,
        "v1_4_valuation_authority": valuation_authority,
        "industrials_v1_4_gate": gate,
    }
