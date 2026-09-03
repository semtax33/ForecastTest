from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import freeze_manifest, sha256_file, verify_manifest


MANIFEST = Path("benchmarks/industrials_v1_5_pit_data/manifest.json")
OUTPUT = Path("output/industrials_valuation_v1_5_research")
ARCHIVE_MANIFEST = Path("data-lake/bronze/industrials/v1_5/bls/archive_manifest.json")


def _frozen_files(root: Path) -> list[str]:
    archive = json.loads((root / ARCHIVE_MANIFEST).read_text(encoding="utf-8"))
    acquired = [item["local_path"] for key in ("ppi_report_artifacts", "release_schedule_artifacts") for item in archive[key]]
    stable_outputs = [
        "bls_ppi_archive_sources.csv",
        "bls_release_schedule_sources.csv",
        "bls_ppi_vintage_canonical.csv",
        "bls_ppi_vintage_coverage.csv",
        "bls_ppi_vintage_audit.csv",
        "forecast_origins.csv",
        "pit_segment_features.csv",
        "pit_vintage_selection_audit.csv",
        "pit_feature_summary.csv",
        "cat_retail_ir_sources.csv",
        "cat_retail_vintages.csv",
        "cat_retail_cross_release_audit.csv",
        "cat_retail_quarterly_panel.csv",
        "cat_retail_parser_audit.csv",
    ]
    return [
        "configs/industrials_v1_5_pit_segment_sensors.csv",
        str(ARCHIVE_MANIFEST).replace("\\", "/"),
        "equity_platform/sectors/industrials/v15/benchmark.py",
        "equity_platform/sectors/industrials/v15/pit.py",
        "equity_platform/sectors/industrials/v15/retail.py",
        "scripts/industrials/fetch_v1_5_bls_archives.mjs",
        "scripts/industrials/freeze_v1_5_pit_data.py",
        "tests/test_industrials_v1_5_pit_data_freeze.py",
        *acquired,
        *(f"{OUTPUT.as_posix()}/{name}" for name in stable_outputs),
    ]


def _assertions(root: Path) -> dict[str, object]:
    audit = pd.read_csv(root / OUTPUT / "bls_ppi_vintage_audit.csv").iloc[0]
    features = pd.read_csv(root / OUTPUT / "pit_feature_summary.csv").iloc[0]
    retail = pd.read_csv(root / OUTPUT / "cat_retail_parser_audit.csv").iloc[0]
    selection = pd.read_csv(root / OUTPUT / "pit_vintage_selection_audit.csv")
    return {
        "benchmark_scope": "PIT_DATA_INFRASTRUCTURE_NOT_FORECAST_MODEL",
        "bls_archive_report_files": int(audit["archive_report_files"]),
        "bls_release_schedule_files": int(audit["release_schedule_files"]),
        "bls_vintage_rows": int(audit["vintage_rows"]),
        "bls_series_count": int(audit["parsed_series"]),
        "pit_feature_rows": int(features["feature_rows"]),
        "pit_feature_periods": int(features["forecast_periods"]),
        "pit_series_coverage_pct": float(features["minimum_series_coverage_pct"]),
        "cutoff_violations": int((~selection["cutoff_respected"].astype(bool)).sum()),
        "cat_retail_vintage_rows": int(retail["vintage_rows"]),
        "cat_retail_source_files": int(retail["source_files"]),
        "historical_pit_ready": bool(audit["historical_pit_ready"] and features["historical_pit_ready"]),
        "pdf_parsing_used": False,
        "forecast_model_frozen": False,
        "research_freeze_eligible": False,
        "terminal_evidence_eligible": False,
        "production_promotable": False,
    }


def freeze_v15_pit_data(root: Path) -> dict[str, object]:
    parent = verify_manifest(root=root, manifest_path=Path("benchmarks/industrials_v1_2_architecture/manifest.json"))
    return freeze_manifest(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_V1_5_PIT_DATA_BENCHMARK",
        version="1.5-pit-data",
        relative_paths=_frozen_files(root),
        assertions=_assertions(root),
        parents={"industrials_v1_2_architecture": parent["manifest_sha256"], "archive_manifest": sha256_file(root / ARCHIVE_MANIFEST)},
    )


def verify_v15_pit_data(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
