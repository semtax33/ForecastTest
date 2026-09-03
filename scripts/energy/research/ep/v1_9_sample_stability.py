from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v174.benchmark import verify_v174
from energy_nowcast.research.ep_v19 import (
    build_expanded_company_ranges,
    build_expanded_distribution,
    build_expanded_loco,
    build_range_width_attribution,
    build_rrc_annual_evidence,
    build_rrc_candidate_audit,
    build_rrc_clean_organic_cohort,
    build_rrc_normalization_evidence,
    build_stability_comparison,
    build_v19_gate,
    v18_parent_snapshot,
)


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
ARCANA = ROOT.parent / "Arcana"
FNSD = ARCANA / "data-lake" / "bronze" / "sec" / "financial-statement-and-notes-data-set"
V18_OUTPUT = ROOT / "output" / "energy_valuation_v1_8_research"
V174_OUTPUT = ROOT / "output" / "energy_valuation_v1_7_4_research"
OUTPUT = ROOT / "output" / "energy_valuation_v1_9_research"


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    parent_before = v18_parent_snapshot(ROOT)
    v174_before = verify_v174(ROOT)

    annual_organic = pd.read_csv(
        ROOT / "output/energy_valuation_v1_7_research/annual_organic_company_economics.csv"
    )
    ttm_financial = pd.read_parquet(
        ROOT / "output/energy_valuation_v1_1/ttm_financial_bridge_v1_1.parquet"
    )
    cycle_reference = pd.read_csv(
        ROOT / "output/energy_valuation_v1_7_2_research/cycle_normalization_reference.csv"
    )
    width_policy = pd.read_csv(ROOT / "configs/ep_v18_distribution_policy.csv")
    v18_ranges = pd.read_csv(V18_OUTPUT / "company_organic_roic_ranges.csv")
    v18_distribution = pd.read_csv(
        V18_OUTPUT / "through_cycle_roic_distribution.csv"
    )
    v18_loco = pd.read_csv(V18_OUTPUT / "leave_one_cohort_out_robustness.csv")
    closed_cohorts = pd.read_csv(V174_OUTPUT / "closed_three_year_cohorts.csv")

    rrc_evidence = build_rrc_annual_evidence(
        source_registry_path=ROOT / "configs/ep_v19_rrc_sources.csv",
        fnsd_root=FNSD,
        companyfacts_path=(
            ARCANA / "data-lake/bronze/sec/companyfacts/CIK0000315852.json"
        ),
        ttm_financial=ttm_financial,
    )
    candidate_audit = build_rrc_candidate_audit(
        annual_organic=annual_organic,
        annual_evidence=rrc_evidence,
    )
    rrc_normalization = build_rrc_normalization_evidence(
        annual_evidence=rrc_evidence,
        candidate_audit=candidate_audit,
        cycle_reference=cycle_reference,
    )
    rrc_cohort = build_rrc_clean_organic_cohort(
        candidate_audit=candidate_audit,
        normalization_evidence=rrc_normalization,
        annual_organic=annual_organic,
    )
    width_attribution, component_attribution = build_range_width_attribution(
        closed_cohorts=closed_cohorts,
        v18_company_ranges=v18_ranges,
    )
    expanded_ranges = build_expanded_company_ranges(
        v18_company_ranges=v18_ranges,
        rrc_cohort=rrc_cohort,
        width_policy=width_policy,
    )
    expanded_distribution = build_expanded_distribution(
        company_ranges=expanded_ranges
    )
    expanded_loco = build_expanded_loco(
        company_ranges=expanded_ranges,
        distribution=expanded_distribution,
    )
    stability = build_stability_comparison(
        v18_distribution=v18_distribution,
        v18_loco=v18_loco,
        v19_distribution=expanded_distribution,
        v19_loco=expanded_loco,
    )
    gate = build_v19_gate(
        parent_v18_verified=True,
        candidate_audit=candidate_audit,
        rrc_cohort=rrc_cohort,
        company_ranges=expanded_ranges,
        distribution=expanded_distribution,
        loco=expanded_loco,
        width_attribution=width_attribution,
    )
    artifacts = {
        "rrc_clean_window_candidate_audit": candidate_audit,
        "rrc_annual_source_evidence": rrc_evidence,
        "rrc_selected_normalization_evidence": rrc_normalization,
        "rrc_clean_organic_cohort": rrc_cohort,
        "dvn_fang_range_width_attribution": width_attribution,
        "range_width_component_attribution": component_attribution,
        "expanded_company_organic_roic_ranges": expanded_ranges,
        "expanded_through_cycle_roic_distribution": expanded_distribution,
        "expanded_leave_one_cohort_out_robustness": expanded_loco,
        "sample_stability_comparison": stability,
        "v1_9_gate": gate,
    }
    for name, frame in artifacts.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)

    parent_after = v18_parent_snapshot(ROOT)
    v174_after = verify_v174(ROOT)
    if parent_before["snapshot_sha256"] != parent_after["snapshot_sha256"]:
        raise RuntimeError("V1.8 parent changed during V1.9 research")
    if v174_before["manifest_sha256"] != v174_after["manifest_sha256"]:
        raise RuntimeError("Frozen V1.7.4 changed during V1.9 research")

    selected = candidate_audit.loc[candidate_audit["selected_for_v19"]]
    mature = rrc_cohort.loc[rrc_cohort["cohort_offset"].eq(2)]
    distribution_row = expanded_distribution.iloc[0]
    stability_row = stability.iloc[0]
    gate_row = gate.iloc[0]
    metadata = {
        "version": "E&P_SAMPLE_STABILITY_UNCERTAINTY_DECOMPOSITION_V1_9_RESEARCH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_8_parent_snapshot_sha256": parent_after["snapshot_sha256"],
        "v1_8_parent_verified_files": parent_after["verified_files"],
        "v1_8_parent_mutated": False,
        "v1_7_4_manifest_sha256": v174_after["manifest_sha256"],
        "v1_7_4_parent_mutated": False,
        "selected_fourth_cohort": "RRC_2022_2024",
        "outcome_values_used_for_selection": False,
        "cohort_count": int(gate_row["cohort_count"]),
        "group_count": int(gate_row["group_count"]),
        "strong_or_usable_range_count": int(
            gate_row["strong_or_usable_range_count"]
        ),
        "effective_weighted_cohort_count": float(
            gate_row["effective_weighted_cohort_count"]
        ),
        "midpoint_p25_pct": float(distribution_row["midpoint_p25_pct"]),
        "midpoint_p50_pct": float(distribution_row["midpoint_p50_pct"]),
        "midpoint_p75_pct": float(distribution_row["midpoint_p75_pct"]),
        "max_abs_loco_p50_shift_pct_points": float(
            gate_row["max_abs_loco_p50_shift_pct_points"]
        ),
        "max_abs_loco_improvement_pct_points": float(
            stability_row["max_abs_loco_improvement_pct_points"]
        ),
        "sample_stability_issue_resolved": bool(
            gate_row["sample_stability_issue_resolved"]
        ),
        "uncertainty_decomposition_issue_resolved": bool(
            gate_row["uncertainty_decomposition_issue_resolved"]
        ),
        "research_freeze_eligible": bool(
            gate_row["v1_9_research_freeze_eligible"]
        ),
        "research_frozen": False,
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

    report = f"""# E&P V1.9 sample-stability and uncertainty-decomposition research

V1.9 is a child research layer of V1.8. It hashes 19 V1.8 source, policy,
test, and output files before and after execution and independently verifies
the frozen V1.7.4 manifest. Neither parent is modified.

## Outcome-blind fourth-cohort selection

{_markdown(candidate_audit)}

The research cutoff is fixed at 2025-03-01. Selection uses direct source
coverage, a single-operating-segment proof, business-transaction perimeter,
an exact reserve roll-forward, the unchanged 2% reserve-event threshold, and
a positive cumulative organic-capital denominator. It chooses the latest
eligible window and never reads a ROIC level or range width. RRC 2022-2024 is
therefore selected before its outcomes are opened.

## RRC direct source evidence

{_markdown(rrc_evidence[[
    'year', 'revenue_usd', 'cost_and_expense_usd', 'income_before_tax_usd',
    'income_identity_error_usd', 'production_mboe', 'end_reserves_mmcfe',
    'purchases_identity_mmcfe', 'sales_identity_mmcfe',
    'reserve_rollforward_identity_error_mmcfe', 'reserve_event_ratio',
    'effective_tax_rate', 'tax_rate_method',
    'single_operating_segment_phrase_proven', 'source_cells_fully_verified',
]])}

Revenue, cost, and pretax-income cells are re-read from the SEC companyfacts
source. Reserve cells and the one-operating-segment statement are retained in
the curated local FNSD gold registry with accession, tag, and dimension scope.
The net reserve transaction is reported as a stock-flow balancing item rather
than falsely labelled a directly disclosed purchase or sale. RRC explicitly
reports one operating segment, so consolidated revenues and all costs and
expenses form the complete company operating scope.

## RRC selected cohort

{_markdown(mature)}

## Expanded company ranges

{_markdown(expanded_ranges)}

## DVN/FANG range-width attribution

{_markdown(width_attribution)}

The decomposition is a signed path from reported economics through price,
cost, and tax normalization, plus bounded accounting-perimeter endpoint
stress. Negative contributions are offsets, not negative uncertainty.
Denominator contribution is zero because both cohorts retain one fixed,
validated denominator. The component sum exactly reproduces each observed
range width.

## Four-cohort descriptive distribution

{_markdown(expanded_distribution)}

This remains an empirical research diagnostic, not a posterior distribution
and not a normal-ROIC estimate.

## Leave-one-cohort-out robustness

{_markdown(expanded_loco)}

## Stability improvement

{_markdown(stability)}

## Research gate

{_markdown(gate)}

The unchanged V1.8 freeze criteria are used: at least two Strong/Usable ranges
and a maximum leave-one-cohort-out P50 shift of 10 percentage points. Passing
these criteria makes V1.9 freeze-eligible, not automatically frozen. Terminal
replacement is unconditionally outside V1.9 authority, WACC is unchanged, and
production remains locked at 0/20.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(selected.to_string(index=False))
    print(mature.to_string(index=False))
    print(width_attribution.to_string(index=False))
    print(expanded_ranges.to_string(index=False))
    print(expanded_distribution.to_string(index=False))
    print(expanded_loco.to_string(index=False))
    print(stability.to_string(index=False))
    print(gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
