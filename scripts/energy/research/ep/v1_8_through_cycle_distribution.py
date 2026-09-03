from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v174.benchmark import verify_v174
from energy_nowcast.research.ep_v18 import (
    build_ar_clean_organic_cohort,
    build_ar_segment_evidence,
    build_company_roic_ranges,
    build_gas_candidate_audit,
    build_leave_one_cohort_out,
    build_three_level_comparison,
    build_through_cycle_distribution,
    build_v18_gate,
)


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
ARCANA = ROOT.parent / "Arcana"
FNSD = ARCANA / "data-lake" / "bronze" / "sec" / "financial-statement-and-notes-data-set"
V174_OUTPUT = ROOT / "output" / "energy_valuation_v1_7_4_research"
OUTPUT = ROOT / "output" / "energy_valuation_v1_8_research"


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    parent_before = verify_v174(ROOT)

    annual_organic = pd.read_csv(
        ROOT / "output/energy_valuation_v1_7_research/annual_organic_company_economics.csv"
    )
    unit_economics = pd.read_csv(
        ROOT / "output/energy_valuation_v1_3_research/annual_unit_economics_panel.csv"
    )
    cycle_reference = pd.read_csv(
        ROOT / "output/energy_valuation_v1_7_2_research/cycle_normalization_reference.csv"
    )
    ttm_financial = pd.read_parquet(
        ROOT / "output/energy_valuation_v1_1/ttm_financial_bridge_v1_1.parquet"
    )
    candidate_audit = build_gas_candidate_audit(
        annual_organic=annual_organic,
        unit_economics=unit_economics,
    )
    ar_evidence = build_ar_segment_evidence(
        source_registry_path=ROOT / "configs/ep_v18_ar_segment_sources.csv",
        fnsd_root=FNSD,
        unit_economics=unit_economics,
        ttm_financial=ttm_financial,
        cycle_reference=cycle_reference,
    )
    ar_cohort = build_ar_clean_organic_cohort(
        candidate_audit=candidate_audit,
        segment_evidence=ar_evidence,
        annual_organic=annual_organic,
    )
    width_policy = pd.read_csv(ROOT / "configs/ep_v18_distribution_policy.csv")
    v174_validation = pd.read_csv(
        V174_OUTPUT / "organic_roic_validation_ranges.csv"
    )
    company_ranges = build_company_roic_ranges(
        v174_validation=v174_validation,
        ar_cohort=ar_cohort,
        width_policy=width_policy,
    )
    acquisition_routes = pd.read_csv(
        V174_OUTPUT / "scope_adjusted_nopat_triangulation.csv"
    )
    three_level = build_three_level_comparison(
        company_ranges=company_ranges,
        three_level_parent=pd.read_csv(
            ROOT / "output/energy_valuation_v1_6_research/three_level_roic_summary.csv"
        ),
        acquisition_routes=acquisition_routes,
    )
    distribution = build_through_cycle_distribution(
        company_ranges=company_ranges
    )
    loco = build_leave_one_cohort_out(
        company_ranges=company_ranges,
        full_distribution=distribution,
    )
    width_gate = company_ranges[
        [
            "ticker",
            "group",
            "roic_range_width_pct",
            "range_width_category",
            "range_width_research_weight",
            "range_width_gate_pass",
            "accounting_confidence_grade",
            "company_confidence_weight",
            "terminal_input_allowed",
        ]
    ].copy()
    gate = build_v18_gate(
        parent_v174_verified=True,
        company_ranges=company_ranges,
        gas_cohort=ar_cohort,
        distribution=distribution,
        loco=loco,
        three_level_comparison=three_level,
    )
    artifacts = {
        "gas_heavy_candidate_audit": candidate_audit,
        "ar_segment_annual_evidence": ar_evidence,
        "ar_clean_organic_cohort": ar_cohort,
        "company_organic_roic_ranges": company_ranges,
        "three_level_roic_comparison": three_level,
        "through_cycle_roic_distribution": distribution,
        "leave_one_cohort_out_robustness": loco,
        "roic_range_width_gate": width_gate,
        "v1_8_gate": gate,
    }
    for name, frame in artifacts.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)

    parent_after = verify_v174(ROOT)
    if parent_before["manifest_sha256"] != parent_after["manifest_sha256"]:
        raise RuntimeError("Frozen V1.7.4 changed during V1.8 research")

    gate_row = gate.iloc[0]
    distribution_row = distribution.iloc[0]
    metadata = {
        "version": "E&P_THROUGH_CYCLE_ORGANIC_ROIC_DISTRIBUTION_V1_8_RESEARCH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_7_4_parent_manifest_sha256": parent_after["manifest_sha256"],
        "v1_7_4_parent_mutated": False,
        "cohort_count": int(gate_row["cohort_count"]),
        "group_count": int(gate_row["group_count"]),
        "validated_company_research_ranges": int(
            gate_row["validated_company_research_ranges"]
        ),
        "strong_or_usable_range_count": int(
            gate_row["strong_or_usable_range_count"]
        ),
        "too_uncertain_range_count": int(
            gate_row["too_uncertain_range_count"]
        ),
        "midpoint_p25_pct": float(distribution_row["midpoint_p25_pct"]),
        "midpoint_p50_pct": float(distribution_row["midpoint_p50_pct"]),
        "midpoint_p75_pct": float(distribution_row["midpoint_p75_pct"]),
        "max_abs_loco_p50_shift_pct_points": float(
            gate_row["max_abs_loco_p50_shift_pct_points"]
        ),
        "research_gate": bool(gate_row["v1_8_research_gate"]),
        "research_freeze_eligible": bool(
            gate_row["v1_8_research_freeze_eligible"]
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

    selected_audit = candidate_audit.loc[candidate_audit["selected_for_v18"]]
    mature_ar = ar_cohort.loc[ar_cohort["cohort_offset"].eq(2)]
    report = f"""# E&P V1.8 through-cycle organic ROIC distribution research

V1.8 is a child research layer of frozen V1.7.4. The parent manifest is
verified before and after execution. No V1.7.4 file, V1.1 terminal assumption,
WACC, scenario, parser, or production state is changed.

## Deterministic gas-heavy cohort selection

{_markdown(selected_audit)}

The selection rule uses evidence coverage, transaction perimeter, reserve-event
materiality, and a positive cumulative invested-capital denominator only. It
does not use ROIC outcome values. AR 2022-2024 is the sole eligible gas-heavy
window. It is a clean organic window rather than an acquisition cohort, so
target NOPAT triangulation is explicitly not applicable.

## AR direct E&P segment evidence

{_markdown(ar_evidence[[
    'year', 'production_mboe', 'segment_revenue_usd',
    'segment_cost_and_expense_usd', 'segment_operating_income_usd',
    'segment_accounting_identity_error_usd', 'actual_price_per_boe',
    'actual_complete_segment_unit_cost_per_boe', 'normalized_price_per_boe',
    'normalized_complete_segment_unit_cost_per_boe',
    'normalization_attribution_identity_error_usd',
    'source_cells_fully_verified',
]])}

The direct segment route includes every operating cost reported within AR's E&P
segment, including gathering, processing, transportation, production taxes,
G&A, DD&A, impairment, and other reported operating items. It therefore closes
the transport/tax scope that prevented the earlier hierarchical gas route from
receiving independent-data confidence.

## AR clean three-year cohort

{_markdown(mature_ar[[
    'ticker', 'cohort_start_year', 'cohort_end_year',
    'cumulative_organic_invested_capital_proxy_usd',
    'reported_gaap_nopat_cumulative_roic_pct',
    'reported_economic_nopat_cumulative_roic_pct',
    'full_cycle_normalized_nopat_cumulative_roic_pct',
    'organic_company_roic_validated',
]])}

## Company research ranges and width policy

{_markdown(company_ranges)}

Width categories are fixed at less than 15 percentage points for Strong, 15 to
less than 30 for Usable Research, and 30 or more for Too Uncertain for Terminal.
The confidence-weighted results remain descriptive empirical cohort statistics,
not a posterior distribution and not a normal-ROIC estimate.

## Through-cycle descriptive distribution

{_markdown(distribution)}

## Leave-one-cohort-out robustness

{_markdown(loco)}

## Project / reserve / acquisition / company comparison

{_markdown(three_level)}

## Research and freeze gate

{_markdown(gate)}

Descriptive oil/mixed/gas pooling is now possible. Research freeze remains
locked unless at least two ranges pass the width gate and every
leave-one-cohort-out P50 shift stays within 10 percentage points. Terminal use
is unconditionally locked in V1.8; a separately reported terminal-evidence
diagnostic cannot grant application authority.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(company_ranges.to_string(index=False))
    print(distribution.to_string(index=False))
    print(loco.to_string(index=False))
    print(gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
