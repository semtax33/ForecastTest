from __future__ import annotations

import numpy as np
import pandas as pd


def build_v17_gate(
    *,
    source_summary: pd.DataFrame,
    margin_summary: pd.DataFrame,
    margin_walk_forward: pd.DataFrame,
    profit_driver_summary: pd.DataFrame,
    application_mix_summary: pd.DataFrame,
    reinvestment_summary: pd.DataFrame,
    revenue_benchmark_verified: bool,
    minimum_margin_champions: int,
    maximum_worst_margin_mase: float,
    expected_oos_quarters_per_segment: int,
    production_minimum_live_observations: int,
) -> dict[str, pd.DataFrame]:
    source_gate = bool(source_summary.iloc[0]["source_gate_pass"])
    parser_gate = bool(profit_driver_summary["profit_driver_parser_pass"].all())
    mix_gate = bool(application_mix_summary.iloc[0]["product_mix_history_ready"])
    note_gate = bool(reinvestment_summary.iloc[0]["research_evidence_ready"])
    fixed_oos = bool(
        margin_summary["validation_observations"].eq(expected_oos_quarters_per_segment).all()
        and margin_walk_forward.groupby("segment").size().eq(expected_oos_quarters_per_segment).all()
    )
    pit_gate = bool(margin_walk_forward["historical_pit_input"].all() and margin_walk_forward["actual_after_forecast"].all())
    champions = int(margin_summary["margin_champion_eligible"].sum())
    worst_mase = float(margin_summary["selected_margin_mase"].max())
    performance_gate = champions >= minimum_margin_champions and worst_mase < maximum_worst_margin_mase
    research_freeze = bool(
        revenue_benchmark_verified
        and source_gate
        and parser_gate
        and mix_gate
        and note_gate
        and fixed_oos
        and pit_gate
        and performance_gate
    )
    failed: list[str] = []
    checks = [
        (revenue_benchmark_verified, "REVENUE_CHAMPION_PARENT"),
        (source_gate, "SEC_IR_SOURCE_COMPLETENESS"),
        (parser_gate, "PROFIT_DRIVER_PARSER"),
        (mix_gate, "POWER_ENERGY_PRODUCT_MIX"),
        (note_gate, "REINVESTMENT_ROIC_NOTE_EVIDENCE"),
        (fixed_oos, "FIXED_SIX_QUARTER_OOS"),
        (pit_gate, "PIT_CUTOFF"),
        (performance_gate, "MARGIN_PERFORMANCE"),
    ]
    for passed, label in checks:
        if not passed:
            failed.append(label)
    unforecastable = int(margin_walk_forward["unforecastable_scope_change"].sum())
    gate = pd.DataFrame(
        [
            {
                "version": "INDUSTRIALS_CAT_MARGIN_V1_7",
                "revenue_champion_parent_verified": revenue_benchmark_verified,
                "sec_ir_source_gate_pass": source_gate,
                "profit_driver_parser_gate_pass": parser_gate,
                "power_energy_product_mix_gate_pass": mix_gate,
                "reinvestment_roic_note_evidence_ready": note_gate,
                "fixed_oos_window_unchanged": fixed_oos,
                "historical_pit_coverage_pct": float(margin_walk_forward["historical_pit_input"].mean() * 100.0),
                "margin_champion_segments": champions,
                "minimum_margin_champion_segments": minimum_margin_champions,
                "maximum_selected_margin_mase": worst_mase,
                "maximum_allowed_worst_margin_mase": maximum_worst_margin_mase,
                "unforecastable_scope_change_rows": unforecastable,
                "unforecastable_scope_changes_used_as_component_claims": False,
                "research_freeze_eligible": research_freeze,
                "terminal_input_allowed": False,
                "new_dcf_run": False,
                "new_reverse_dcf_run": False,
                "live_matched_observations": f"0/{production_minimum_live_observations}",
                "production_promotable": False,
                "pdf_parsing_deferred": True,
                "status": "RESEARCH_FROZEN" if research_freeze else "HOLD_RESEARCH_UNFROZEN",
                "failed_conditions": "|".join(failed),
            }
        ]
    )
    route_authority = margin_summary[
        ["segment", "predeclared_route", "selected_margin_mase", "margin_champion_eligible", "unforecastable_scope_change_rows"]
    ].copy()
    route_authority["component_attribution_allowed"] = route_authority["predeclared_route"].eq("STRUCTURAL_PROFIT_DRIVER") & route_authority["margin_champion_eligible"]
    route_authority["reduced_form_route"] = route_authority["predeclared_route"].str.startswith("REDUCED_FORM")
    route_authority["roic_attribution_allowed"] = False
    route_authority["terminal_input_allowed"] = False
    route_authority["status"] = np.where(
        route_authority["margin_champion_eligible"],
        "MARGIN_RESEARCH_CHAMPION",
        "RESEARCH_ONLY_NOT_CHAMPION",
    )
    valuation = pd.DataFrame(
        [
            {
                "v1_3_lite_reference_value_per_share_usd": 399.1175,
                "reference_preserved": True,
                "new_dcf_value_per_share_usd": np.nan,
                "new_reverse_dcf_result": "NOT_RUN_BY_DESIGN",
                "reinvestment_bridge_used_in_terminal": False,
                "margin_champion_used_in_terminal": False,
                "reason": "MARGIN_RESEARCH_FREEZE_IS_SEPARATE_FROM_TERMINAL_EVIDENCE_AND_PRODUCTION",
            }
        ]
    )
    return {
        "margin_route_authority": route_authority,
        "industrials_v1_7_gate": gate,
        "v1_7_valuation_authority": valuation,
    }
