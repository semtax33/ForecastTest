from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161
from energy_nowcast.research.ep_v172 import (
    build_acquiree_nopat_reconciliation,
    build_cycle_normalized_cohorts,
    build_v172_gate,
)


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
ARCANA = ROOT.parent / "Arcana"
FNSD = ARCANA / "data-lake" / "bronze" / "sec" / "financial-statement-and-notes-data-set"
COMPANYFACTS = ARCANA / "data-lake" / "bronze" / "sec" / "companyfacts"
V171_OUTPUT = ROOT / "output" / "energy_valuation_v1_7_1_research"
OUTPUT = ROOT / "output" / "energy_valuation_v1_7_2_research"
V171_PARENT_FILES = (
    ROOT / "configs" / "ep_v171_acquisition_proof_registry.csv",
    ROOT / "configs" / "ep_v171_divestiture_proof_registry.csv",
    ROOT / "energy_nowcast" / "research" / "ep_v171" / "__init__.py",
    ROOT / "energy_nowcast" / "research" / "ep_v171" / "evidence.py",
    ROOT / "energy_nowcast" / "research" / "ep_v171" / "cohort.py",
    ROOT / "energy_nowcast" / "research" / "ep_v171" / "gate.py",
    ROOT / "scripts/energy/research/ep/v1_7_1_mna_numerator.py",
    ROOT / "tests" / "test_ep_mna_numerator_purchase_accounting_v1_7_1.py",
    V171_OUTPUT / "acquisition_numerator_and_purchase_accounting_proof.csv",
    V171_OUTPUT / "divestiture_capital_and_earnings_proof.csv",
    V171_OUTPUT / "company_year_mna_normalized_bridge_v1_7_1.csv",
    V171_OUTPUT / "deal_year_t_plus_2_roic_cohorts.csv",
    V171_OUTPUT / "v1_7_1_gate.csv",
    V171_OUTPUT / "metadata.json",
    V171_OUTPUT / "report.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _v171_snapshot() -> str:
    missing = [str(path) for path in V171_PARENT_FILES if not path.exists()]
    if missing:
        raise FileNotFoundError(f"V1.7.1 parent artifacts missing: {missing}")
    payload = "|".join(
        f"{path.relative_to(ROOT)}={_sha256(path)}" for path in V171_PARENT_FILES
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    v161_before = verify_v161(ROOT)
    v171_before = _v171_snapshot()
    acquisition = pd.read_csv(
        V171_OUTPUT / "acquisition_numerator_and_purchase_accounting_proof.csv",
        dtype={"target_cik": str, "target_accession": str, "adsh": str},
    )
    v171_company_year = pd.read_csv(
        V171_OUTPUT / "company_year_mna_normalized_bridge_v1_7_1.csv"
    )
    v171_cohorts = pd.read_csv(V171_OUTPUT / "deal_year_t_plus_2_roic_cohorts.csv")
    annual_organic = pd.read_csv(
        ROOT
        / "output"
        / "energy_valuation_v1_7_research"
        / "annual_organic_company_economics.csv"
    )
    acquiree_nopat = build_acquiree_nopat_reconciliation(
        acquisition_proof=acquisition, companyfacts_root=COMPANYFACTS
    )
    cycle = build_cycle_normalized_cohorts(
        acquisition_proof=acquisition,
        acquiree_nopat=acquiree_nopat,
        v171_company_year=v171_company_year,
        v171_cohorts=v171_cohorts,
        annual_organic=annual_organic,
        through_cycle_path=ROOT
        / "output"
        / "energy_valuation_v1_2_research"
        / "through_cycle_economics.csv",
        price_mix_path=ROOT
        / "output"
        / "energy_valuation_v1_3_research"
        / "production_mix_price_proxy.csv",
        v14_cross_check_path=ROOT
        / "output"
        / "energy_valuation_v1_4_research"
        / "expanded_core_cross_check.csv",
        annual_cost_scope_path=ROOT
        / "output"
        / "energy_valuation_v1_4_research"
        / "annual_cost_scope_panel.csv",
        fang_accounting_path=ROOT
        / "output"
        / "energy_valuation_v1_6_1_research"
        / "fang_margin_gap_attribution.csv",
        reserve_panel_path=ROOT
        / "output"
        / "energy_valuation_v1_6_research"
        / "v16_combined_reserve_chain_panel.csv",
        fang_panel_path=ROOT
        / "output"
        / "energy_valuation_v1_6_research"
        / "fang_actual_cost_mix_panel.csv",
        supplement_registry_path=ROOT
        / "configs"
        / "ep_v172_cycle_production_supplement.csv",
        fnsd_root=FNSD,
        companyfacts_root=COMPANYFACTS,
        ttm_financial_path=ROOT
        / "output"
        / "energy_valuation_v1_1"
        / "ttm_financial_bridge_v1_1.parquet",
    )
    v171_gate = pd.read_csv(V171_OUTPUT / "v1_7_1_gate.csv")
    v161_gate = pd.read_csv(
        ROOT
        / "output"
        / "energy_valuation_v1_6_1_research"
        / "v1_6_1_freeze_gate.csv"
    )
    gate = build_v172_gate(
        acquiree_nopat=acquiree_nopat,
        cycle_company_year=cycle["cycle_normalized_company_year_panel"],
        cohorts=cycle["reported_vs_cycle_normalized_deal_cohorts"],
        v171_gate=v171_gate,
        v161_gate=v161_gate,
    )
    artifacts = {
        "acquiree_net_income_to_nopat_reconciliation": acquiree_nopat,
        **cycle,
        "v1_7_2_gate": gate,
    }
    for name, frame in artifacts.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)

    v161_after = verify_v161(ROOT)
    v171_after = _v171_snapshot()
    if v161_before["manifest_sha256"] != v161_after["manifest_sha256"]:
        raise RuntimeError("Frozen V1.6.1 changed during V1.7.2 research")
    if v171_before != v171_after:
        raise RuntimeError("V1.7.1 parent changed during V1.7.2 research")

    gate_row = gate.iloc[0]
    metadata = {
        "version": "E&P_ACQUIREE_NOPAT_CYCLE_NORMALIZED_COHORT_V1_7_2_RESEARCH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_6_1_manifest_sha256": v161_after["manifest_sha256"],
        "v1_7_1_parent_snapshot_sha256": v171_after,
        "frozen_v1_6_1_mutated": False,
        "v1_7_1_parent_mutated": False,
        "direct_acquiree_nopat_events": int(gate_row["direct_acquiree_nopat_events"]),
        "bridged_acquiree_nopat_events": int(
            gate_row["bridged_acquiree_nopat_events"]
        ),
        "complete_3y_reported_nopat_cohort_tickers": int(
            gate_row["complete_3y_reported_nopat_cohort_tickers"]
        ),
        "cycle_normalized_annual_tickers": int(
            gate_row["cycle_normalized_annual_tickers"]
        ),
        "complete_3y_cycle_normalized_cohort_tickers": int(
            gate_row["complete_3y_cycle_normalized_cohort_tickers"]
        ),
        "validated_organic_roic_tickers": int(
            gate_row["validated_organic_roic_tickers"]
        ),
        "research_gate": bool(gate_row["v1_7_2_research_gate"]),
        "research_freeze_eligible": bool(
            gate_row["v1_7_2_research_freeze_eligible"]
        ),
        "development_status": gate_row["development_status"],
        "terminal_anchor_replacement_allowed": False,
        "wacc_recalibrated": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    nopat_view = acquiree_nopat[
        [
            "ticker",
            "fiscal_year",
            "event_name",
            "predeal_annualized_interest_expense_usd",
            "predeal_implied_interest_rate",
            "predeal_normalized_tax_rate",
            "acquiree_full_year_normalized_nopat_bridge_usd",
            "acquiree_nopat_return_proxy_pct",
            "acquiree_nopat_bridge_ready",
            "acquiree_nopat_bridge_status",
        ]
    ]
    cycle_reference_view = cycle["cycle_normalization_reference"].loc[
        lambda frame: frame["ticker"].isin(["COP", "DVN", "EOG", "FANG"]),
        [
            "ticker",
            "normalized_price_per_boe",
            "normalized_unit_cost_per_boe",
            "normalized_after_tax_unit_margin_per_boe",
            "normalized_tax_rate",
            "cycle_normalization_route",
            "independent_complete_unit_cost_scope",
        ],
    ]
    cohorts_view = cycle["reported_vs_cycle_normalized_deal_cohorts"]
    cohorts_view = cohorts_view[
        [
            "ticker",
            "deal_year",
            "year_label",
            "observation_year",
            "reported_organic_nopat_roic_pct",
            "cycle_normalized_organic_roic_proxy_pct",
            "reported_organic_nopat_bridge_status",
            "cycle_normalization_status",
            "reported_cumulative_organic_nopat_roic_pct",
            "cycle_normalized_cumulative_organic_roic_proxy_pct",
            "reported_nopat_cohort_complete",
            "cycle_normalized_cohort_complete",
        ]
    ]
    report = f"""# E&P V1.7.2 acquiree NOPAT and cycle-normalized cohort research

V1.7.2 is a child research layer of V1.7.1. Frozen V1.6.1 and the full
V1.7.1 parent snapshot are hash-verified before and after execution. No WACC,
terminal, scenario, parser, or production state is changed.

## Acquiree net income to NOPAT reconciliation

{_markdown(nopat_view)}

WPX and Concho use target-company pre-deal YTD interest expense, tax, debt, and
PPA-assumed debt. The bridge annualizes the target's interest burden, applies
the target effective tax rate, and adds after-tax interest to acquiree net
income. Separately disclosed pre-deal non-operating items are retained but not
applied to a different post-close period. These are evidence-backed interest
bridges, not directly disclosed operating NOPAT.

## Cycle-normalization reference

{_markdown(cycle_reference_view)}

Cycle-normalized NOPAT follows `normalized commodity price x production -
normalized unit cost`, after normalized tax. FANG can use the V1.4
basis-adjusted known-cost route. Other tickers use the V1.3 normalized price and
V1.2 hierarchical margin-implied all-in unit cost and are explicitly marked as
not having independent complete unit-cost scope.

## Reported versus cycle-normalized deal cohorts

{_markdown(cohorts_view)}

The event-year reported numerator removes bridged acquiree NOPAT, while the
cycle-normalized numerator removes an acquiree production proxy inferred from
reported acquiree revenue and buyer revenue per BOE. These two views are stored
separately. Missing years and contaminated company-year M&A perimeters remain
locked.

## Gate

{_markdown(gate)}

The research gate passes because two acquiree NOPAT bridges and multiple annual
cycle-normalized diagnostics are available. Freeze remains deferred: only DVN
has complete reported and cycle-normalized t-through-t+2 cohorts, all acquiree
NOPAT values remain bridged rather than directly disclosed, and validated
organic ROIC remains zero. Terminal replacement remains 0/14 and production
remains 0/20.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(nopat_view.to_string(index=False))
    print(cycle_reference_view.to_string(index=False))
    print(cohorts_view.to_string(index=False))
    print(gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
