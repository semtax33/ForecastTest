from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161
from energy_nowcast.research.ep_v171 import (
    build_acquisition_proof,
    build_divestiture_proof,
    build_v171_company_year_bridge,
    build_v171_deal_cohorts,
    build_v171_gate,
)


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
ARCANA = ROOT.parent / "Arcana"
FNSD = ARCANA / "data-lake" / "bronze" / "sec" / "financial-statement-and-notes-data-set"
COMPANYFACTS = ARCANA / "data-lake" / "bronze" / "sec" / "companyfacts"
V17_OUTPUT = ROOT / "output" / "energy_valuation_v1_7_research"
OUTPUT = ROOT / "output" / "energy_valuation_v1_7_1_research"
V17_PARENT_FILES = (
    ROOT / "configs" / "ep_v17_mna_event_registry.csv",
    ROOT / "energy_nowcast" / "research" / "ep_v17" / "__init__.py",
    ROOT / "energy_nowcast" / "research" / "ep_v17" / "fnsd.py",
    ROOT / "energy_nowcast" / "research" / "ep_v17" / "organic.py",
    ROOT / "energy_nowcast" / "research" / "ep_v17" / "gate.py",
    ROOT / "scripts/energy/research/ep/v1_7_organic_company_economics.py",
    V17_OUTPUT / "mna_event_capital_and_numerator_evidence.csv",
    V17_OUTPUT / "annual_organic_company_economics.csv",
    V17_OUTPUT / "organic_company_economics_summary.csv",
    V17_OUTPUT / "v1_7_gate.csv",
    V17_OUTPUT / "metadata.json",
    V17_OUTPUT / "report.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _v17_snapshot() -> str:
    missing = [str(path) for path in V17_PARENT_FILES if not path.exists()]
    if missing:
        raise FileNotFoundError(f"V1.7 parent artifacts missing: {missing}")
    payload = "|".join(
        f"{path.relative_to(ROOT)}={_sha256(path)}" for path in V17_PARENT_FILES
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    v161_before = verify_v161(ROOT)
    v17_before = _v17_snapshot()
    annual = pd.read_csv(V17_OUTPUT / "annual_organic_company_economics.csv")
    acquisition = build_acquisition_proof(
        registry_path=ROOT / "configs" / "ep_v171_acquisition_proof_registry.csv",
        fnsd_root=FNSD,
        companyfacts_root=COMPANYFACTS,
    )
    divestiture = build_divestiture_proof(
        registry_path=ROOT / "configs" / "ep_v171_divestiture_proof_registry.csv",
        fnsd_root=FNSD,
        annual_organic=annual,
    )
    company_year = build_v171_company_year_bridge(
        acquisition_proof=acquisition, annual_organic=annual
    )
    cohorts = build_v171_deal_cohorts(
        acquisition_proof=acquisition,
        company_year_bridge=company_year,
        annual_organic=annual,
    )
    v17_gate = pd.read_csv(V17_OUTPUT / "v1_7_gate.csv")
    v161_gate = pd.read_csv(
        ROOT / "output" / "energy_valuation_v1_6_1_research" / "v1_6_1_freeze_gate.csv"
    )
    gate = build_v171_gate(
        acquisition_proof=acquisition,
        divestiture_proof=divestiture,
        company_year_bridge=company_year,
        deal_cohorts=cohorts,
        v17_gate=v17_gate,
        v161_gate=v161_gate,
    )
    artifacts = {
        "acquisition_numerator_and_purchase_accounting_proof": acquisition,
        "divestiture_capital_and_earnings_proof": divestiture,
        "company_year_mna_normalized_bridge_v1_7_1": company_year,
        "deal_year_t_plus_2_roic_cohorts": cohorts,
        "v1_7_1_gate": gate,
    }
    for name, frame in artifacts.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)

    v161_after = verify_v161(ROOT)
    v17_after = _v17_snapshot()
    if v161_before["manifest_sha256"] != v161_after["manifest_sha256"]:
        raise RuntimeError("Frozen V1.6.1 changed during V1.7.1 research")
    if v17_before != v17_after:
        raise RuntimeError("V1.7 parent changed during V1.7.1 research")

    gate_row = gate.iloc[0]
    metadata = {
        "version": "E&P_MNA_NUMERATOR_PURCHASE_ACCOUNTING_V1_7_1_RESEARCH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_6_1_manifest_sha256": v161_after["manifest_sha256"],
        "v1_7_parent_snapshot_sha256": v17_after,
        "frozen_v1_6_1_mutated": False,
        "v1_7_parent_mutated": False,
        "acquiree_numerator_normalized_events": int(
            gate_row["acquiree_numerator_normalized_events"]
        ),
        "purchase_accounting_step_up_proven_events": int(
            gate_row["purchase_accounting_step_up_proven_events"]
        ),
        "divestiture_capital_and_earnings_proxy_proven_events": int(
            gate_row["divestiture_capital_and_earnings_proxy_proven_events"]
        ),
        "material_mna_fully_bridged_company_years": int(
            gate_row["material_mna_fully_bridged_company_years"]
        ),
        "validated_organic_roic_tickers": int(
            gate_row["validated_organic_roic_tickers"]
        ),
        "complete_multi_year_roic_cohort_tickers": int(
            gate_row["complete_multi_year_roic_cohort_tickers"]
        ),
        "research_gate": bool(gate_row["v1_7_1_research_gate"]),
        "research_freeze_eligible": bool(
            gate_row["v1_7_1_research_freeze_eligible"]
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

    acquisition_view = acquisition[
        [
            "ticker",
            "fiscal_year",
            "event_name",
            "ownership_fraction",
            "acquiree_net_income_since_close_usd",
            "full_year_normalized_acquiree_net_income_usd",
            "acquired_invested_capital_usd",
            "predeal_book_invested_capital_usd",
            "purchase_accounting_step_up_usd",
            "normalized_acquiree_return_proxy_pct",
            "purchase_accounting_step_up_status",
        ]
    ]
    bridge_view = company_year[
        [
            "ticker",
            "year",
            "event_name",
            "organic_delta_nopat_same_period_proxy_usd",
            "organic_delta_invested_capital_v171_proxy_usd",
            "organic_incremental_roic_v171_after_tax_proxy_pct",
            "company_year_mna_scope_fully_bridged",
            "company_year_bridge_status",
        ]
    ]
    cohort_view = cohorts[
        [
            "ticker",
            "deal_year",
            "year_label",
            "observation_year",
            "annual_organic_incremental_roic_proxy_pct",
            "cumulative_organic_incremental_roic_proxy_pct",
            "cohort_window_complete",
            "cohort_status",
        ]
    ]
    report = f"""# E&P V1.7.1 M&A numerator and purchase-accounting proof

V1.7.1 is a child research layer. Frozen V1.6.1 and the V1.7 parent snapshot
are hash-verified before and after the run. WACC, terminal economics, scenario
weights, parser semantics, and production status are unchanged.

## Acquisition numerator, ownership period, and purchase accounting

{_markdown(acquisition_view)}

Reported post-close net income is subtracted only from the buyer's same-period
change in NOPAT. Its full-year normalized value is kept separately for an
acquiree run-rate return proxy. This prevents a full-year numerator from being
mixed into a partial-year consolidated bridge. The proxy remains net income,
not NOPAT, and therefore is not validated company ROIC.

WPX and Concho use the last public pre-deal 10-Q book basis filed before close.
Purchase-accounting step-up is PPA economic invested capital minus that book
basis. Private targets Endeavor and Encino remain locked rather than receiving
an inferred pre-deal book value.

## Company-year M&A bridges

{_markdown(bridge_view)}

Divestiture materiality is measured against opening capital plus acquired
capital in the event year. Immaterial dispositions are left unadjusted and
explicitly labelled. Known additional material transactions still fail closed.

## Divestiture capital and earnings evidence

{_markdown(divestiture[[
    'ticker', 'fiscal_year', 'event_name', 'event_close_period',
    'net_proceeds_usd', 'divested_book_invested_capital_usd',
    'pre_tax_operating_contribution_usd',
    'divested_after_tax_operating_contribution_proxy_usd',
    'divestiture_proof_status',
]])}

The Indonesia disclosure proves divested book capital and pre-close earnings,
but the after-tax amount is still a tax-adjusted earnings proxy rather than
directly disclosed NOPAT.

## Deal-year through t+2 cohorts

{_markdown(cohort_view)}

Only DVN/WPX currently has a complete t, t+1, t+2 diagnostic window. Its
cumulative return is a cycle-sensitive after-tax proxy, not a terminal input.
Other cohorts remain partial or fail closed when company-year M&A scope is
contaminated.

## Gate

{_markdown(gate)}

The V1.7.1 research gate passes, but freeze remains deferred: directly matched
organic NOPAT is still unavailable, validated organic ROIC remains zero, and
only one ticker has a complete three-year cohort. Terminal replacement stays
locked at 0/14 and production stays locked at 0/20.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(acquisition_view.to_string(index=False))
    print(bridge_view.to_string(index=False))
    print(cohort_view.to_string(index=False))
    print(gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
