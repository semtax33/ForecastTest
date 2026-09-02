from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.research.ep_v14.benchmark import verify_v14
from energy_nowcast.research.ep_v15.benchmark import verify_v15
from energy_nowcast.research.ep_v161 import (
    build_core_accounting_proof,
    build_mna_normalized_capital_bridge,
    build_v161_freeze_gate,
)
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "energy_valuation_v1_6_1_research"
ARCANA = ROOT.parent / "Arcana"
IR = ARCANA / "data-lake" / "bronze" / "sec" / "fillings" / "ir"
COMPANYFACTS = ARCANA / "data-lake" / "bronze" / "sec" / "companyfacts"


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
    accounting = build_core_accounting_proof(
        ir_root=IR,
        parent_annual_path=ROOT / "output/energy_valuation_v1_5_research/annual_accounting_perimeter_reconciliation.csv",
        parent_summary_path=ROOT / "output/energy_valuation_v1_5_research/accounting_perimeter_reconciliation_summary.csv",
        v16_fang_reconciliation_path=ROOT / "output/energy_valuation_v1_6_research/fang_v16_accounting_reconciliation.csv",
    )
    capital = build_mna_normalized_capital_bridge(
        companyfacts_root=COMPANYFACTS,
        ttm_financial_path=ROOT / "output/energy_valuation_v1_1/ttm_financial_bridge_v1_1.parquet",
    )
    coverage_gate = pd.read_csv(
        ROOT / "output/energy_valuation_v1_6_research/v16_coverage_completion_gate.csv"
    )
    three_level = pd.read_csv(
        ROOT / "output/energy_valuation_v1_6_research/three_level_roic_summary.csv"
    )
    terminal = pd.read_csv(
        ROOT / "output/energy_valuation_v1_6_research/terminal_candidate_gate.csv"
    )
    freeze_gate = build_v161_freeze_gate(
        coverage_gate=coverage_gate,
        accounting_summary=accounting["core_accounting_proof_summary"],
        mna_summary=capital["mna_normalized_roic_summary"],
        three_level_roic_summary=three_level,
        terminal_gate=terminal,
    )
    artifacts = {**accounting, **capital, "v1_6_1_freeze_gate": freeze_gate}
    for name, frame in artifacts.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)
    after = _parents()
    for key in before:
        if before[key]["manifest_sha256"] != after[key]["manifest_sha256"]:
            raise RuntimeError(f"Frozen {key} manifest changed during V1.6.1")
    metadata = {
        "version": "E&P_ACCOUNTING_PROVEN_V1_6_1_RESEARCH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **{
            f"{key}_manifest_sha256": value["manifest_sha256"]
            for key, value in after.items()
        },
        "v1_6_coverage_source": "HASH_PINNED_V1_6_OUTPUT_DEPENDENCY_ON_FREEZE",
        "frozen_parent_mutated": False,
        "core_accounting_pass_tickers": int(
            accounting["core_accounting_proof_summary"][
                "accounting_perimeter_pass"
            ].sum()
        ),
        "mna_normalization_diagnostic_implemented": True,
        "mna_normalization_validated": False,
        "freeze_eligible": bool(freeze_gate.iloc[0]["v1_6_1_research_freeze_eligible"]),
        "terminal_anchor_replacement_allowed": False,
        "wacc_recalibrated": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    fang_2025 = accounting["fang_margin_gap_attribution"].loc[
        accounting["fang_margin_gap_attribution"]["year"].eq(2025)
    ]
    report = f"""# E&P V1.6.1 accounting proof and M&A-normalized capital bridge

V1.6.1 is an accounting-proven research layer built on the reproducible V1.6
coverage output. Its consumed V1.6 outputs are hash-pinned when this layer is
frozen. Frozen V1.0 through V1.5 manifests are verified before and after
execution. No WACC, terminal, scenario, or production assumption changes.

## Core accounting proof

{_markdown(accounting['core_accounting_proof_summary'])}

AR's reported lease operating, GP&T, and production/ad valorem tax expenses
reconcile to the already-selected composite lifting cost. Adding separate
transport and tax would double count them. Historical 2021/2022 red margin-gap
rows remain disclosed.

CNX's annual supplemental statements separately reconcile production revenue,
realized derivative settlement, unrealized derivative change, and cash-settled
production sales. No best-fit hedge hypothesis is used.

## FANG 2025 attribution

{_markdown(fang_2025)}

The reported consolidated operating margin contains a $3.652 billion oil and
gas property impairment. The V1.6 comparison also added tax and transport to a
lifting-cost measure that already contained LOE, tax, and GP&T. V1.6.1 removes
the duplicate additions only in this child research layer and preserves all
reported GAAP values.

## M&A-normalized company incremental ROIC

{_markdown(capital['mna_normalized_roic_summary'].loc[capital['mna_normalized_roic_summary']['ticker'].isin(['AR','CNX','FANG','EOG'])])}

The bridge subtracts observed cash acquisition facts and adds observed
divestiture proceeds to the total invested-capital change. It is denominator-
only diagnostic normalization: acquired NOPAT, non-cash consideration, and
book-value differences remain in the disclosed residual. It is not a validated
terminal ROIC input.

## Freeze gate

{_markdown(freeze_gate)}

Terminal replacement remains locked at 0/14 and production remains locked at
0/20 live matched observations.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(accounting["core_accounting_proof_summary"].to_string(index=False))
    print(fang_2025.to_string(index=False))
    print(freeze_gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
