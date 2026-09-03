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
from equity_platform.sectors.industrials.v14 import build_ir_pq_bridge
from equity_platform.sectors.industrials.v15 import (
    build_cat_retail_history,
    build_forecast_origins,
    build_pit_forecast_features,
    build_segment_route_validation,
    build_v15_research,
    parse_bls_ppi_vintages,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v1_5.toml"
V13_CONFIG = ROOT / "configs/industrials_v1_3_lite.toml"
PARENT_OUTPUT = ROOT / "output/industrials_valuation_v1_4_research"
OUTPUT = ROOT / "output/industrials_valuation_v1_5_research"
ARCANA = ROOT.parent / "Arcana"


def _verify_parent_source_hashes() -> tuple[bool, dict[str, str]]:
    metadata = json.loads((PARENT_OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    expected = metadata["source_hashes"]
    actual = hash_files(ROOT, expected.keys())
    return actual == expected, actual


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    v13_config = tomllib.loads(V13_CONFIG.read_text(encoding="utf-8"))
    cutoff = pd.Timestamp(config["as_of_date"])
    parent_before = verify_v12_architecture(ROOT)
    v14_unchanged, v14_source_hashes = _verify_parent_source_hashes()

    cat_sources = load_cat_10k_sources(ROOT, ROOT / v13_config["cat_10k_source_catalog"], cutoff)
    annual_history = build_cat_segment_history(cat_sources)
    ir_directory = ARCANA / v13_config["arcana_ir_relative_path"]
    ir = build_ir_segment_history(ir_directory, cutoff)
    pq = build_ir_pq_bridge(ir["ir_segment_quarterly_history"])
    forecast_origins = build_forecast_origins(ir["ir_segment_quarterly_history"])

    archive_manifest = ROOT / config["archive_manifest"]
    sensor_map_path = ROOT / config["sensor_map"]
    sensor_map = pd.read_csv(sensor_map_path)
    pit = parse_bls_ppi_vintages(
        project_root=ROOT,
        archive_manifest_path=archive_manifest,
        sensor_map_path=sensor_map_path,
        cutoff=cutoff,
    )
    pit_features = build_pit_forecast_features(
        vintages=pit["bls_ppi_vintage_canonical"],
        sensor_map=sensor_map,
        forecast_origins=forecast_origins,
    )
    retail = build_cat_retail_history(ir_directory, cutoff)
    routes = build_segment_route_validation(
        ir_history=ir["ir_segment_quarterly_history"],
        pq_bridge=pq["ir_segment_pq_bridge"],
        pit_features=pit_features["pit_segment_features"],
        forecast_origins=forecast_origins,
        retail_vintages=retail["cat_retail_vintages"],
        validation_start_period=config["validation_start_period"],
        minimum_training_quarters=int(config["minimum_training_quarters"]),
        minimum_inner_validation_quarters=int(config["minimum_inner_validation_quarters"]),
        ridge_penalty=float(config["ridge_penalty"]),
    )
    research = build_v15_research(
        validation=routes["segment_route_walk_forward"],
        v14_components=pd.read_csv(PARENT_OUTPUT / "segment_component_validation_summary.csv"),
        annual_history=annual_history,
        pit_archive_audit=pit["bls_ppi_vintage_audit"],
        pit_feature_summary=pit_features["pit_feature_summary"],
        parent_architecture_verified=True,
        minimum_segments_below_one=int(config["minimum_segments_below_one"]),
        worst_segment_margin_mase=float(config["worst_segment_margin_mase"]),
        maximum_revenue_regression_pct=float(config["maximum_segment_revenue_regression_pct"]),
        cancellation_ratio_threshold=float(config["component_cancellation_ratio_threshold"]),
        component_gross_mae_threshold_pct=float(config["component_gross_mae_threshold_pct"]),
        minimum_reinvestment_oos_years=int(config["minimum_reinvestment_oos_years"]),
        maximum_reinvestment_mase=float(config["maximum_reinvestment_mase"]),
    )
    artifacts = {
        **ir,
        **pq,
        "forecast_origins": forecast_origins,
        "v1_5_segment_sensor_registry": sensor_map,
        **pit,
        **pit_features,
        **retail,
        **routes,
        **research,
    }
    write_csv_artifacts(OUTPUT, artifacts)

    parent_after = verify_v12_architecture(ROOT)
    source_paths = [
        "configs/industrials_v1_5.toml",
        "configs/industrials_v1_5_pit_segment_sensors.csv",
        "equity_platform/sectors/industrials/v15/__init__.py",
        "equity_platform/sectors/industrials/v15/pit.py",
        "equity_platform/sectors/industrials/v15/retail.py",
        "equity_platform/sectors/industrials/v15/routes.py",
        "equity_platform/sectors/industrials/v15/research.py",
        "scripts/industrials/fetch_v1_5_bls_archives.mjs",
        "scripts/industrials/valuation_v1_5.py",
    ]
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "ticker": "CAT",
        "branch_status": str(research["v1_5_freeze_readiness"].iloc[0]["status"]),
        "research_scope": "HISTORICAL_PIT_VINTAGE_AND_SEGMENT_ROUTE_VALIDATION",
        "arcana_ir_directory": str(ir_directory),
        "pdf_parsing_deferred": True,
        "parent_v1_2_manifest_sha256": parent_before["manifest_sha256"],
        "parent_v1_2_verified_after": parent_after["manifest_sha256"] == parent_before["manifest_sha256"],
        "parent_v1_4_source_hashes_unchanged": v14_unchanged,
        "parent_v1_4_source_hashes": v14_source_hashes,
        "historical_pit_vintages_available": bool(pit["bls_ppi_vintage_audit"].iloc[0]["historical_pit_ready"]),
        "forecast_performance_claim_allowed": bool(
            research["segment_route_validation_summary"]["performance_claim_allowed"].all()
        ),
        "valuation_update_allowed": False,
        "v1_3_lite_reference_value_per_share_usd": 399.1175,
        "terminal_input_allowed": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "archive_manifest_sha256": sha256_file(archive_manifest),
        "source_hashes": hash_files(ROOT, source_paths),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = f"""# Industrials V1.5 — Historical PIT vintage and segment-route validation

## Freeze disposition

{markdown_table(research['v1_5_freeze_readiness'])}

V1.5 remains `HOLD_RESEARCH_UNFROZEN`.  Historical point-in-time validation is
now real rather than a schema placeholder, but the strengthened full-chain gate
still blocks DCF and Reverse DCF updates.  The V1.3-lite reference value of
$399.1175 per share is preserved.

## Historical PIT acquisition and cutoff

{markdown_table(pit['bls_ppi_vintage_audit'])}

{markdown_table(pit_features['pit_feature_summary'])}

All BLS inputs are archived monthly XLSX releases with verified SHA-256 hashes.
CAT dealer retail inputs come from the Arcana SEC IR HTML archive.  PDF parsing
was not used.  Each target quarter uses the immediately preceding CAT earnings
release as forecast origin; the target release is settlement only.

## Segment champions and margin validation

{markdown_table(research['segment_route_validation_summary'])}

Routes are selected separately inside each segment and forecast origin using
training-only inner validation.  A route cannot defeat the lagged-volume anchor
unless its inner MAE is lower.

## Component-error and cancellation audit

{markdown_table(research['segment_component_pit_validation_summary'])}

The cancellation lock fails closed when a margin MASE below one coexists with
large gross component errors and a high offset ratio.  Therefore a seemingly
good margin cannot be promoted if price, volume, and cost are merely cancelling.

## Reinvestment full-chain validation

{markdown_table(research['reinvestment_pit_full_chain_summary'])}

Reinvestment parameters were not retuned.  Only complete historical-PIT fiscal
years count; fewer than three observations cannot unlock the bridge.

## Valuation authority

{markdown_table(research['v1_5_valuation_authority'])}

Backlog remains 2/3 OOS, terminal economics remain locked, and production remains
0/20.  No DCF or Reverse DCF was run by design.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(pit["bls_ppi_vintage_audit"].to_string(index=False))
    print(pit_features["pit_feature_summary"].to_string(index=False))
    print(research["segment_route_validation_summary"].to_string(index=False))
    print(research["reinvestment_pit_full_chain_summary"].to_string(index=False))
    print(research["v1_5_freeze_readiness"].to_string(index=False))
    return 0 if bool(research["industrials_v1_5_gate"].iloc[0]["research_complete"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
