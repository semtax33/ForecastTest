from __future__ import annotations

from datetime import datetime, timezone
import json
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files, sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials import build_cat_segment_history, load_cat_10k_sources
from equity_platform.sectors.industrials.v12.benchmark import verify_v12_architecture
from equity_platform.sectors.industrials.v13lite import build_ir_segment_history
from equity_platform.sectors.industrials.v14 import (
    build_ir_pq_bridge,
    build_segment_margin_research,
    build_segment_sensor_panel,
    build_v14_research,
    build_vintage_canonical,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v1_4.toml"
PARENT_CONFIG = ROOT / "configs/industrials_v1_3_lite.toml"
PARENT_OUTPUT = ROOT / "output/industrials_valuation_v1_3_lite_research"
OUTPUT = ROOT / "output/industrials_valuation_v1_4_research"
ARCANA = ROOT.parent / "Arcana"


def _verify_v13_source_hashes() -> tuple[bool, dict[str, str]]:
    metadata = json.loads((PARENT_OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    expected = metadata["source_hashes"]
    actual = hash_files(ROOT, expected.keys())
    return actual == expected, actual


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    parent_config = tomllib.loads(PARENT_CONFIG.read_text(encoding="utf-8"))
    cutoff = pd.Timestamp(config["as_of_date"])
    parent_before = verify_v12_architecture(ROOT)
    v13_unchanged, v13_source_hashes = _verify_v13_source_hashes()

    cat_sources = load_cat_10k_sources(ROOT, ROOT / parent_config["cat_10k_source_catalog"], cutoff)
    annual_history = build_cat_segment_history(cat_sources)
    ir_directory = ARCANA / parent_config["arcana_ir_relative_path"]
    ir = build_ir_segment_history(ir_directory, cutoff)
    pq = build_ir_pq_bridge(ir["ir_segment_quarterly_history"])

    snapshot_path = ROOT / config["bls_snapshot"]
    sensor_map_path = ROOT / config["sensor_map"]
    vintages = build_vintage_canonical(snapshot_path, cutoff)
    sensors = build_segment_sensor_panel(
        snapshot_path=snapshot_path,
        sensor_map_path=sensor_map_path,
        cutoff=cutoff,
    )
    industry_signals = pd.read_csv(PARENT_OUTPUT / "quarterly_industry_signals.csv")
    v13_validation = pd.read_csv(PARENT_OUTPUT / "capture_temporal_validation.csv")
    economics = build_segment_margin_research(
        pq_bridge=pq["ir_segment_pq_bridge"],
        ir_history=ir["ir_segment_quarterly_history"],
        segment_sensors=sensors["segment_sensor_panel"],
        industry_signals=industry_signals,
        v13_validation=v13_validation,
        minimum_training_quarters=int(config["minimum_training_quarters"]),
        ridge_penalty=float(config["ridge_penalty"]),
        prior_strength=float(config["hierarchical_prior_strength"]),
    )
    research = build_v14_research(
        margin_results=economics,
        pq_results=pq,
        vintage_results=vintages,
        annual_history=annual_history,
        parent_architecture_verified=True,
        minimum_validation_observations=int(config["minimum_validation_quarters"]),
        minimum_segments_below_one=int(config["minimum_segments_below_one"]),
        catastrophic_margin_mase=float(config["catastrophic_margin_mase"]),
        minimum_capture_improvement_pct=float(config["minimum_capture_mae_improvement_pct"]),
    )
    artifacts = {**ir, **pq, **vintages, **sensors, **economics, **research}
    write_csv_artifacts(OUTPUT, artifacts)

    parent_after = verify_v12_architecture(ROOT)
    gate = research["industrials_v1_4_gate"].iloc[0]
    freeze = research["v1_3_lite_freeze_readiness"].iloc[0]
    source_paths = [
        "configs/industrials_v1_4.toml",
        "configs/industrials_v1_4_segment_sensors.csv",
        "data-lake/bronze/industrials/v1_4/bls/latest_segment_cost_drivers.json",
        "equity_platform/reporting.py",
        "equity_platform/sectors/industrials/v14/__init__.py",
        "equity_platform/sectors/industrials/v14/data.py",
        "equity_platform/sectors/industrials/v14/economics.py",
        "equity_platform/sectors/industrials/v14/pq_bridge.py",
        "equity_platform/sectors/industrials/v14/research.py",
        "scripts/industrials/fetch_v1_4_bls.py",
        "scripts/industrials/valuation_v1_4.py",
    ]
    source_hashes = hash_files(ROOT, source_paths)
    parent_metadata = json.loads((PARENT_OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "ticker": "CAT",
        "branch_status": "RESEARCH_NOT_FROZEN",
        "research_scope": "SEGMENT_PQ_COST_DRIVER_MARGIN_VALIDATION",
        "arcana_ir_directory": str(ir_directory),
        "pdf_parsing_deferred": True,
        "parent_v1_2_manifest_sha256": parent_before["manifest_sha256"],
        "parent_v1_2_verified_after": parent_after["manifest_sha256"] == parent_before["manifest_sha256"],
        "parent_v1_3_lite_source_hashes_unchanged": v13_unchanged,
        "parent_v1_3_lite_source_hashes": v13_source_hashes,
        "v1_3_lite_reference_value_per_share": parent_metadata["v1_3_lite_value_per_share"],
        "v1_3_lite_freeze_ready": bool(freeze["v1_3_lite_freeze_ready"]),
        "historical_pit_vintages_available": False,
        "forecast_performance_claim_allowed": False,
        "valuation_update_allowed": False,
        "terminal_input_allowed": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "bls_snapshot_sha256": sha256_file(snapshot_path),
        "source_hashes": source_hashes,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = f"""# Industrials V1.4 — CAT segment cost-driver and margin validation

## Research gate

{markdown_table(research['industrials_v1_4_gate'])}

The CAT IR source is the Arcana SEC IR HTML archive. PDF parsing remains
explicitly deferred. BLS data are stored as a reproducible bronze snapshot, but
historical release vintages do not yet exist; all temporal statistics are
calibration diagnostics and cannot support an investment-performance claim.

## IR price/volume identity

{markdown_table(pq['ir_segment_pq_summary'])}

## Dedicated segment sensors

{markdown_table(sensors['segment_sensor_coverage'])}

## Margin walk-forward

{markdown_table(economics['segment_margin_validation_summary'])}

## Component diagnostics

{markdown_table(economics['segment_component_validation_summary'])}

## V1.3-lite freeze readiness

{markdown_table(research['v1_3_lite_freeze_readiness'])}

## PIT vintage infrastructure

{markdown_table(vintages['pit_vintage_schema_audit'])}

## Reinvestment full-chain validation

{markdown_table(research['reinvestment_full_chain_summary'])}

## Valuation authority

{markdown_table(research['v1_4_valuation_authority'])}

ROIC and terminal economics were intentionally not re-estimated. The V1.3-lite
DCF reference remains unchanged until margin, PIT, and reinvestment gates pass.
Backlog remains 2/3 OOS and production remains locked at 0/20.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(research["industrials_v1_4_gate"].to_string(index=False))
    print(pq["ir_segment_pq_summary"].to_string(index=False))
    print(economics["segment_margin_validation_summary"].to_string(index=False))
    print(research["v1_3_lite_freeze_readiness"].to_string(index=False))
    print(research["reinvestment_full_chain_summary"].to_string(index=False))
    return 0 if bool(gate["research_complete"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
