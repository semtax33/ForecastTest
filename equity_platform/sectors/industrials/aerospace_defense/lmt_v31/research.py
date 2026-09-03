from __future__ import annotations

import pandas as pd

from equity_platform.core.gates import GateCheck, evaluate_gate_checks


def build_lmt_v31_research_gates(
    *,
    evidence_summary: pd.DataFrame,
    coverage: pd.DataFrame,
    selected_summary: pd.DataFrame,
    challenger_summary: pd.DataFrame,
    decisions: pd.DataFrame,
    preservation: pd.DataFrame,
    uncertainty_gate: pd.DataFrame,
    bridge_summary: pd.DataFrame,
    parent_status: str,
    minimum_research_joint_champions: int,
    production_minimum_live_observations: int,
) -> dict[str, pd.DataFrame]:
    evidence = evidence_summary.iloc[0]
    covered = coverage.iloc[0]
    evidence_pass = bool(evidence["evidence_gate_pass"])
    pit_pass = bool(covered["cutoff_violations"] == 0)
    window_pass = bool(
        covered["validation_rows"] == 24
        and covered["validation_periods"] == 6
        and covered["fixed_window_first_period"] == "2025Q1"
        and covered["fixed_window_last_period"] == "2026Q2"
    )
    preservation_pass = bool(
        covered["parent_routes_preserved"]
        and preservation[
            ["mfc_all_predictions_preserved", "space_revenue_preserved", "non_space_margin_preserved"]
        ].all().all()
    )
    joint_champions = int(selected_summary["joint_champion"].sum())
    research_freeze, failed = evaluate_gate_checks(
        [
            GateCheck("PARENT_V3_REMAINS_UNFROZEN", parent_status == "HOLD_RESEARCH_UNFROZEN"),
            GateCheck("PROGRAM_EVIDENCE_COVERAGE", evidence_pass),
            GateCheck("PROGRAM_LEVEL_BACKLOG_FAIL_CLOSED", bool(evidence["program_level_backlog_fail_closed"])),
            GateCheck("HISTORICAL_PIT_CUTOFF", pit_pass),
            GateCheck("FIXED_SIX_QUARTER_OOS", window_pass),
            GateCheck("AUTHORIZED_TARGETS_ONLY_AND_PARENT_PRESERVED", preservation_pass),
            GateCheck(
                "PORTABILITY_POINT_PERFORMANCE",
                joint_champions >= minimum_research_joint_champions,
            ),
        ]
    )
    gate = pd.DataFrame(
        [
            {
                "version": "INDUSTRIALS_PLATFORM_V3_1_LMT_PROGRAM_CONVERSION_RESEARCH",
                "parent_v3_status": parent_status,
                "program_evidence_gate_pass": evidence_pass,
                "historical_pit_cutoff_pass": pit_pass,
                "fixed_oos_window_pass": window_pass,
                "parent_preservation_pass": preservation_pass,
                "revenue_challengers_tested": int(decisions["revenue_challenger_tested"].sum()),
                "revenue_challengers_accepted": int(decisions["revenue_challenger_accepted"].sum()),
                "margin_challengers_tested": int(decisions["margin_challenger_tested"].sum()),
                "margin_challengers_accepted": int(decisions["margin_challenger_accepted"].sum()),
                "selected_revenue_champions": int(selected_summary["revenue_champion_eligible"].sum()),
                "selected_margin_champions": int(selected_summary["margin_champion_eligible"].sum()),
                "selected_joint_champions": joint_champions,
                "minimum_joint_champions": minimum_research_joint_champions,
                "uncertainty_champions": int(uncertainty_gate.iloc[0]["uncertainty_champions"]),
                "financial_bridge_claim_periods": int(bridge_summary.iloc[0]["financial_bridge_claim_periods"]),
                "research_freeze_eligible": research_freeze,
                "terminal_gate_pass": False,
                "production_gate_pass": False,
                "live_matched_observations": f"0/{production_minimum_live_observations}",
                "new_dcf_run": False,
                "new_reverse_dcf_run": False,
                "status": "FREEZE_ELIGIBLE_NOT_FROZEN" if research_freeze else "HOLD_RESEARCH_UNFROZEN",
                "failed_conditions": failed,
            }
        ]
    )
    authority = selected_summary.merge(
        challenger_summary[
            [
                "segment",
                "revenue_route",
                "revenue_mase",
                "margin_route",
                "margin_mase",
            ]
        ].rename(
            columns={
                "revenue_route": "challenger_revenue_route",
                "revenue_mase": "challenger_revenue_mase",
                "margin_route": "challenger_margin_route",
                "margin_mase": "challenger_margin_mase",
            }
        ),
        on="segment",
        validate="one_to_one",
    ).merge(decisions, on="segment", validate="one_to_one")
    authority["program_narrative_research_evidence_allowed"] = True
    authority["program_level_backlog_claim_allowed"] = False
    authority["challenger_component_forecast_claim_allowed"] = (
        authority["revenue_challenger_accepted"] | authority["margin_challenger_accepted"]
    )
    authority["reinvestment_forecast_claim_allowed"] = False
    authority["roic_forecast_claim_allowed"] = False
    authority["terminal_input_allowed"] = False
    authority["production_input_allowed"] = False
    valuation = pd.DataFrame(
        [
            {
                "lmt_v31_dcf_value_per_share_usd": pd.NA,
                "lmt_v31_reverse_dcf_result": "NOT_RUN_BY_DESIGN",
                "reason": "PROGRAM_CONVERSION_CHALLENGERS_DID_NOT_CLOSE_POINT_PERFORMANCE_GATE",
                "terminal_input_allowed": False,
                "production_promotable": False,
            }
        ]
    )
    return {
        "industrials_v3_1_lmt_gate": gate,
        "lmt_v31_target_authority": authority,
        "industrials_v3_1_lmt_valuation_authority": valuation,
    }
