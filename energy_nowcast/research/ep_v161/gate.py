from __future__ import annotations

import pandas as pd


def build_v161_freeze_gate(
    *,
    coverage_gate: pd.DataFrame,
    accounting_summary: pd.DataFrame,
    mna_summary: pd.DataFrame,
    three_level_roic_summary: pd.DataFrame,
    terminal_gate: pd.DataFrame,
) -> pd.DataFrame:
    coverage = coverage_gate.iloc[0]
    accounting = accounting_summary.set_index("ticker")
    core_pass = int(accounting["accounting_perimeter_pass"].sum())
    fang_classified = bool(accounting.loc["FANG", "special_case_classified"])
    cnx_hedge = bool(accounting.loc["CNX", "hedge_presentation_proven"])
    ar_scope = bool(accounting.loc["AR", "scope_identity_proven"])
    roic_separated = bool(three_level_roic_summary["three_level_roic_separated"].all())
    mna_implemented = bool(mna_summary["diagnostic_implemented"].all())
    terminal_ready = int(terminal_gate["terminal_candidate_ready"].sum())
    conditions = {
        "reserve_coverage_8_of_14": int(coverage["reserve_chain_ready_tickers"]) >= 8,
        "all_group_coverage": bool(coverage["group_targets_met"]),
        "core_accounting_min_2_of_3": core_pass >= 2,
        "fang_2025_classified": fang_classified,
        "cnx_hedge_presentation_proven": cnx_hedge,
        "ar_transport_tax_scope_proven": ar_scope,
        "three_level_roic_separated": roic_separated,
        "mna_normalization_diagnostic_implemented": mna_implemented,
        "terminal_replacement_remains_locked": terminal_ready == 0,
    }
    return pd.DataFrame(
        [
            {
                **conditions,
                "core_accounting_pass_tickers": core_pass,
                "core_accounting_target_tickers": 2,
                "terminal_candidate_ready_tickers": terminal_ready,
                "v1_6_1_research_freeze_eligible": all(conditions.values()),
                "terminal_anchor_replacement_allowed": False,
                "wacc_recalibrated": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
