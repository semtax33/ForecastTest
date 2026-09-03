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
from equity_platform.sectors.industrials.common import build_industry_sensor_authority
from equity_platform.sectors.industrials.v15.pit import build_pit_forecast_features, parse_bls_ppi_vintages
from equity_platform.sectors.industrials.v17.benchmark import verify_margin_v1_7
from equity_platform.sectors.industrials.v2 import (
    build_cmi_ir_evidence,
    build_cmi_portability_forecast,
    build_cmi_reinvestment_roic_evidence,
    build_cmi_source_audit,
    build_uncertainty_calibration,
    build_v2_gates,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v2_cmi.toml"
OUTPUT = ROOT / "output/industrials_v2_cmi_portability_research"


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    parent_before = verify_margin_v1_7(ROOT)
    ir = build_cmi_ir_evidence(
        Path(config["ir_root"]), pd.Timestamp(config["as_of_date"])
    )
    sources = build_cmi_source_audit(
        project_root=ROOT,
        sec_manifest_path=ROOT / config["sec_manifest"],
        ir_inventory=ir["cmi_ir_source_inventory"],
    )
    origins = build_quarterly_forecast_origins(ir["cmi_segment_quarterly_history"])
    bls = parse_bls_ppi_vintages(
        project_root=ROOT,
        archive_manifest_path=ROOT / config["bls_archive_manifest"],
        sensor_map_path=ROOT / config["bls_sensor_map"],
        cutoff=pd.Timestamp(config["as_of_date"]),
    )
    sensor_map = pd.read_csv(ROOT / config["bls_sensor_map"])
    pit = build_pit_forecast_features(
        vintages=bls["bls_ppi_vintage_canonical"],
        sensor_map=sensor_map,
        forecast_origins=origins,
    )
    common_industry = build_industry_sensor_authority(
        registry=pd.read_csv(ROOT / config["industry_sensor_registry"]),
        registry_subindustry="machinery",
        model_sensor_map=sensor_map,
        vintage_audit=bls["bls_ppi_vintage_audit"],
        feature_summary=pit["pit_feature_summary"],
    )
    industry = {
        "cmi_industry_sensor_authority": common_industry["industry_sensor_authority"],
        "cmi_industry_data_summary": common_industry["industry_data_summary"].rename(
            columns={
                "registry_sensors": "registry_machinery_sensors",
                "model_sensor_rows": "bls_model_sensor_rows",
                "model_unique_series": "bls_unique_series",
                "context_only_sensors": "census_context_only_sensors",
                "archive_vintage_rows": "bls_archive_vintage_rows",
                "revised_context_data_used_in_oos_claim": "revised_census_used_in_oos_claim",
            }
        ).drop(columns=["registry_subindustry"]),
    }
    forecast = build_cmi_portability_forecast(
        history=ir["cmi_segment_quarterly_history"],
        scope_audit=ir["cmi_cross_release_scope_audit"],
        scope_events=ir["cmi_scope_event_registry"],
        anchors=ir["cmi_product_anchor_history"],
        industry_features=pit["pit_segment_features"],
        forecast_origins=origins,
        validation_start_period=config["validation_start_period"],
        minimum_training_quarters=int(config["minimum_training_quarters"]),
        ridge_penalty=float(config["ridge_penalty"]),
    )
    reinvestment = build_cmi_reinvestment_roic_evidence(
        sec_inventory=sources["cmi_sec_periodic_source_inventory"]
    )
    uncertainty = build_uncertainty_calibration(
        cat_margin_walk_forward=pd.read_csv(
            ROOT / "output/industrials_valuation_v1_7_research/margin_route_walk_forward.csv"
        ),
        cat_margin_summary=pd.read_csv(
            ROOT / "output/industrials_valuation_v1_7_research/margin_route_summary.csv"
        ),
        cmi_walk_forward=forecast["cmi_portability_walk_forward"],
        cmi_summary=forecast["cmi_portability_summary"],
        minimum_calibration_observations=int(config["minimum_conformal_calibration_observations"]),
    )
    gates = build_v2_gates(
        source_summary=sources["cmi_source_audit_summary"],
        ir_summary=ir["cmi_ir_parser_summary"],
        industry_summary=industry["cmi_industry_data_summary"],
        portability_summary=forecast["cmi_portability_summary"],
        portability_coverage=forecast["cmi_portability_coverage"],
        reinvestment_summary=reinvestment["cmi_reinvestment_roic_summary"],
        uncertainty_gate=uncertainty["portability_uncertainty_gate"],
        expected_oos_quarters_per_segment=int(config["expected_oos_quarters_per_segment"]),
        minimum_research_champions=int(config["minimum_research_champions"]),
        production_minimum_live_observations=int(config["production_minimum_live_observations"]),
    )
    artifacts = {
        **ir,
        **sources,
        "cmi_forecast_origins": origins,
        **bls,
        **pit,
        **industry,
        **forecast,
        **reinvestment,
        **uncertainty,
        **gates,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    parent_after = verify_margin_v1_7(ROOT)
    source_paths = [
        "configs/industrials_v2_cmi.toml",
        "configs/industrials_v2_cmi_bls_sensors.csv",
        "equity_platform/sectors/industrials/v2/__init__.py",
        "equity_platform/sectors/industrials/v2/forecast.py",
        "equity_platform/sectors/industrials/v2/ir.py",
        "equity_platform/sectors/industrials/v2/reinvestment.py",
        "equity_platform/sectors/industrials/v2/research.py",
        "equity_platform/sectors/industrials/v2/sources.py",
        "equity_platform/sectors/industrials/v2/uncertainty.py",
        "equity_platform/core/forecast.py",
        "equity_platform/core/gates.py",
        "equity_platform/core/pit.py",
        "equity_platform/core/uncertainty.py",
        "equity_platform/sectors/industrials/common/sensors.py",
        "scripts/industrials/fetch_cmi_periodic_filings_v2.py",
        "scripts/industrials/valuation_v2_cmi.py",
    ]
    gate = gates["industrials_v2_gate"].iloc[0]
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "ticker": "CMI",
        "branch_status": gate["status"],
        "cat_v1_7_parent_manifest_sha256": parent_before["manifest_sha256"],
        "cat_v1_7_parent_unchanged": parent_before["manifest_sha256"] == parent_after["manifest_sha256"],
        "sec_periodic_manifest_sha256": sha256_file(ROOT / config["sec_manifest"]),
        "source_hashes": hash_files(ROOT, source_paths),
        "fixed_validation_window": "2025Q1-2026Q2",
        "revenue_margin_champions_separate": True,
        "point_uncertainty_champions_separate": True,
        "terminal_input_allowed": False,
        "production_promotable": False,
        "new_dcf_run": False,
        "new_reverse_dcf_run": False,
        "pdf_parsing_deferred": True,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = f"""# Industrials Platform V2 — CMI cross-company portability research

## Gate

{markdown_table(gates['industrials_v2_gate'])}

CAT V1.7 remains byte-for-byte unchanged. CMI is a separate portability branch;
its research, terminal and production authorities are evaluated independently.

## 10-K, 10-Q and IR coverage

{markdown_table(sources['cmi_source_audit_summary'])}

{markdown_table(ir['cmi_ir_parser_summary'])}

The HTML-only parser covers five reported segments and preserves every explicit
Atmus or cross-release perimeter break as an unforecastable scope change.

## Company anchor coverage

{markdown_table(ir['cmi_product_anchor_coverage'])}

Engine unit shipments and the disclosed application/product mix of Engine,
Components, Distribution and Power Systems are retained as PIT company evidence.
No undisclosed residual is relabelled as price, volume or mix.

## Industry data authority

{markdown_table(industry['cmi_industry_data_summary'])}

BLS PPI values come from archived as-released workbooks and enter the model.
Census M3 sensors remain context-only until release-vintage history is archived.

## Revenue and EBITDA-margin portability

{markdown_table(forecast['cmi_portability_summary'])}

Revenue and margin champion decisions are separate. Structural labels are only
used where a non-financial company anchor exists; reduced-form results do not
create component attribution or ROIC claims.

## Prediction interval calibration

{markdown_table(uncertainty['portability_uncertainty_gate'])}

{markdown_table(uncertainty['portability_uncertainty_summary'])}

Point-model champion status never grants uncertainty-model authority. PI80 uses
strictly prior errors and fails closed while calibration samples are insufficient.

## Reinvestment and ROIC evidence

{markdown_table(reinvestment['cmi_reinvestment_roic_summary'])}

{markdown_table(reinvestment['cmi_annual_note_fact_coverage'])}

Quarterly and annual note facts are preserved separately. Reported, tangible,
incremental and through-cycle ROIC diagnostics remain research evidence only.

## Target authority

{markdown_table(gates['cmi_target_route_authority'])}

## Valuation authority

{markdown_table(gates['industrials_v2_valuation_authority'])}
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")

    print(sources["cmi_source_audit_summary"].to_string(index=False))
    print(ir["cmi_ir_parser_summary"].to_string(index=False))
    print(industry["cmi_industry_data_summary"].to_string(index=False))
    print(forecast["cmi_portability_summary"].to_string(index=False))
    print(reinvestment["cmi_reinvestment_roic_summary"].to_string(index=False))
    print(uncertainty["portability_uncertainty_gate"].to_string(index=False))
    print(gates["industrials_v2_gate"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
