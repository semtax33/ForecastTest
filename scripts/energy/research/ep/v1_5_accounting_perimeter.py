from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.research.ep_v14.benchmark import verify_v14
from energy_nowcast.research.ep_v15.perimeter import build_accounting_perimeter_research
from energy_nowcast.research.ep_v15.reserve_cost import (
    build_reserve_coverage_and_cost_research,
)
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output" / "energy_valuation_v1_5_research"
ARCANA = ROOT.parent / "Arcana"
COMPANYFACTS = ARCANA / "data-lake" / "bronze" / "sec" / "companyfacts"


def _verify_parents() -> dict[str, dict[str, object]]:
    return {
        "v1": verify_v1(ROOT),
        "v11": verify_v11(ROOT),
        "v12": verify_v12(ROOT),
        "v13": verify_v13(ROOT),
        "v14": verify_v14(ROOT),
    }


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    parents_before = _verify_parents()
    perimeter = build_accounting_perimeter_research(
        v13_annual_path=(
            ROOT / "output/energy_valuation_v1_3_research/annual_unit_economics_panel.csv"
        ),
        v14_cost_panel_path=(
            ROOT / "output/energy_valuation_v1_4_research/annual_cost_scope_panel.csv"
        ),
        v14_cross_path=(
            ROOT / "output/energy_valuation_v1_4_research/expanded_core_cross_check.csv"
        ),
        consolidated_financial_path=(
            ROOT / "output/energy_valuation_v1_1/quarterly_financial_bridge_v1_1.parquet"
        ),
    )
    reserve = build_reserve_coverage_and_cost_research(
        companyfacts_root=COMPANYFACTS,
        production_path=ROOT / "output/v3_5_2_clean_component/production_actuals.csv",
        v13_coverage_path=ROOT / "output/energy_valuation_v1_3_research/data_coverage.csv",
        v13_cross_path=(
            ROOT / "output/energy_valuation_v1_3_research/unit_economics_cross_check.csv"
        ),
        v14_cross_path=(
            ROOT / "output/energy_valuation_v1_4_research/expanded_core_cross_check.csv"
        ),
        v14_basis_path=(
            ROOT / "output/energy_valuation_v1_4_research/annual_realized_basis_panel.csv"
        ),
    )
    artifacts = {**perimeter, **reserve}
    for name, frame in artifacts.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)

    perimeter_summary = perimeter["accounting_perimeter_reconciliation_summary"]
    coverage = reserve["reserve_coverage_summary"]
    roic = reserve["reserve_roic_scope_cross_check"]
    mix = reserve["production_mix_coverage"]
    core = roic.loc[roic["ticker"].isin(["AR", "CNX", "FANG"])]
    core_perimeter = perimeter_summary.loc[
        perimeter_summary["ticker"].isin(["AR", "CNX", "FANG"])
    ]
    ready_count = int(coverage["route_aware_reserve_chain_ready"].sum())
    perimeter_pass = int(
        perimeter_summary["accounting_perimeter_reconciliation_gate"].eq(
            "PASS_RESEARCH_PERIMETER_RECONCILIATION"
        ).sum()
    )
    all_in_ready = int(
        roic["roic_scope_status"].eq(
            "OBSERVED_DEV_EXPLORATION_ACQUISITION_SCOPE_NOT_FULL_COMPANY_INCREMENTAL_ROIC"
        ).sum()
    )
    company_roic_below_100 = int(
        pd.to_numeric(
            roic["company_scope_all_in_reserve_roic_proxy_q50_pct"],
            errors="coerce",
        ).lt(100.0).sum()
    )
    actual_mix_ready = int(mix["actual_mix_ready"].sum())
    gate = pd.DataFrame(
        [{
            "ep_tickers": 14,
            "accounting_perimeter_reconciliation_pass_tickers": perimeter_pass,
            "route_aware_reserve_chain_ready_tickers": ready_count,
            "reserve_coverage_target_tickers": 8,
            "reserve_coverage_target_met": ready_count >= 8,
            "all_in_reserve_cost_roic_cross_check_tickers": all_in_ready,
            "company_scope_roic_below_100pct_tickers": company_roic_below_100,
            "actual_three_component_production_mix_ready_tickers": actual_mix_ready,
            "company_incremental_roic_validated_tickers": 0,
            "terminal_anchor_ready_tickers": 0,
            "terminal_anchor_replacement_allowed": False,
            "wacc_range_recalibrated": False,
            "v1_1_mutation_allowed": False,
            "risk_channel_duplicate_count": 0,
            "production_eligible": False,
            "live_matched_observations": "0/20",
        }]
    )
    gate.to_csv(OUTPUT / "v1_5_gate.csv", index=False)

    wacc = pd.read_csv(
        ROOT / "output/energy_valuation_v1_3_research/wacc_reference_summary.csv"
    ).iloc[0]
    report = f"""# E&P V1.5 accounting-perimeter and reserve-coverage research

V1.5 is a research-only child of frozen V1.4. It verifies V1.0 through V1.4
before and after execution. It does not change frozen cash-flow assumptions,
the independent WACC range, terminal economics, scenario weights, or parser
semantics.

## Accounting-perimeter reconciliation gate

{_markdown(core_perimeter)}

Annual reconstructed upstream margin is compared with the same-year
consolidated EBIT margin. Provisional row grades are green at an absolute gap
of at most 5 percentage points, yellow above 5 through 10, and red above 10.
A company pass additionally requires complete standardized cost scope, at
least three comparable years, red-year share no greater than 25%, and median
upstream/consolidated revenue coverage between 90% and 110%.
Even a numeric pass remains locked when the frozen V1.4 diagnostic shows a
strong exact-hedge association whose revenue presentation is not proven.

Reported hedge gain/loss is shown under alternative accounting-presentation
hypotheses, but no hedge adjustment is applied. The lower-gap presentation is
diagnostic only and cannot prove where the hedge sits in reported revenue.

## Route-aware reserve coverage

{_markdown(coverage)}

The route-aware extractor selects the earliest original 10-K fact by year and
can fall back from the Energy reserve tags to the equivalent generic reserve
tags. Every production quantity is independently calibrated to the audited
annual production KPI. The result expands research-ready chains from 3/14 to
{ready_count}/14, still below the explicit 8/14 sector-coverage target.

## Project versus broader company-scope reserve ROIC

{_markdown(core)}

Project ROIC uses development cost per added BOE. The broader proxy uses
observed development, exploration, and proved/unproved acquisition costs per
gross organic plus purchased reserve additions. It still does not prove full
leasehold, infrastructure, corporate capital, dry-hole overlap, or acquisition
premium scope, so it is not labelled company incremental ROIC.

## Production-mix coverage

{_markdown(mix.loc[mix['ticker'].isin(['AR', 'CNX', 'FANG'])])}

FANG remains group-prior allocated for NGL and gas. CNX uses one residual
component. Only AR has fully audited oil/NGL/gas mix across the recent window.

## Research gate

{_markdown(gate)}

- Frozen independent WACC range remains approximately
  {float(wacc['symmetric_return_wacc_median_pct']):.2f}% to
  {float(wacc['downside_return_wacc_median_pct']):.2f}%.
- WACC recalibration: prohibited.
- Terminal economics replacement: locked at 0/14.
- Hormuz: cash-flow regime overlay only, no WACC premium.
- Production: locked at 0/20 matched live observations.

These outputs are research diagnostics and not investment recommendations.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    parents_after = _verify_parents()
    for key in parents_before:
        if parents_before[key]["manifest_sha256"] != parents_after[key]["manifest_sha256"]:
            raise RuntimeError(f"Frozen {key} manifest changed during V1.5 research")
    metadata = {
        "version": "E&P_ACCOUNTING_PERIMETER_RESERVE_COVERAGE_V1_5_RESEARCH_ONLY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_manifest_sha256": parents_after["v1"]["manifest_sha256"],
        "v1_1_manifest_sha256": parents_after["v11"]["manifest_sha256"],
        "v1_2_manifest_sha256": parents_after["v12"]["manifest_sha256"],
        "v1_3_manifest_sha256": parents_after["v13"]["manifest_sha256"],
        "v1_4_manifest_sha256": parents_after["v14"]["manifest_sha256"],
        "frozen_parent_mutated": False,
        "accounting_perimeter_reconciliation_pass_tickers": perimeter_pass,
        "route_aware_reserve_chain_ready_tickers": ready_count,
        "reserve_coverage_target": "8/14",
        "reserve_coverage_target_met": ready_count >= 8,
        "all_in_reserve_cost_roic_cross_check_tickers": all_in_ready,
        "company_incremental_roic_validated_tickers": 0,
        "terminal_anchor_ready": 0,
        "terminal_anchor_replacement_allowed": False,
        "wacc_range_recalibrated": False,
        "single_appropriate_wacc_claim_allowed": False,
        "v1_1_mutation_allowed": False,
        "risk_channel_duplicate_count": 0,
        "hormuz_treatment": "CASH_FLOW_REGIME_OVERLAY_NO_WACC_PREMIUM",
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(core_perimeter.to_string(index=False))
    print(coverage.to_string(index=False))
    print(core.to_string(index=False))
    print(gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
