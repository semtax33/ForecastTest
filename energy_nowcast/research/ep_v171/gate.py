from __future__ import annotations

import pandas as pd


def build_v171_gate(
    *,
    acquisition_proof: pd.DataFrame,
    divestiture_proof: pd.DataFrame,
    company_year_bridge: pd.DataFrame,
    deal_cohorts: pd.DataFrame,
    v17_gate: pd.DataFrame,
    v161_gate: pd.DataFrame,
) -> pd.DataFrame:
    normalized_events = int(
        acquisition_proof["full_year_normalized_acquiree_net_income_usd"]
        .notna()
        .sum()
    )
    step_up_events = int(acquisition_proof["purchase_accounting_step_up_proven"].sum())
    fully_bridged_events = int(
        company_year_bridge["company_year_mna_scope_fully_bridged"].sum()
    )
    divestiture_events = int(
        divestiture_proof["divestiture_proof_status"]
        .eq("BOOK_CAPITAL_AND_AFTER_TAX_EARNINGS_PROXY_PROVEN_NOT_NOPAT")
        .sum()
    )
    validated_tickers = int(
        company_year_bridge.loc[
            company_year_bridge["organic_company_roic_validated"], "ticker"
        ].nunique()
    )
    complete_cohort_tickers = int(
        deal_cohorts.loc[deal_cohorts["cohort_window_complete"], "ticker"].nunique()
    )
    direct_nopat_events = int(acquisition_proof["acquired_nopat_directly_disclosed"].sum())
    ownership_math_proven = bool(
        (
            acquisition_proof.loc[
                acquisition_proof["acquiree_net_income_since_close_usd"].notna(),
                "ownership_fraction",
            ]
            .between(0.0, 1.0, inclusive="right")
            .all()
        )
        and normalized_events >= 2
    )
    parent_v17 = v17_gate.iloc[0]
    parent_v161 = v161_gate.iloc[0]
    research_conditions = {
        "v1_6_1_frozen_parent_gate_preserved": bool(
            parent_v161["v1_6_1_research_freeze_eligible"]
        ),
        "v1_7_parent_research_gate_preserved": bool(parent_v17["v1_7_research_gate"]),
        "acquiree_numerator_normalized_min_2": normalized_events >= 2,
        "purchase_accounting_step_up_min_2": step_up_events >= 2,
        "divestiture_capital_and_earnings_proof_min_1": divestiture_events >= 1,
        "material_mna_fully_bridged_min_2": fully_bridged_events >= 2,
        "ownership_period_math_proven": ownership_math_proven,
        "terminal_replacement_remains_locked": bool(
            parent_v161["terminal_candidate_ready_tickers"] == 0
        ),
    }
    freeze_conditions = {
        "validated_organic_roic_tickers_min_2": validated_tickers >= 2,
        "complete_multi_year_roic_cohort_tickers_min_2": complete_cohort_tickers >= 2,
    }
    research_gate = all(research_conditions.values())
    freeze_eligible = research_gate and all(freeze_conditions.values())
    return pd.DataFrame(
        [
            {
                **research_conditions,
                **freeze_conditions,
                "acquiree_numerator_normalized_events": normalized_events,
                "purchase_accounting_step_up_proven_events": step_up_events,
                "divestiture_capital_and_earnings_proxy_proven_events": divestiture_events,
                "material_mna_fully_bridged_company_years": fully_bridged_events,
                "direct_acquiree_nopat_disclosed_events": direct_nopat_events,
                "validated_organic_roic_tickers": validated_tickers,
                "complete_multi_year_roic_cohort_tickers": complete_cohort_tickers,
                "v1_7_1_research_gate": research_gate,
                "v1_7_1_research_freeze_eligible": freeze_eligible,
                "development_status": (
                    "RESEARCH_GATE_PASSED_FREEZE_DEFERRED"
                    if research_gate and not freeze_eligible
                    else (
                        "RESEARCH_FREEZE_ELIGIBLE"
                        if freeze_eligible
                        else "RESEARCH_GATE_FAILED"
                    )
                ),
                "terminal_anchor_replacement_allowed": False,
                "wacc_recalibrated": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
