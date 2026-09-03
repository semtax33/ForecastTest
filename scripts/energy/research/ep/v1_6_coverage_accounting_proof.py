from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.research.ep_v14.benchmark import verify_v14
from energy_nowcast.research.ep_v15.benchmark import verify_v15
from energy_nowcast.research.ep_v16 import (
    build_three_level_roic,
    build_terminal_candidate_gate,
    build_v16_accounting_proof,
    build_v16_reserve_coverage,
)
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output" / "energy_valuation_v1_6_research"
ARCANA = ROOT.parent / "Arcana"
IR = ARCANA / "data-lake" / "bronze" / "sec" / "fillings" / "ir"


def _parents() -> dict[str, dict[str, object]]:
    return {
        "v1": verify_v1(ROOT),
        "v11": verify_v11(ROOT),
        "v12": verify_v12(ROOT),
        "v13": verify_v13(ROOT),
        "v14": verify_v14(ROOT),
        "v15": verify_v15(ROOT),
    }


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    before = _parents()
    coverage = build_v16_reserve_coverage(
        ir_root=IR,
        production_path=ROOT / "output/v3_5_2_clean_component/production_actuals.csv",
        parent_panel_path=ROOT / "output/energy_valuation_v1_5_research/route_aware_reserve_panel.csv",
        parent_summary_path=ROOT / "output/energy_valuation_v1_5_research/reserve_coverage_summary.csv",
    )
    proof = build_v16_accounting_proof(
        ir_root=IR,
        parent_annual_path=ROOT / "output/energy_valuation_v1_5_research/annual_accounting_perimeter_reconciliation.csv",
        parent_summary_path=ROOT / "output/energy_valuation_v1_5_research/accounting_perimeter_reconciliation_summary.csv",
        parent_mix_path=ROOT / "output/energy_valuation_v1_5_research/production_mix_coverage.csv",
    )
    roic = build_three_level_roic(
        parent_roic_path=ROOT / "output/energy_valuation_v1_5_research/reserve_roic_scope_cross_check.csv",
        ttm_financial_path=ROOT / "output/energy_valuation_v1_1/ttm_financial_bridge_v1_1.parquet",
    )
    terminal = build_terminal_candidate_gate(
        coverage_summary=coverage["v16_reserve_coverage_summary"],
        accounting_summary=proof["v16_accounting_proof_summary"],
        roic_summary=roic["three_level_roic_summary"],
        parent_roic_path=ROOT / "output/energy_valuation_v1_5_research/reserve_roic_scope_cross_check.csv",
    )
    artifacts = {**coverage, **proof, **roic, "terminal_candidate_gate": terminal}
    for name, frame in artifacts.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)

    sector = coverage["v16_coverage_completion_gate"].iloc[0]
    accounting = proof["v16_accounting_proof_summary"]
    ready_terminal = int(terminal["terminal_candidate_ready"].sum())
    parent_hashes = {key: value["manifest_sha256"] for key, value in before.items()}
    metadata = {
        "version": "E&P_COVERAGE_COMPLETION_ACCOUNTING_PROOF_V1_6_RESEARCH_ONLY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **{f"{key}_manifest_sha256": value for key, value in parent_hashes.items()},
        "frozen_parent_mutated": False,
        "reserve_chain_ready_tickers": int(sector["reserve_chain_ready_tickers"]),
        "reserve_coverage_target": "8/14_WITH_OIL3_GAS3_MIXED2",
        "reserve_coverage_target_met": bool(sector["coverage_completion_gate"]),
        "accounting_perimeter_pass_tickers": int(accounting["accounting_perimeter_pass"].sum()),
        "fang_actual_mix_ready": bool(
            accounting.set_index("ticker").loc["FANG", "actual_three_component_mix_ready"]
        ),
        "terminal_candidate_ready_tickers": ready_terminal,
        "terminal_anchor_replacement_allowed": False,
        "wacc_range_recalibrated": False,
        "v1_1_mutation_allowed": False,
        "risk_channel_duplicate_count": 0,
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    core = accounting.loc[accounting["ticker"].isin(["AR", "CNX", "FANG"])]
    report = f"""# E&P V1.6 coverage completion and accounting proof

V1.6 is a research-only child of frozen V1.5. It verifies V1.0 through V1.5
before and after execution and does not modify valuation assumptions, WACC,
terminal economics, or any frozen parser semantics.

## Reserve coverage completion

{_markdown(coverage['v16_coverage_completion_gate'])}

{_markdown(coverage['v16_reserve_group_gate'])}

Supplemental reserve routes preserve their economic meaning. EOG, RRC, DVN,
and SM use total-proved event rollforwards with an independent operational
production check. MTDR uses consecutive total-proved stock snapshots and is
explicitly labelled total replacement including acquisitions, not organic
replacement.

## Accounting proof

{_markdown(core)}

FANG actual oil, NGL, and gas volumes and exact reported gathering, processing,
and transportation cost are extracted from annual Selected Operating Data.
No hedge adjustment is inferred. AR transport/tax and CNX hedge presentation
remain fail-closed blockers.

## Three-level ROIC

{_markdown(roic['three_level_roic_summary'].loc[roic['three_level_roic_summary']['ticker'].isin(['AR','CNX','FANG','EOG'])])}

Company incremental ROIC is Delta NOPAT divided by Delta total invested capital,
using only positive material denominators. It remains diagnostic because M&A
normalization and full accounting-perimeter proof are incomplete.

## Terminal candidate gate

Ready research candidates: {ready_terminal}/14. Terminal replacement remains
prohibited for every ticker, even if an intermediate research-candidate row
passes. Production remains locked at 0/20 live matched observations.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    after = _parents()
    for key in before:
        if before[key]["manifest_sha256"] != after[key]["manifest_sha256"]:
            raise RuntimeError(f"Frozen {key} manifest changed during V1.6 research")
    print(coverage["v16_coverage_completion_gate"].to_string(index=False))
    print(coverage["v16_reserve_group_gate"].to_string(index=False))
    print(core.to_string(index=False))
    print(terminal[["ticker", "terminal_candidate_ready", "terminal_candidate_status"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
