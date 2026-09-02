from __future__ import annotations

import pandas as pd


def build_v17_gate(
    *,
    event_evidence: pd.DataFrame,
    annual_organic: pd.DataFrame,
    summary: pd.DataFrame,
    v161_gate: pd.DataFrame,
) -> pd.DataFrame:
    core = set(event_evidence["ticker"])
    classification_proven = int(event_evidence["classification_phrase_proven"].sum())
    after_tax_proxy_events = int(
        event_evidence["acquiree_net_income_since_close_usd"].notna().sum()
    )
    acquired_capital_events = int(
        event_evidence["acquired_invested_capital_proxy_usd"].notna().sum()
    )
    noncash_evidence_events = int(
        (
            event_evidence["noncash_equity_consideration_usd"].fillna(0.0)
            + event_evidence["noncash_assumed_debt_usd"].fillna(0.0)
        ).gt(0.0).sum()
    )
    material_ready = int(annual_organic["material_mna_year_proxy_ready"].sum())
    validated = int(summary["organic_company_roic_validated"].sum())
    parent = v161_gate.iloc[0]
    conditions = {
        "v1_6_1_parent_freeze_gate_preserved": bool(
            parent["v1_6_1_research_freeze_eligible"]
        ),
        "core_event_registry_3_of_3": core == {"CNX", "EOG", "FANG"},
        "classification_proof_3_of_3": classification_proven == 3,
        "after_tax_contribution_proxy_min_2": after_tax_proxy_events >= 2,
        "acquired_capital_proxy_3_of_3": acquired_capital_events == 3,
        "noncash_or_assumed_debt_evidence_min_1": noncash_evidence_events >= 1,
        "material_mna_proxy_bridge_min_1": material_ready >= 1,
        "terminal_replacement_remains_locked": bool(
            parent["terminal_candidate_ready_tickers"] == 0
        ),
    }
    research_complete = all(conditions.values())
    return pd.DataFrame(
        [
            {
                **conditions,
                "classification_proven_events": classification_proven,
                "after_tax_contribution_proxy_events": after_tax_proxy_events,
                "acquired_capital_proxy_events": acquired_capital_events,
                "noncash_or_assumed_debt_evidence_events": noncash_evidence_events,
                "material_mna_proxy_ready_company_years": material_ready,
                "organic_company_roic_validated_tickers": validated,
                "purchase_accounting_step_up_identified_events": int(
                    event_evidence["purchase_accounting_step_up_usd"].notna().sum()
                ),
                "v1_7_research_gate": research_complete,
                "v1_7_research_freeze_eligible": bool(
                    research_complete
                    and validated >= 3
                    and event_evidence["purchase_accounting_step_up_usd"].notna().sum()
                    >= 2
                ),
                "terminal_anchor_replacement_allowed": False,
                "wacc_recalibrated": False,
                "production_promoted": False,
                "live_matched_observations": "0/20",
            }
        ]
    )
