from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161
from energy_nowcast.research.ep_v173 import (
    build_energen_historical_evidence,
    build_nopat_triangulation,
    build_normalization_attribution,
    build_v173_gate,
)


ROOT = Path(__file__).resolve().parent
ARCANA = ROOT.parent / "Arcana"
COMPANYFACTS = ARCANA / "data-lake" / "bronze" / "sec" / "companyfacts"
FNSD = (
    ARCANA
    / "data-lake"
    / "bronze"
    / "sec"
    / "financial-statement-and-notes-data-set"
)
IR = ARCANA / "data-lake" / "bronze" / "sec" / "fillings" / "ir"
V171_OUTPUT = ROOT / "output" / "energy_valuation_v1_7_1_research"
V172_OUTPUT = ROOT / "output" / "energy_valuation_v1_7_2_research"
OUTPUT = ROOT / "output" / "energy_valuation_v1_7_3_research"

V172_PARENT_FILES = (
    ROOT / "energy_nowcast" / "research" / "ep_v172" / "__init__.py",
    ROOT / "energy_nowcast" / "research" / "ep_v172" / "nopat.py",
    ROOT / "energy_nowcast" / "research" / "ep_v172" / "cycle.py",
    ROOT / "energy_nowcast" / "research" / "ep_v172" / "gate.py",
    ROOT / "run_ep_acquiree_nopat_cycle_cohorts_v1_7_2.py",
    ROOT / "tests" / "test_ep_acquiree_nopat_cycle_cohorts_v1_7_2.py",
    ROOT / "configs" / "ep_v172_cycle_production_supplement.csv",
    V172_OUTPUT / "acquiree_net_income_to_nopat_reconciliation.csv",
    V172_OUTPUT / "cycle_normalization_reference.csv",
    V172_OUTPUT / "cycle_production_evidence.csv",
    V172_OUTPUT / "cycle_normalized_company_year_panel.csv",
    V172_OUTPUT / "reported_vs_cycle_normalized_deal_cohorts.csv",
    V172_OUTPUT / "v1_7_2_gate.csv",
    V172_OUTPUT / "metadata.json",
    V172_OUTPUT / "report.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _v172_snapshot() -> str:
    missing = [str(path) for path in V172_PARENT_FILES if not path.exists()]
    if missing:
        raise FileNotFoundError(f"V1.7.2 parent artifacts missing: {missing}")
    payload = "|".join(
        f"{path.relative_to(ROOT)}={_sha256(path)}" for path in V172_PARENT_FILES
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    v161_before = verify_v161(ROOT)
    v172_before = _v172_snapshot()

    acquisition = pd.read_csv(
        V171_OUTPUT / "acquisition_numerator_and_purchase_accounting_proof.csv",
        dtype={"target_cik": str, "target_accession": str, "adsh": str},
    )
    acquiree_nopat = pd.read_csv(
        V172_OUTPUT / "acquiree_net_income_to_nopat_reconciliation.csv"
    )
    historical = build_energen_historical_evidence(
        registry_path=ROOT / "configs" / "ep_v173_historical_deal_evidence.csv",
        fnsd_root=FNSD,
        companyfacts_root=COMPANYFACTS,
    )
    triangulation = build_nopat_triangulation(
        acquisition_proof=acquisition,
        acquiree_nopat=acquiree_nopat,
        historical_evidence=historical,
    )
    v172_reference = pd.read_csv(V172_OUTPUT / "cycle_normalization_reference.csv")
    v172_production = pd.read_csv(V172_OUTPUT / "cycle_production_evidence.csv")
    v172_cohorts = pd.read_csv(
        V172_OUTPUT / "reported_vs_cycle_normalized_deal_cohorts.csv"
    )
    v172_cycle_company_year = pd.read_csv(
        V172_OUTPUT / "cycle_normalized_company_year_panel.csv"
    )
    annual_organic = pd.read_csv(
        ROOT
        / "output"
        / "energy_valuation_v1_7_research"
        / "annual_organic_company_economics.csv"
    )
    attribution = build_normalization_attribution(
        fang_registry_path=ROOT
        / "configs"
        / "ep_v173_fang_historical_operating_data.csv",
        ir_root=IR,
        companyfacts_root=COMPANYFACTS,
        v172_reference=v172_reference,
        v172_production=v172_production,
        v172_cohorts=v172_cohorts,
        v172_cycle_company_year=v172_cycle_company_year,
        historical_evidence=historical,
        triangulation=triangulation,
        annual_organic=annual_organic,
        ttm_financial_path=ROOT
        / "output"
        / "energy_valuation_v1_1"
        / "ttm_financial_bridge_v1_1.parquet",
    )
    v172_gate = pd.read_csv(V172_OUTPUT / "v1_7_2_gate.csv")
    gate = build_v173_gate(
        triangulation=triangulation,
        annual_attribution=attribution["normalization_attribution_annual"],
        cohorts=attribution["normalization_attribution_cohorts"],
        validation=attribution["organic_roic_validation"],
        v172_gate=v172_gate,
    )
    artifacts = {
        "historical_energen_acquisition_evidence": historical,
        "nopat_route_triangulation": triangulation,
        **attribution,
        "v1_7_3_gate": gate,
    }
    for name, frame in artifacts.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)

    v161_after = verify_v161(ROOT)
    v172_after = _v172_snapshot()
    if v161_before["manifest_sha256"] != v161_after["manifest_sha256"]:
        raise RuntimeError("Frozen V1.6.1 changed during V1.7.3 research")
    if v172_before != v172_after:
        raise RuntimeError("V1.7.2 parent changed during V1.7.3 research")

    gate_row = gate.iloc[0]
    annual = attribution["normalization_attribution_annual"]
    source_checks = int(annual["source_cell_checks"].sum())
    source_passed = int(annual["source_cell_checks_passed"].sum())
    identity_max = float(
        annual["normalization_attribution_identity_error_usd"].abs().max()
    )
    metadata = {
        "version": "E&P_NORMALIZATION_ATTRIBUTION_NOPAT_TRIANGULATION_V1_7_3_RESEARCH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_6_1_manifest_sha256": v161_after["manifest_sha256"],
        "v1_7_2_parent_snapshot_sha256": v172_after,
        "frozen_v1_6_1_mutated": False,
        "v1_7_2_parent_mutated": False,
        "triangulation_tolerance_pct_predeclared": 10.0,
        "source_cell_checks": source_checks,
        "source_cell_checks_passed": source_passed,
        "normalization_identity_max_abs_error_usd": identity_max,
        "evidence_backed_nopat_bridge_deals": int(
            gate_row["evidence_backed_nopat_bridge_deals"]
        ),
        "two_route_nopat_triangulated_deals": int(
            gate_row["two_route_nopat_triangulated_deals"]
        ),
        "normalization_attribution_tickers": int(
            gate_row["normalization_attribution_tickers"]
        ),
        "independent_cost_normalized_cohort_tickers": int(
            gate_row["independent_cost_normalized_cohort_tickers"]
        ),
        "complete_3y_reported_cohort_tickers": int(
            gate_row["complete_3y_reported_cohort_tickers"]
        ),
        "complete_3y_cycle_normalized_cohort_tickers": int(
            gate_row["complete_3y_cycle_normalized_cohort_tickers"]
        ),
        "validated_organic_roic_tickers": int(
            gate_row["validated_organic_roic_tickers"]
        ),
        "research_gate": bool(gate_row["v1_7_3_research_gate"]),
        "research_freeze_eligible": bool(
            gate_row["v1_7_3_research_freeze_eligible"]
        ),
        "development_status": gate_row["development_status"],
        "terminal_anchor_replacement_allowed": False,
        "wacc_recalibrated": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    tri_view = triangulation[
        [
            "ticker",
            "fiscal_year",
            "event_name",
            "route_a_net_income_plus_after_tax_interest_usd",
            "route_b_operating_income_after_tax_usd",
            "route_a_b_symmetric_gap_pct",
            "two_route_nopat_triangulated",
            "evidence_backed_nopat_bridge_usd",
            "evidence_backed_acquisition_return_proxy_pct",
            "evidence_backed_nopat_bridge_semantics",
        ]
    ]
    annual_view = annual[
        [
            "ticker",
            "year",
            "actual_price_per_boe",
            "actual_unit_cost_per_boe",
            "normalized_price_per_boe",
            "normalized_unit_cost_per_boe",
            "accounting_scope_residual_usd",
            "price_normalization_effect_usd",
            "cost_normalization_effect_usd",
            "tax_normalization_effect_usd",
            "normalization_attribution_identity_error_usd",
            "normalization_confidence_grade",
        ]
    ]
    cohort = attribution["normalization_attribution_cohorts"]
    cohort_view = cohort.loc[
        cohort["cohort_offset"].eq(2),
        [
            "ticker",
            "event_name",
            "reported_cumulative_organic_roic_pct",
            "reported_economic_cumulative_organic_roic_pct",
            "price_only_normalized_cumulative_organic_roic_pct",
            "cost_only_normalized_cumulative_organic_roic_pct",
            "price_and_cost_normalized_cumulative_organic_roic_pct",
            "full_cycle_normalized_cumulative_organic_roic_pct",
            "methodology_attribution_complete",
            "independent_cost_normalized_cohort_complete",
            "reported_cohort_complete",
            "full_cycle_normalized_cohort_complete",
        ],
    ]
    validation_view = attribution["organic_roic_validation"][
        [
            "ticker",
            "fiscal_year",
            "event_name",
            "reported_3y_roic_pct",
            "cycle_normalized_3y_roic_pct",
            "acquisition_return_proxy_pct",
            "organic_company_roic_validated",
            "validation_status",
        ]
    ]
    report = f"""# E&P V1.7.3 normalization attribution and NOPAT triangulation

V1.7.3 is a child research layer of V1.7.2. Frozen V1.6.1 and the full
V1.7.2 parent snapshot are hash-verified before and after execution. No WACC,
terminal, scenario, parser, or production state is changed.

## Predeclared evidence rules

- Two-route NOPAT triangulation tolerance: symmetric absolute gap <= 10.0%.
- Grade A: independently sourced complete production and component cost scope.
- Grade B: accounting-proven partial cost scope; half weight.
- Grade C: hierarchical-implied cost; diagnostic only and zero sector weight.
- Organic validation requires a complete reported cohort, a complete independent
  full-cycle cohort, a triangulated NOPAT route, and an acquisition return.

## NOPAT route triangulation

{_markdown(tri_view)}

Energen adds a public-target same-period Route A/Route B observation. Its bridge
is a pre-deal target run-rate and is not substituted for post-close contribution.
Negative target NOPAT can still validate an accounting identity, but it is
separately barred from being interpreted as a positive economic run-rate.

## Annual normalization attribution

{_markdown(annual_view)}

The bridge is `reported GAAP NOPAT -> reported upstream economic NOPAT -> price
only -> cost only -> price+cost -> full cycle tax`. The accounting-scope residual
is explicit, so impairments, hedges, and non-upstream scope are not silently
mislabelled as commodity-price effects. The maximum bridge identity error is
{identity_max:,.6f} USD. Source-cell verification is {source_passed}/{source_checks}.

## Three-year attribution cohorts

{_markdown(cohort_view)}

DVN has a complete organic perimeter. FANG has complete independent price/cost
methodology evidence, but its 2019 asset sale lacks the disposed assets' operating
contribution. The disclosed $300m proceeds and $1m gain prove a $299m book-capital
bridge; they do not prove NOPAT. FANG therefore remains fail-closed for organic
cohort validation.

## Organic ROIC validation

{_markdown(validation_view)}

## Gate

{_markdown(gate)}

The infrastructure gate passes, but freeze remains deferred. Evidence-backed
NOPAT bridges, two-route triangulation, and independent-cost attribution coverage
reach their predeclared research targets. Complete organic three-year cohorts and
validated organic ROIC do not. Terminal replacement remains 0/14 and production
remains 0/20.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(tri_view.to_string(index=False))
    print(cohort_view.to_string(index=False))
    print(validation_view.to_string(index=False))
    print(gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
