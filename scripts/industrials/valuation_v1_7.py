from __future__ import annotations

from datetime import datetime, timezone
import json
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files, sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.v16.benchmark import verify_revenue_champion_v1
from equity_platform.sectors.industrials.v17 import (
    build_margin_research,
    build_power_energy_application_mix,
    build_profit_driver_evidence,
    build_reinvestment_roic_evidence,
    build_source_audit,
    build_v17_gate,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v1_7.toml"
OUTPUT = ROOT / "output/industrials_valuation_v1_7_research"


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    revenue_parent = verify_revenue_champion_v1(ROOT)
    v15 = ROOT / config["parent_v1_5_output"]
    v16 = ROOT / config["parent_v1_6_output"]
    v12 = ROOT / config["parent_v1_2_output"]
    ir_history = pd.read_csv(v15 / "ir_segment_quarterly_history.csv")
    route_panel = pd.read_csv(v15 / "segment_route_panel.csv")
    revenue_validation = pd.read_csv(v15 / "segment_route_walk_forward.csv")
    cost_perimeter = pd.read_csv(v16 / "segment_cost_perimeter.csv")
    mpe_roic_history = pd.read_csv(v12 / "mpe_incremental_roic_history.csv")

    sources = build_source_audit(
        project_root=ROOT,
        sec_manifest_path=ROOT / config["sec_manifest"],
        ir_history=ir_history,
    )
    drivers = build_profit_driver_evidence(ir_history)
    application = build_power_energy_application_mix(ir_history)
    margin = build_margin_research(
        route_panel=route_panel,
        revenue_validation=revenue_validation,
        cost_perimeter=cost_perimeter,
        driver_evidence=drivers["company_reported_profit_driver_evidence"],
        application_mix=application["power_energy_application_mix"],
        validation_start_period=config["validation_start_period"],
        predeclared_routes=dict(config["predeclared_margin_routes"]),
        ridge_penalty=float(config["ridge_penalty"]),
        material_scope_threshold_pct=float(config["material_scope_threshold_pct"]),
    )
    reinvestment = build_reinvestment_roic_evidence(
        sec_inventory=sources["sec_periodic_source_inventory"],
        mpe_roic_history=mpe_roic_history,
    )
    gate = build_v17_gate(
        source_summary=sources["v1_7_source_audit_summary"],
        margin_summary=margin["margin_route_summary"],
        margin_walk_forward=margin["margin_route_walk_forward"],
        profit_driver_summary=drivers["company_reported_profit_driver_summary"],
        application_mix_summary=application["power_energy_application_mix_summary"],
        reinvestment_summary=reinvestment["reinvestment_roic_evidence_summary"],
        revenue_benchmark_verified=True,
        minimum_margin_champions=int(config["minimum_margin_champions"]),
        maximum_worst_margin_mase=float(config["maximum_worst_margin_mase"]),
        expected_oos_quarters_per_segment=int(config["expected_oos_quarters_per_segment"]),
        production_minimum_live_observations=int(config["production_minimum_live_observations"]),
    )
    artifacts = {**sources, **drivers, **application, **margin, **reinvestment, **gate}
    write_csv_artifacts(OUTPUT, artifacts)

    revenue_parent_after = verify_revenue_champion_v1(ROOT)
    source_paths = [
        "configs/industrials_v1_7.toml",
        "equity_platform/sectors/industrials/v17/__init__.py",
        "equity_platform/sectors/industrials/v17/application_mix.py",
        "equity_platform/sectors/industrials/v17/margin.py",
        "equity_platform/sectors/industrials/v17/profit_drivers.py",
        "equity_platform/sectors/industrials/v17/reinvestment.py",
        "equity_platform/sectors/industrials/v17/research.py",
        "equity_platform/sectors/industrials/v17/sources.py",
        "scripts/industrials/fetch_cat_periodic_filings_v1_7.py",
        "scripts/industrials/valuation_v1_7.py",
    ]
    gate_row = gate["industrials_v1_7_gate"].iloc[0]
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "ticker": "CAT",
        "branch_status": gate_row["status"],
        "research_scope": "SEGMENT_PROFIT_DRIVER_COMPARABLE_MARGIN_REINVESTMENT_ROIC_NOTE_AUDIT",
        "revenue_champion_manifest_sha256": revenue_parent["manifest_sha256"],
        "revenue_champion_verified_files": revenue_parent["verified_files"],
        "revenue_champion_verified_after": revenue_parent_after["manifest_sha256"] == revenue_parent["manifest_sha256"],
        "sec_periodic_manifest_sha256": sha256_file(ROOT / config["sec_manifest"]),
        "sec_periodic_filings": int(sources["v1_7_source_audit_summary"].iloc[0]["sec_filings"]),
        "ir_earnings_releases": int(sources["v1_7_source_audit_summary"].iloc[0]["ir_earnings_releases"]),
        "source_hashes": hash_files(ROOT, source_paths),
        "fixed_validation_window": "2025Q1-2026Q2",
        "pdf_parsing_deferred": True,
        "research_freeze_eligible": bool(gate_row["research_freeze_eligible"]),
        "terminal_input_allowed": False,
        "production_promotable": False,
        "new_dcf_run": False,
        "new_reverse_dcf_run": False,
        "reference_value_per_share_usd": 399.1175,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = f"""# Industrials V1.7 — Segment profit driver and comparable-margin bridge

## Result

{markdown_table(gate['industrials_v1_7_gate'])}

Revenue remains the separately frozen `INDUSTRIALS_CAT_REVENUE_CHAMPION_V1`.
This branch evaluates margin evidence only; terminal valuation and production
promotion remain independent and locked.

## Source and parser audit

{markdown_table(sources['v1_7_source_audit_summary'])}

All 23 official CAT 10-K/10-Q HTML filings from 2021 through the cutoff and all
23 matching Arcana earnings-release HTML files were hash-checked. PDFs were not
parsed by design.

## Company-reported profit-driver evidence

{markdown_table(drivers['company_reported_profit_driver_summary'])}

Only explicitly quantified price, volume/mix, manufacturing cost, SG&A/R&D and
currency effects are assigned to a named driver. Every undisclosed remainder is
kept as `unallocated_other_residual_usd`; it is never reverse-labelled.

## P&E application mix

{markdown_table(application['power_energy_application_mix_summary'])}

The product-mix route uses only the most recently released application mix at
each forecast origin. The 2026 removal of Transportation from the segment is an
explicit scope change.

## Reported versus comparable margin

The current reported margin, originally reported prior-year margin, and the
current filing's recast comparable prior margin satisfy an exact additive
perimeter identity. Material unexpected changes are labelled
`UNFORECASTABLE_SCOPE_CHANGE` and cannot support component attribution.

## Fixed six-quarter margin validation

{markdown_table(margin['margin_route_summary'])}

Construction keeps the predeclared structural route even though it fails the
MASE<1 champion threshold. P&E and Resource use reduced-form routes; their
statistical forecasts do not create economic component or ROIC claims.

## Reinvestment and ROIC note evidence

{markdown_table(reinvestment['reinvestment_roic_evidence_summary'])}

{markdown_table(reinvestment['annual_note_fact_coverage'])}

Capex includes both PP&E purchases and equipment acquired for lease. Net capex,
operating working capital, R&D, cash acquisitions, goodwill/intangibles,
restructuring, warranty and pension/OPEB evidence are retained separately.
Consolidated and MP&E ROIC perimeters are cross-checked but never blended.

## Route authority

{markdown_table(gate['margin_route_authority'])}

## Valuation authority

{markdown_table(gate['v1_7_valuation_authority'])}
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(sources["v1_7_source_audit_summary"].to_string(index=False))
    print(drivers["company_reported_profit_driver_summary"].to_string(index=False))
    print(application["power_energy_application_mix_summary"].to_string(index=False))
    print(margin["margin_route_summary"].to_string(index=False))
    print(reinvestment["reinvestment_roic_evidence_summary"].to_string(index=False))
    print(gate["industrials_v1_7_gate"].to_string(index=False))
    return 0 if bool(gate_row["research_freeze_eligible"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
