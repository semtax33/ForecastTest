from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161
from energy_nowcast.research.ep_v17 import (
    build_mna_event_evidence,
    build_organic_company_economics,
    build_v17_gate,
)


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
ARCANA = ROOT.parent / "Arcana"
FNSD = ARCANA / "data-lake" / "bronze" / "sec" / "financial-statement-and-notes-data-set"
OUTPUT = ROOT / "output" / "energy_valuation_v1_7_research"


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    parent_before = verify_v161(ROOT)
    event_evidence = build_mna_event_evidence(
        registry_path=ROOT / "configs/ep_v17_mna_event_registry.csv",
        fnsd_root=FNSD,
    )
    research = build_organic_company_economics(
        event_evidence=event_evidence,
        parent_capital_panel_path=ROOT
        / "output/energy_valuation_v1_6_1_research/annual_mna_normalized_capital_bridge.csv",
        ttm_financial_path=ROOT
        / "output/energy_valuation_v1_1/ttm_financial_bridge_v1_1.parquet",
    )
    v161_gate = pd.read_csv(
        ROOT / "output/energy_valuation_v1_6_1_research/v1_6_1_freeze_gate.csv"
    )
    gate = build_v17_gate(
        event_evidence=research["mna_event_capital_and_numerator_evidence"],
        annual_organic=research["annual_organic_company_economics"],
        summary=research["organic_company_economics_summary"],
        v161_gate=v161_gate,
    )
    artifacts = {**research, "v1_7_gate": gate}
    for name, frame in artifacts.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)
    parent_after = verify_v161(ROOT)
    if parent_before["manifest_sha256"] != parent_after["manifest_sha256"]:
        raise RuntimeError("Frozen V1.6.1 changed during V1.7 research")

    annual = research["annual_organic_company_economics"]
    selected = annual.loc[
        annual.apply(
            lambda row: (row["ticker"], int(row["year"]))
            in {("FANG", 2024), ("EOG", 2025), ("CNX", 2025)},
            axis=1,
        )
    ]
    metadata = {
        "version": "E&P_ORGANIC_COMPANY_ECONOMICS_V1_7_RESEARCH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_6_1_manifest_sha256": parent_after["manifest_sha256"],
        "frozen_parent_mutated": False,
        "event_evidence_rows": len(event_evidence),
        "material_mna_proxy_ready_company_years": int(
            annual["material_mna_year_proxy_ready"].sum()
        ),
        "organic_company_roic_validated_tickers": int(
            research["organic_company_economics_summary"][
                "organic_company_roic_validated"
            ].sum()
        ),
        "research_gate": bool(gate.iloc[0]["v1_7_research_gate"]),
        "research_freeze_eligible": bool(
            gate.iloc[0]["v1_7_research_freeze_eligible"]
        ),
        "terminal_anchor_replacement_allowed": False,
        "wacc_recalibrated": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report = f"""# E&P V1.7 organic company economics research

V1.7 is a child research layer of frozen V1.6.1. It does not change WACC,
terminal economics, scenario weights, or production status.

## Event-level SEC evidence

{_markdown(research['mna_event_capital_and_numerator_evidence'][[
    'ticker', 'fiscal_year', 'event_name', 'event_type',
    'acquiree_revenue_since_close_usd', 'acquiree_net_income_since_close_usd',
    'acquired_invested_capital_proxy_usd', 'acquired_capital_proxy_semantics',
    'noncash_equity_consideration_usd', 'noncash_assumed_debt_usd',
    'classification_phrase_proven', 'acquired_numerator_semantics',
]])}

Acquiree net income is an after-tax contribution proxy, not NOPAT. Purchase-
accounting step-up remains unidentified without the acquiree's pre-deal book
basis. Neither item is allowed as a terminal input.

## Core event-year organic bridges

{_markdown(selected[[
    'ticker', 'year', 'raw_delta_nopat_usd',
    'acquired_after_tax_contribution_adjustment_usd',
    'transaction_cost_after_tax_addback_usd',
    'organic_delta_nopat_after_tax_proxy_usd',
    'raw_delta_invested_capital_usd', 'acquired_capital_adjustment_usd',
    'divested_capital_adjustment_usd',
    'pre_divestiture_scope_delta_invested_capital_proxy_usd',
    'organic_delta_invested_capital_proxy_usd',
    'pre_divestiture_scope_delta_nopat_after_tax_proxy_usd',
    'organic_incremental_roic_after_tax_proxy_pct', 'organic_bridge_status',
]])}

Material divestitures fail closed when divested book capital and operating
contribution are not separately disclosed. Asset acquisitions fail closed when
the acquired operation's contribution cannot be separated from the buyer.

## Research gate

{_markdown(gate)}

The research infrastructure is complete, but V1.7 is not freeze-eligible:
validated organic company ROIC remains 0 tickers and purchase-accounting
step-up remains unidentified. Terminal replacement stays locked at 0/14 and
production stays locked at 0/20.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(
        research["mna_event_capital_and_numerator_evidence"][[
            "ticker",
            "fiscal_year",
            "event_name",
            "event_type",
            "acquiree_net_income_since_close_usd",
            "acquired_invested_capital_proxy_usd",
            "noncash_equity_consideration_usd",
            "noncash_assumed_debt_usd",
            "acquired_numerator_semantics",
        ]].to_string(index=False)
    )
    print(
        selected[[
            "ticker",
            "year",
            "raw_delta_nopat_usd",
            "organic_delta_nopat_after_tax_proxy_usd",
            "raw_delta_invested_capital_usd",
            "pre_divestiture_scope_delta_invested_capital_proxy_usd",
            "organic_delta_invested_capital_proxy_usd",
            "organic_incremental_roic_after_tax_proxy_pct",
            "organic_bridge_status",
        ]].to_string(index=False)
    )
    print(gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
