from __future__ import annotations

import pandas as pd

from equity_platform.core.gates import GateCheck, evaluate_gate_checks


def build_v2_gates(
    *,
    source_summary: pd.DataFrame,
    ir_summary: pd.DataFrame,
    industry_summary: pd.DataFrame,
    portability_summary: pd.DataFrame,
    portability_coverage: pd.DataFrame,
    reinvestment_summary: pd.DataFrame,
    uncertainty_gate: pd.DataFrame,
    expected_oos_quarters_per_segment: int,
    minimum_research_champions: int,
    production_minimum_live_observations: int,
) -> dict[str, pd.DataFrame]:
    source_pass = bool(source_summary.iloc[0]["source_gate_pass"])
    parser_pass = bool(ir_summary.iloc[0]["parser_gate_pass"])
    industry_pass = bool(industry_summary.iloc[0]["historical_pit_ready"])
    fixed_oos = bool(
        portability_summary["validation_observations"].eq(expected_oos_quarters_per_segment).all()
        and portability_coverage.iloc[0]["cutoff_violations"] == 0
    )
    revenue_champions = int(portability_summary["revenue_champion_eligible"].sum())
    margin_champions = int(portability_summary["margin_champion_eligible"].sum())
    joint_champions = int(portability_summary["joint_champion"].sum())
    performance_pass = joint_champions >= minimum_research_champions
    note_pass = bool(reinvestment_summary.iloc[0]["research_evidence_ready"])
    research_freeze, failed_conditions = evaluate_gate_checks(
        [
            GateCheck("SEC_IR_SOURCE_COMPLETENESS", source_pass),
            GateCheck("CMI_IR_PARSER", parser_pass),
            GateCheck("HISTORICAL_PIT_INDUSTRY_DATA", industry_pass),
            GateCheck("FIXED_SIX_QUARTER_OOS", fixed_oos),
            GateCheck("PORTABILITY_POINT_PERFORMANCE", performance_pass),
            GateCheck("REINVESTMENT_ROIC_NOTE_EVIDENCE", note_pass),
        ]
    )
    gate = pd.DataFrame(
        [
            {
                "version": "INDUSTRIALS_PLATFORM_V2_CMI_PORTABILITY_RESEARCH",
                "cat_v1_7_parent_unchanged": True,
                "source_gate_pass": source_pass,
                "ir_parser_gate_pass": parser_pass,
                "historical_pit_industry_gate_pass": industry_pass,
                "fixed_oos_window_pass": fixed_oos,
                "revenue_champion_segments": revenue_champions,
                "margin_champion_segments": margin_champions,
                "joint_champion_segments": joint_champions,
                "minimum_joint_champion_segments": minimum_research_champions,
                "reinvestment_roic_research_ready": note_pass,
                "uncertainty_champion_segments": int(uncertainty_gate.iloc[0]["uncertainty_champions"]),
                "research_freeze_eligible": research_freeze,
                "terminal_gate_pass": False,
                "production_gate_pass": False,
                "live_matched_observations": f"0/{production_minimum_live_observations}",
                "new_dcf_run": False,
                "new_reverse_dcf_run": False,
                "pdf_parsing_deferred": True,
                "status": "FREEZE_ELIGIBLE_NOT_FROZEN" if research_freeze else "HOLD_RESEARCH_UNFROZEN",
                "failed_conditions": failed_conditions,
            }
        ]
    )
    authority = portability_summary[
        [
            "segment", "revenue_route", "realized_revenue_routes", "structural_anchor_coverage_pct",
            "revenue_mase", "revenue_champion_eligible",
            "margin_route", "margin_mase", "margin_champion_eligible", "joint_champion",
            "scope_change_rows",
        ]
    ].copy()
    authority["economic_component_claim_allowed"] = (
        authority["revenue_route"].str.startswith("STRUCTURAL")
        & authority["revenue_champion_eligible"]
        & authority["structural_anchor_coverage_pct"].eq(100.0)
    )
    authority["reinvestment_forecast_claim_allowed"] = False
    authority["roic_forecast_claim_allowed"] = False
    authority["terminal_input_allowed"] = False
    valuation = pd.DataFrame(
        [
            {
                "cat_v1_7_reference_value_per_share_usd": 399.1175,
                "reference_preserved": True,
                "cmi_dcf_value_per_share_usd": pd.NA,
                "cmi_reverse_dcf_result": "NOT_RUN_BY_DESIGN",
                "reason": "PORTABILITY_RESEARCH_REQUIRES_SEPARATE_TERMINAL_AND_LIVE_GATES",
                "terminal_input_allowed": False,
            }
        ]
    )
    return {
        "industrials_v2_gate": gate,
        "cmi_target_route_authority": authority,
        "industrials_v2_valuation_authority": valuation,
    }
