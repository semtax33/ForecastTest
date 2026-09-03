from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files, sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.aerospace_defense.lmt import (
    build_lmt_financial_bridge_forecast,
    build_lmt_uncertainty_calibration,
)
from equity_platform.sectors.industrials.aerospace_defense.lmt_v31 import (
    build_lmt_program_conversion_evidence,
    build_lmt_v31_forecast,
    build_lmt_v31_research_gates,
    build_v31_feature_panel,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v3_1_lmt.toml"
OUTPUT = ROOT / "output/industrials_v3_1_lmt_program_conversion_research"


def _read(parent: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(parent / f"{name}.csv")


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    parent = ROOT / config["parent_output"]
    parent_metadata = json.loads((parent / "metadata.json").read_text(encoding="utf-8"))
    ir_inventory = _read(parent, "lmt_ir_source_inventory")
    sec_inventory = _read(parent, "lmt_sec_periodic_source_inventory")
    evidence = build_lmt_program_conversion_evidence(
        ir_inventory=ir_inventory,
        sec_inventory=sec_inventory,
    )
    feature_panel, delivery_values = build_v31_feature_panel(
        base_panel=_read(parent, "lmt_portability_feature_panel"),
        attributions=evidence["lmt_v31_program_attribution_history"],
        deliveries=_read(parent, "lmt_aircraft_delivery_history"),
        backlog=_read(parent, "lmt_backlog_history"),
        horizon=evidence["lmt_v31_backlog_conversion_horizon"],
        delivery_value_penalty=float(config["delivery_value_penalty"]),
    )
    forecast = build_lmt_v31_forecast(
        feature_panel=feature_panel,
        parent_walk=_read(parent, "lmt_portability_walk_forward"),
        validation_start_period=config["validation_start_period"],
        minimum_training_quarters=int(config["minimum_training_quarters"]),
        ridge_penalty=float(config["ridge_penalty"]),
    )
    uncertainty = build_lmt_uncertainty_calibration(
        walk_forward=forecast["lmt_v31_walk_forward"],
        point_summary=forecast["lmt_v31_summary"],
        minimum_calibration_observations=8,
    )
    bridge = build_lmt_financial_bridge_forecast(
        walk_forward=forecast["lmt_v31_walk_forward"],
        quarterly_actuals=_read(parent, "lmt_quarterly_reinvestment_note_bridge"),
        annual_actuals=_read(parent, "lmt_annual_reinvestment_roic_bridge"),
        point_summary=forecast["lmt_v31_summary"],
    )
    gates = build_lmt_v31_research_gates(
        evidence_summary=evidence["lmt_v31_program_evidence_summary"],
        coverage=forecast["lmt_v31_coverage"],
        selected_summary=forecast["lmt_v31_summary"],
        challenger_summary=forecast["lmt_v31_challenger_summary"],
        decisions=forecast["lmt_v31_route_decisions"],
        preservation=forecast["lmt_v31_parent_preservation"],
        uncertainty_gate=uncertainty["lmt_uncertainty_gate"],
        bridge_summary=bridge["lmt_company_financial_bridge_summary"],
        parent_status=parent_metadata["branch_status"],
        minimum_research_joint_champions=int(config["minimum_research_joint_champions"]),
        production_minimum_live_observations=int(config["production_minimum_live_observations"]),
    )
    source = _read(parent, "lmt_source_audit_summary").iloc[0]
    parser = _read(parent, "lmt_ir_parser_summary").iloc[0]
    reconciliation = _read(parent, "lmt_sec_ir_segment_reconciliation_summary").iloc[0]
    industry = _read(parent, "lmt_industry_data_summary").iloc[0]
    inherited = pd.DataFrame(
        [
            {
                "sec_10k_filings": int(source["sec_10k_filings"]),
                "sec_10q_filings": int(source["sec_10q_filings"]),
                "note_families_audited": int(source["note_families_audited"]),
                "ir_earnings_releases": int(source["ir_earnings_releases"]),
                "ir_segment_rows": int(parser["segment_quarter_rows"]),
                "sec_ir_segment_identity_cells": int(reconciliation["sec_ir_segment_identity_pass_cells"]),
                "sec_rpo_ir_backlog_identity_periods": int(reconciliation["rpo_backlog_identity_pass_periods"]),
                "bls_vintage_rows": int(industry["bls_archive_vintage_rows"]),
                "census_context_rows": int(industry["census_aerospace_defense_context_rows"]),
                "bea_context_only": True,
                "inherited_source_gate_pass": bool(
                    source["source_gate_pass"]
                    and parser["parser_gate_pass"]
                    and reconciliation["segment_and_backlog_reconciliation_gate_pass"]
                    and industry["historical_pit_ready"]
                ),
            }
        ]
    )
    artifacts = {
        "lmt_v31_inherited_source_authority": inherited,
        **evidence,
        "lmt_v31_rms_delivery_value_weights": delivery_values,
        **forecast,
        **uncertainty,
        **bridge,
        **gates,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    source_paths = [
        "configs/industrials_v3_1_lmt.toml",
        "equity_platform/sectors/industrials/aerospace_defense/lmt_v31/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt_v31/evidence.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt_v31/model.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt_v31/research.py",
        "scripts/industrials/valuation_v3_1_lmt.py",
        "tests/test_industrials_v3_1_lmt.py",
    ]
    parent_inputs = [
        "metadata.json",
        "lmt_portability_feature_panel.csv",
        "lmt_portability_walk_forward.csv",
        "lmt_ir_source_inventory.csv",
        "lmt_sec_periodic_source_inventory.csv",
        "lmt_aircraft_delivery_history.csv",
        "lmt_backlog_history.csv",
        "lmt_quarterly_reinvestment_note_bridge.csv",
        "lmt_annual_reinvestment_roic_bridge.csv",
    ]
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "parent_version": parent_metadata["version"],
        "parent_status": parent_metadata["branch_status"],
        "parent_metadata_sha256": sha256_file(parent / "metadata.json"),
        "parent_input_hashes": {name: sha256_file(parent / name) for name in parent_inputs},
        "source_hashes": hash_files(ROOT, source_paths),
        "fixed_validation_window": f"{config['validation_start_period']}-{config['validation_end_period']}",
        "program_level_backlog_claim_allowed": False,
        "terminal_input_allowed": False,
        "production_promotable": False,
        "new_dcf_run": False,
        "new_reverse_dcf_run": False,
        "pdf_parsing_used": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = f"""# Industrials Platform V3.1 — LMT program conversion closure

## Gate

{markdown_table(gates['industrials_v3_1_lmt_gate'])}

The 2025Q1–2026Q2 OOS window is unchanged. A challenger must beat both the
parent route and the seasonal-naive baseline before it can replace a target.

## Inherited 10-K, 10-Q, notes, IR and industry authority

{markdown_table(inherited)}

## New program evidence coverage

{markdown_table(evidence['lmt_v31_program_evidence_summary'])}

{markdown_table(evidence['lmt_v31_backlog_conversion_horizon'])}

The 12/24-month conversion percentages are company-wide disclosures. LMT does
not disclose program-level backlog amounts, so no program-level backlog claim is allowed.

## Pre-specified challenger results

{markdown_table(forecast['lmt_v31_challenger_summary'])}

{markdown_table(forecast['lmt_v31_route_decisions'])}

All three challengers deteriorated on the fixed OOS window and were rejected.
No post-result feature substitution was performed.

## Selected champion results

{markdown_table(forecast['lmt_v31_summary'])}

## Uncertainty and financial bridge

{markdown_table(uncertainty['lmt_uncertainty_gate'])}

{markdown_table(bridge['lmt_company_financial_bridge_summary'])}

## Target and valuation authority

{markdown_table(gates['lmt_v31_target_authority'])}

{markdown_table(gates['industrials_v3_1_lmt_valuation_authority'])}
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    for frame in (
        inherited,
        evidence["lmt_v31_program_evidence_summary"],
        forecast["lmt_v31_challenger_summary"],
        forecast["lmt_v31_route_decisions"],
        forecast["lmt_v31_summary"],
        gates["industrials_v3_1_lmt_gate"],
    ):
        print(frame.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
