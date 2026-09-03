from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161
from energy_nowcast.research.ep_v174 import (
    build_closed_three_year_cohorts,
    build_dvn_nopat_discrepancy_reconciliation,
    build_fang_divestiture_nopat_range,
    build_fang_transaction_perimeter_evidence,
    build_organic_roic_validation_ranges,
    build_scope_adjusted_triangulation,
    build_v174_gate,
)


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
ARCANA = ROOT.parent / "Arcana"
COMPANYFACTS = ARCANA / "data-lake" / "bronze" / "sec" / "companyfacts"
IR = ARCANA / "data-lake" / "bronze" / "sec" / "fillings" / "ir"
V173_OUTPUT = ROOT / "output" / "energy_valuation_v1_7_3_research"
OUTPUT = ROOT / "output" / "energy_valuation_v1_7_4_research"

V173_PARENT_FILES = (
    ROOT / "energy_nowcast" / "research" / "ep_v173" / "__init__.py",
    ROOT / "energy_nowcast" / "research" / "ep_v173" / "triangulation.py",
    ROOT / "energy_nowcast" / "research" / "ep_v173" / "attribution.py",
    ROOT / "energy_nowcast" / "research" / "ep_v173" / "gate.py",
    ROOT / "scripts/energy/research/ep/v1_7_3_normalization_attribution.py",
    ROOT / "tests" / "test_ep_normalization_attribution_nopat_triangulation_v1_7_3.py",
    ROOT / "configs" / "ep_v173_historical_deal_evidence.csv",
    ROOT / "configs" / "ep_v173_fang_historical_operating_data.csv",
    V173_OUTPUT / "historical_energen_acquisition_evidence.csv",
    V173_OUTPUT / "nopat_route_triangulation.csv",
    V173_OUTPUT / "normalization_confidence_policy.csv",
    V173_OUTPUT / "normalization_confidence_by_ticker.csv",
    V173_OUTPUT / "independent_cost_annual_evidence.csv",
    V173_OUTPUT / "normalization_attribution_annual.csv",
    V173_OUTPUT / "normalization_attribution_cohorts.csv",
    V173_OUTPUT / "organic_roic_validation.csv",
    V173_OUTPUT / "v1_7_3_gate.csv",
    V173_OUTPUT / "metadata.json",
    V173_OUTPUT / "report.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _v173_snapshot() -> str:
    missing = [str(path) for path in V173_PARENT_FILES if not path.exists()]
    if missing:
        raise FileNotFoundError(f"V1.7.3 parent artifacts missing: {missing}")
    payload = "|".join(
        f"{path.relative_to(ROOT)}={_sha256(path)}" for path in V173_PARENT_FILES
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    v161_before = verify_v161(ROOT)
    v173_before = _v173_snapshot()

    parent_triangulation = pd.read_csv(V173_OUTPUT / "nopat_route_triangulation.csv")
    parent_cohorts = pd.read_csv(V173_OUTPUT / "normalization_attribution_cohorts.csv")
    annual_attribution = pd.read_csv(
        V173_OUTPUT / "normalization_attribution_annual.csv"
    )
    historical_energen = pd.read_csv(
        V173_OUTPUT / "historical_energen_acquisition_evidence.csv"
    )
    parent_gate = pd.read_csv(V173_OUTPUT / "v1_7_3_gate.csv")

    fang_evidence = build_fang_transaction_perimeter_evidence(
        registry_path=ROOT
        / "configs"
        / "ep_v174_transaction_perimeter_evidence.csv",
        ir_root=IR,
    )
    fang_perimeter = build_fang_divestiture_nopat_range(
        evidence=fang_evidence,
        historical_energen=historical_energen,
        parent_cohorts=parent_cohorts,
    )
    dvn_reconciliation = build_dvn_nopat_discrepancy_reconciliation(
        companyfacts_root=COMPANYFACTS,
        parent_triangulation=parent_triangulation,
    )
    adjusted_triangulation = build_scope_adjusted_triangulation(
        parent_triangulation=parent_triangulation,
        reconciliation=dvn_reconciliation,
    )
    closed_cohorts = build_closed_three_year_cohorts(
        parent_cohorts=parent_cohorts,
        annual_attribution=annual_attribution,
        fang_perimeter=fang_perimeter,
    )
    validation = build_organic_roic_validation_ranges(
        closed_cohorts=closed_cohorts,
        adjusted_triangulation=adjusted_triangulation,
    )
    gate = build_v174_gate(
        parent_gate=parent_gate,
        closed_cohorts=closed_cohorts,
        validation=validation,
        adjusted_triangulation=adjusted_triangulation,
    )

    artifacts = {
        "fang_transaction_perimeter_evidence": fang_evidence,
        "fang_divestiture_nopat_range": fang_perimeter,
        "dvn_nopat_discrepancy_reconciliation": dvn_reconciliation,
        "scope_adjusted_nopat_triangulation": adjusted_triangulation,
        "closed_three_year_cohorts": closed_cohorts,
        "organic_roic_validation_ranges": validation,
        "v1_7_4_gate": gate,
    }
    for name, frame in artifacts.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)

    v161_after = verify_v161(ROOT)
    v173_after = _v173_snapshot()
    if v161_before["manifest_sha256"] != v161_after["manifest_sha256"]:
        raise RuntimeError("Frozen V1.6.1 changed during V1.7.4 research")
    if v173_before != v173_after:
        raise RuntimeError("V1.7.3 parent changed during V1.7.4 research")

    gate_row = gate.iloc[0]
    source_checks = int(len(fang_evidence)) + int(
        dvn_reconciliation.iloc[0]["source_cell_checks"]
    )
    source_passed = int(fang_evidence["source_check_passed"].sum()) + int(
        dvn_reconciliation.iloc[0]["source_cell_checks_passed"]
    )
    metadata = {
        "version": "E&P_COHORT_CLOSURE_ORGANIC_ROIC_VALIDATION_V1_7_4_RESEARCH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_6_1_manifest_sha256": v161_after["manifest_sha256"],
        "v1_7_3_parent_snapshot_sha256": v173_after,
        "frozen_v1_6_1_mutated": False,
        "v1_7_3_parent_mutated": False,
        "triangulation_tolerance_pct_predeclared": 10.0,
        "source_cell_checks": source_checks,
        "source_cell_checks_passed": source_passed,
        "complete_reported_3y_cohort_tickers": int(
            gate_row["complete_reported_3y_cohort_tickers"]
        ),
        "complete_independent_full_cycle_cohort_tickers": int(
            gate_row["complete_independent_full_cycle_cohort_tickers"]
        ),
        "triangulated_nopat_validated_cohort_tickers": int(
            gate_row["triangulated_nopat_validated_cohort_tickers"]
        ),
        "validated_organic_roic_tickers": int(
            gate_row["validated_organic_roic_tickers"]
        ),
        "unresolved_material_transaction_perimeters": int(
            gate_row["unresolved_material_transaction_perimeters"]
        ),
        "research_freeze_eligible": bool(
            gate_row["v1_7_4_research_freeze_eligible"]
        ),
        "development_status": gate_row["development_status"],
        "normal_roic_claimed": False,
        "terminal_anchor_replacement_allowed": False,
        "wacc_recalibrated": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    fang_view = fang_perimeter[
        [
            "asset_total_production_low_mboe_per_day",
            "asset_total_production_high_mboe_per_day",
            "asset_loe_per_boe_low",
            "asset_loe_per_boe_high",
            "after_tax_unit_margin_low",
            "after_tax_unit_margin_high",
            "missing_after_tax_operating_contribution_low_usd",
            "missing_after_tax_operating_contribution_high_usd",
            "energen_incremental_production_low_mboe",
            "energen_incremental_production_high_mboe",
            "material_transaction_perimeter_resolved",
        ]
    ]
    dvn_view = dvn_reconciliation[
        [
            "headline_route_a_usd",
            "headline_route_b_usd",
            "headline_route_gap_pct",
            "noncontrolling_scope_adjustment_annualized_usd",
            "discontinued_operations_scope_adjustment_annualized_usd",
            "scope_adjusted_route_a_usd",
            "scope_adjusted_route_b_usd",
            "scope_adjusted_route_gap_pct",
            "nonoperating_residual_after_tax_annualized_usd",
            "unexplained_difference_usd",
            "scope_adjusted_two_route_triangulated",
        ]
    ]
    mature = closed_cohorts.loc[
        closed_cohorts["cohort_offset"].eq(2),
        [
            "ticker",
            "event_name",
            "v174_reported_organic_nopat_cumulative_roic_low_pct",
            "v174_reported_organic_nopat_cumulative_roic_high_pct",
            "v174_reported_economic_organic_nopat_cumulative_roic_low_pct",
            "v174_reported_economic_organic_nopat_cumulative_roic_high_pct",
            "v174_full_cycle_normalized_organic_nopat_cumulative_roic_low_pct",
            "v174_full_cycle_normalized_organic_nopat_cumulative_roic_high_pct",
            "v174_reported_3y_cohort_complete",
            "v174_independent_full_cycle_3y_cohort_complete",
            "material_transaction_perimeter_resolved",
        ],
    ]
    report = f"""# E&P V1.7.4 cohort closure and organic ROIC validation

V1.7.4 is a child research layer of V1.7.3. Frozen V1.6.1 and the full V1.7.3
parent snapshot are hash-verified before and after execution. The predeclared
two-route tolerance remains 10%. No WACC, terminal, scenario, parser, or
production state is changed.

## FANG-Energen transaction-perimeter closure

{_markdown(fang_view)}

The 2018 Energen 9M production observation is annualized from 26,709 MBOE over
273 days. The 2019 divestiture is bounded from the company's approximately
6.5 MBOE/d total and 5.8 MBbl/d oil disclosures. Approximate production figures
are widened by 0.05 MBOE/d before calculating the range. The sold assets'
company-wide LOE contribution, actual product prices, production tax, gathering,
and depletion guidance produce a disclosure-bounded missing after-tax operating
contribution. It is not represented as directly disclosed NOPAT.
This is a retrospective transaction-perimeter validation and is not represented
as information available at the 2018 deal date.

## DVN-WPX NOPAT discrepancy reconciliation

{_markdown(dvn_view)}

The original Route A used parent-attributable net income containing discontinued
operations, while Route B used consolidated continuing operating income. Moving
Route A to consolidated continuing scope explains the material difference. The
remaining gap equals the independently reconstructed after-tax non-operating
residual. The $967m YTD oil-and-gas impairment is present in both continuing
operations routes and is therefore not a route-gap adjustment.

## Closed three-year cohorts

{_markdown(mature)}

## Validated company organic ROIC research ranges

{_markdown(validation)}

Reported GAAP is retained as an accounting-stress endpoint. The economically
comparable range spans reported upstream economics and independent full-cycle
economics. Neither endpoint, midpoint, nor the range is called normal ROIC, and
none is eligible for terminal input.

## Freeze gate

{_markdown(gate)}

The research freeze gate requires two complete reported cohorts, two complete
independent full-cycle cohorts, two cohort tickers with NOPAT triangulation, two
validated company organic ROIC ranges, zero unresolved material transaction
perimeters, and a locked terminal replacement state.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(fang_view.to_string(index=False))
    print(dvn_view.to_string(index=False))
    print(validation.to_string(index=False))
    print(gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
