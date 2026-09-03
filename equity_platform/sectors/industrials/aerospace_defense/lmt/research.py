from __future__ import annotations

import pandas as pd

from equity_platform.core.gates import GateCheck, evaluate_gate_checks
from equity_platform.core.target_authority import apply_standard_target_authority


def build_lmt_research_gates(*, source_summary: pd.DataFrame, ir_summary: pd.DataFrame, industry_summary: pd.DataFrame, portability_summary: pd.DataFrame, portability_coverage: pd.DataFrame, reinvestment_summary: pd.DataFrame, segment_reconciliation_summary: pd.DataFrame, uncertainty_gate: pd.DataFrame, bridge_summary: pd.DataFrame, expected_oos_quarters_per_segment: int, minimum_research_champions: int, production_minimum_live_observations: int) -> dict[str, pd.DataFrame]:
    source_pass = bool(source_summary.iloc[0]["source_gate_pass"])
    parser_pass = bool(ir_summary.iloc[0]["parser_gate_pass"])
    industry_pass = bool(industry_summary.iloc[0]["historical_pit_ready"])
    fixed_oos = bool(portability_summary["validation_observations"].eq(expected_oos_quarters_per_segment).all() and portability_coverage.iloc[0]["cutoff_violations"] == 0)
    boundary_pass = bool(not portability_coverage.iloc[0]["all_rows_at_margin_boundary"])
    revenue_champions = int(portability_summary["revenue_champion_eligible"].sum())
    margin_champions = int(portability_summary["margin_champion_eligible"].sum())
    joint_champions = int(portability_summary["joint_champion"].sum())
    note_pass = bool(reinvestment_summary.iloc[0]["research_evidence_ready"])
    reconciliation = segment_reconciliation_summary.iloc[0]
    reconciliation_pass = bool(reconciliation["segment_and_backlog_reconciliation_gate_pass"])
    program_loss_pass = bool(reconciliation["program_loss_no_overallocation_gate_pass"])
    research_freeze, failed = evaluate_gate_checks([
        GateCheck("SEC_IR_SOURCE_COMPLETENESS", source_pass), GateCheck("LMT_IR_PARSER", parser_pass),
        GateCheck("HISTORICAL_PIT_INDUSTRY_DATA", industry_pass), GateCheck("FIXED_SIX_QUARTER_OOS", fixed_oos),
        GateCheck("MARGIN_BOUNDARY_SATURATION", boundary_pass),
        GateCheck("PORTABILITY_POINT_PERFORMANCE", joint_champions >= minimum_research_champions),
        GateCheck("REINVESTMENT_ROIC_NOTE_EVIDENCE", note_pass),
        GateCheck("SEC_IR_SEGMENT_AND_BACKLOG_RECONCILIATION", reconciliation_pass),
        GateCheck("SEC_IR_PROGRAM_LOSS_NO_OVERALLOCATION", program_loss_pass),
    ])
    gate = pd.DataFrame([{
        "version": "INDUSTRIALS_PLATFORM_V3_LMT_AEROSPACE_DEFENSE_RESEARCH", "cmi_v2_parent_unchanged": True,
        "source_gate_pass": source_pass, "ir_parser_gate_pass": parser_pass, "historical_pit_industry_gate_pass": industry_pass,
        "fixed_oos_window_pass": fixed_oos, "revenue_champion_segments": revenue_champions, "margin_champion_segments": margin_champions,
        "margin_boundary_saturation_pass": boundary_pass,
        "joint_champion_segments": joint_champions, "minimum_joint_champion_segments": minimum_research_champions,
        "reinvestment_roic_research_ready": note_pass,
        "sec_ir_segment_reconciliation_pass": reconciliation_pass,
        "sec_ir_segment_identity_pass_cells": int(reconciliation["sec_ir_segment_identity_pass_cells"]),
        "sec_ir_segment_identity_expected_cells": int(reconciliation["expected_segment_metric_cells"]),
        "sec_rpo_ir_backlog_identity_pass_periods": int(reconciliation["rpo_backlog_identity_pass_periods"]),
        "sec_rpo_ir_backlog_expected_periods": int(reconciliation["rpo_backlog_periods"]),
        "program_loss_no_overallocation_pass": program_loss_pass,
        "program_loss_unallocated_residual_usd": float(reconciliation["program_loss_unallocated_residual_usd"]),
        "conditional_financial_bridge_periods": int(bridge_summary.iloc[0]["financial_bridge_claim_periods"]),
        "uncertainty_champion_targets": int(uncertainty_gate.iloc[0]["uncertainty_champions"]), "research_freeze_eligible": research_freeze,
        "terminal_gate_pass": False, "production_gate_pass": False, "live_matched_observations": f"0/{production_minimum_live_observations}",
        "new_dcf_run": False, "new_reverse_dcf_run": False, "pdf_parsing_deferred": True,
        "status": "FREEZE_ELIGIBLE_NOT_FROZEN" if research_freeze else "HOLD_RESEARCH_UNFROZEN", "failed_conditions": failed,
    }])
    authority = portability_summary[[
        "segment", "revenue_route", "structural_anchor_coverage_pct", "delivery_anchor_coverage_pct", "revenue_mase",
        "revenue_champion_eligible", "margin_route", "margin_mase", "margin_champion_eligible", "joint_champion",
        "scope_change_rows", "program_loss_rows", "margin_boundary_hits", "margin_boundary_hit_pct",
    ]].copy()
    authority = apply_standard_target_authority(
        authority,
        route_column="revenue_route",
        champion_column="revenue_champion_eligible",
        structural_anchor_coverage_column="structural_anchor_coverage_pct",
    )
    valuation = pd.DataFrame([{
        "lmt_dcf_value_per_share_usd": pd.NA, "lmt_reverse_dcf_result": "NOT_RUN_BY_DESIGN",
        "reason": "AEROSPACE_PORTABILITY_RESEARCH_REQUIRES_SEPARATE_UNCERTAINTY_TERMINAL_AND_LIVE_GATES",
        "research_financial_bridge_available": True, "terminal_input_allowed": False, "production_promotable": False,
    }])
    return {"industrials_v3_lmt_gate": gate, "lmt_target_route_authority": authority, "industrials_v3_lmt_valuation_authority": valuation}
