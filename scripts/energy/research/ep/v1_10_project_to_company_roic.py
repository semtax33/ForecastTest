from __future__ import annotations

from datetime import datetime, timezone
import json
import pandas as pd

from energy_nowcast.research.ep_v110 import (
    build_cost_component_evidence,
    build_project_to_company_waterfall,
    build_v110_gate,
)
from energy_nowcast.research.ep_v19.benchmark import verify_v19
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table as markdown, write_csv_artifacts


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output/energy_valuation_v1_10_research"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    parent_before = verify_v19(ROOT)
    reserve = pd.read_csv(
        ROOT / "output/energy_valuation_v1_5_research/reserve_roic_scope_cross_check.csv"
    )
    costs = pd.read_csv(
        ROOT / "output/energy_valuation_v1_5_research/annual_all_in_reserve_cost.csv"
    )
    company = pd.read_csv(
        ROOT / "output/energy_valuation_v1_9_research/expanded_company_organic_roic_ranges.csv"
    )
    steps, summary = build_project_to_company_waterfall(reserve, company)
    evidence = build_cost_component_evidence(costs, set(summary["ticker"]))
    gate = build_v110_gate(
        parent_v19_verified=True,
        waterfall_summary=summary,
        driver_evidence=evidence,
    )
    artifacts = {
        "project_to_company_roic_waterfall_steps": steps,
        "project_to_company_roic_reconciliation": summary,
        "roic_waterfall_driver_evidence": evidence,
        "v1_10_gate": gate,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    parent_after = verify_v19(ROOT)
    if parent_before["manifest_sha256"] != parent_after["manifest_sha256"]:
        raise RuntimeError("Frozen V1.9 changed during V1.10 research")
    metadata = {
        "version": "E&P_PROJECT_TO_COMPANY_ROIC_WATERFALL_V1_10_RESEARCH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "v1_9_parent_manifest_sha256": parent_after["manifest_sha256"],
        "v1_10_research_complete": bool(gate.iloc[0]["v1_10_research_complete"]),
        "v1_10_frozen": False,
        "normal_roic_claimed": False,
        "terminal_anchor_replacement_allowed": False,
        "wacc_recalibrated": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report = f"""# E&P V1.10 — Project-to-Company ROIC Waterfall\n\n## Gate\n\n{markdown(gate)}\n\n## Reconciliation\n\n{markdown(summary)}\n\n## Waterfall steps\n\n{markdown(steps)}\n\n## Driver evidence\n\n{markdown(evidence)}\n\nThe project-to-reserve effect is identified only at the aggregate disclosed\nreserve-investment scope. Component cost shares are reported as evidence, but\nno percentage-point ROIC effect is allocated across components because a ratio\nof medians is nonlinear. The remaining reserve-to-company gap is retained as\nan unexplained residual covering leasehold, shared infrastructure, corporate\noverhead, acquisition premium, maintenance/replacement timing, impairment, and\nearnings timing. V1.10 does not estimate a normal ROIC, change WACC, or unlock\nterminal inputs.\n"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(gate.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
