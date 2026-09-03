from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files, sha256_file
from equity_platform.core.pit import build_quarterly_forecast_origins
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.aerospace_defense.lmt import (
    build_lmt_financial_bridge_forecast,
    build_lmt_industry_evidence,
    build_lmt_ir_evidence,
    build_lmt_portability_forecast,
    build_lmt_reinvestment_roic_evidence,
    build_lmt_research_gates,
    build_lmt_sec_ir_segment_reconciliation,
    build_lmt_source_audit,
    build_lmt_uncertainty_calibration,
)
from equity_platform.sectors.industrials.v15.pit import build_pit_forecast_features, parse_bls_ppi_vintages
from equity_platform.sectors.industrials.v2.benchmark import verify_cmi_v2


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v3_lmt.toml"
OUTPUT = ROOT / "output/industrials_v3_lmt_aerospace_research"
ARCANA_PQCI = Path("D:/Programming/python_example/Arcana/data-lake/bronze/pqci")


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    parent_before = verify_cmi_v2(ROOT)
    ir = build_lmt_ir_evidence(Path(config["ir_root"]), pd.Timestamp(config["as_of_date"]))
    sources = build_lmt_source_audit(project_root=ROOT, sec_manifest_path=ROOT / config["sec_manifest"], ir_inventory=ir["lmt_ir_source_inventory"])
    origins = build_quarterly_forecast_origins(ir["lmt_segment_quarterly_history"])
    bls = parse_bls_ppi_vintages(
        project_root=ROOT, archive_manifest_path=ROOT / config["bls_archive_manifest"],
        sensor_map_path=ROOT / config["bls_sensor_map"], cutoff=pd.Timestamp(config["as_of_date"]),
    )
    sensor_map = pd.read_csv(ROOT / config["bls_sensor_map"])
    pit = build_pit_forecast_features(vintages=bls["bls_ppi_vintage_canonical"], sensor_map=sensor_map, forecast_origins=origins)
    industry = build_lmt_industry_evidence(
        arcana_pqci_root=ARCANA_PQCI, sensor_map=sensor_map,
        bls_vintage_audit=bls["bls_ppi_vintage_audit"], pit_feature_summary=pit["pit_feature_summary"],
    )
    forecast = build_lmt_portability_forecast(
        history=ir["lmt_segment_quarterly_history"], scope_audit=ir["lmt_cross_release_scope_audit"],
        program_losses=ir["lmt_program_loss_registry"], backlog=ir["lmt_backlog_history"],
        deliveries=ir["lmt_delivery_segment_summary"], industry_features=pit["pit_segment_features"], forecast_origins=origins,
        validation_start_period=config["validation_start_period"], minimum_training_quarters=int(config["minimum_training_quarters"]),
        ridge_penalty=float(config["ridge_penalty"]),
    )
    reinvestment = build_lmt_reinvestment_roic_evidence(sec_inventory=sources["lmt_sec_periodic_source_inventory"])
    reconciliation = build_lmt_sec_ir_segment_reconciliation(
        raw_facts=reinvestment["lmt_periodic_relevant_xbrl_facts"],
        sec_inventory=sources["lmt_sec_periodic_source_inventory"],
        ir_history=ir["lmt_segment_quarterly_history"],
        ir_backlog=ir["lmt_backlog_history"],
        ir_program_losses=ir["lmt_program_loss_registry"],
        periodic_selections=reinvestment["lmt_periodic_note_fact_selections"],
    )
    uncertainty = build_lmt_uncertainty_calibration(
        walk_forward=forecast["lmt_portability_walk_forward"], point_summary=forecast["lmt_portability_summary"],
        minimum_calibration_observations=int(config["minimum_conformal_calibration_observations"]),
    )
    bridge = build_lmt_financial_bridge_forecast(
        walk_forward=forecast["lmt_portability_walk_forward"], quarterly_actuals=reinvestment["lmt_quarterly_reinvestment_note_bridge"],
        annual_actuals=reinvestment["lmt_annual_reinvestment_roic_bridge"], point_summary=forecast["lmt_portability_summary"],
    )
    gates = build_lmt_research_gates(
        source_summary=sources["lmt_source_audit_summary"], ir_summary=ir["lmt_ir_parser_summary"],
        industry_summary=industry["lmt_industry_data_summary"], portability_summary=forecast["lmt_portability_summary"],
        portability_coverage=forecast["lmt_portability_coverage"], reinvestment_summary=reinvestment["lmt_reinvestment_roic_summary"],
        segment_reconciliation_summary=reconciliation["lmt_sec_ir_segment_reconciliation_summary"],
        uncertainty_gate=uncertainty["lmt_uncertainty_gate"], bridge_summary=bridge["lmt_company_financial_bridge_summary"],
        expected_oos_quarters_per_segment=int(config["expected_oos_quarters_per_segment"]),
        minimum_research_champions=int(config["minimum_research_champions"]),
        production_minimum_live_observations=int(config["production_minimum_live_observations"]),
    )
    artifacts = {**ir, **sources, "lmt_forecast_origins": origins, **bls, **pit, **industry, **forecast, **reinvestment, **reconciliation, **uncertainty, **bridge, **gates}
    write_csv_artifacts(OUTPUT, artifacts)
    parent_after = verify_cmi_v2(ROOT)
    source_paths = [
        "configs/industrials_v3_lmt.toml", "configs/industrials_v3_lmt_bls_sensors.csv",
        "equity_platform/core/champion_gate.py", "equity_platform/core/target_authority.py",
        "equity_platform/sectors/industrials/common/margin.py",
        "equity_platform/sectors/industrials/common/reinvestment.py",
        "equity_platform/sectors/industrials/aerospace_defense/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt/financial_bridge.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt/forecast.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt/industry.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt/ir.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt/research.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt/segment_reconciliation.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt/sources.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt/uncertainty.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt/xbrl.py",
        "scripts/industrials/fetch_lmt_periodic_filings_v3.py", "scripts/industrials/valuation_v3_lmt.py",
    ]
    metadata = {
        "version": config["version"], "generated_at_utc": datetime.now(timezone.utc).isoformat(), "as_of_date": config["as_of_date"],
        "ticker": "LMT", "subindustry": "AEROSPACE_DEFENSE", "branch_status": gates["industrials_v3_lmt_gate"].iloc[0]["status"],
        "cmi_v2_parent_manifest_sha256": parent_before["manifest_sha256"],
        "cmi_v2_parent_unchanged": parent_before["manifest_sha256"] == parent_after["manifest_sha256"],
        "sec_periodic_manifest_sha256": sha256_file(ROOT / config["sec_manifest"]), "source_hashes": hash_files(ROOT, source_paths),
        "fixed_validation_window": "2025Q1-2026Q2", "revenue_margin_champions_separate": True,
        "point_uncertainty_champions_separate": True, "program_losses_separated_from_margin_claims": True,
        "terminal_input_allowed": False, "production_promotable": False, "new_dcf_run": False, "new_reverse_dcf_run": False,
        "pdf_parsing_deferred": True,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = f"""# Industrials Platform V3 — LMT Aerospace & Defense portability research

## Gate

{markdown_table(gates['industrials_v3_lmt_gate'])}

CMI V2 remains byte-for-byte unchanged. LMT is a separate Aerospace & Defense
research branch. Research, uncertainty, terminal and production authorities are separate.

## 10-K, 10-Q, IR and note coverage

{markdown_table(sources['lmt_source_audit_summary'])}

{markdown_table(ir['lmt_ir_parser_summary'])}

The HTML-only IR parser preserves four reported segments, backlog and deliveries.
Explicit program losses stay in raw actuals but are excluded from margin performance claims.

## SEC-to-IR reconciliation

{markdown_table(reconciliation['lmt_sec_ir_segment_reconciliation_summary'])}

Every 10-K/10-Q segment sales and operating-profit cell is independently selected
from SEC XBRL and reconciled to the IR history. Consolidated SEC remaining performance
obligations are also reconciled to the sum of reported segment backlog, allowing only
the disclosed rounding tolerance.

{markdown_table(reconciliation['lmt_sec_ir_program_loss_reconciliation'])}

Only program losses explicitly allocated to a segment by IR evidence are normalized.
The SEC total above that allocation remains an unallocated residual; it is never
silently assigned to a segment.

## Industry data authority

{markdown_table(industry['lmt_industry_data_summary'])}

BLS PPI values are selected from 54 archived as-released workbooks and enter the model.
Census DAP/NAP/DEF and BEA input-output snapshots are retained as context only because
their historical release vintages are not available in the local lake.

## Segment Revenue and operating margin

{markdown_table(forecast['lmt_portability_summary'])}

## Reinvestment and ROIC evidence

{markdown_table(reinvestment['lmt_reinvestment_roic_summary'])}

{markdown_table(reinvestment['lmt_annual_note_fact_coverage'])}

## Conditional company financial bridge

{markdown_table(bridge['lmt_company_financial_bridge_summary'])}

Reinvestment and annualized ROIC are diagnostics conditioned on segment point forecasts
and trailing, origin-available financial-statement ratios. They are not terminal inputs.

## Prediction interval calibration

{markdown_table(uncertainty['lmt_uncertainty_gate'])}

## Target and valuation authority

{markdown_table(gates['lmt_target_route_authority'])}

{markdown_table(gates['industrials_v3_lmt_valuation_authority'])}
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    for frame in [sources["lmt_source_audit_summary"], ir["lmt_ir_parser_summary"], industry["lmt_industry_data_summary"], forecast["lmt_portability_summary"], reinvestment["lmt_reinvestment_roic_summary"], bridge["lmt_company_financial_bridge_summary"], uncertainty["lmt_uncertainty_gate"], gates["industrials_v3_lmt_gate"]]:
        print(frame.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
