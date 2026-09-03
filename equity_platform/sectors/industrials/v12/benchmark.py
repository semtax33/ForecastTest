from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.artifacts import freeze_manifest, verify_manifest
from equity_platform.sectors.industrials.v11_benchmark import MANIFEST as V11_MANIFEST, verify_v11


MANIFEST = Path("benchmarks/industrials_v1_2_architecture/manifest.json")
OUTPUT = Path("output/industrials_valuation_v1_2_research")


def _frozen_paths(root: Path) -> list[str]:
    source_paths = [
        "configs/industry_sensor_registry.csv",
        "configs/industrials_v1_2.toml",
        "configs/industrials_v1_2_cat_industry_sensor_map.csv",
        "configs/industrials_v1_2_cat_industry_weights.csv",
        "configs/industrials_v1_2_cfsc_10k_sources.csv",
        "equity_platform/industry_data/__init__.py",
        "equity_platform/industry_data/pqci.py",
        "equity_platform/industry_data/registry.py",
        "equity_platform/sectors/industrials/v12/__init__.py",
        "equity_platform/sectors/industrials/v12/benchmark.py",
        "equity_platform/sectors/industrials/v12/finance_economics.py",
        "equity_platform/sectors/industrials/v12/industry_forecast.py",
        "equity_platform/sectors/industrials/v12/parser_audit.py",
        "equity_platform/sectors/industrials/v12/research.py",
        "equity_platform/sectors/industrials/v12/roic_audit.py",
        "equity_platform/sectors/industrials/v12/surfaces.py",
        "scripts/industrials/freeze_v1_2_architecture.py",
        "scripts/industrials/valuation_v1_2.py",
        "tests/test_industrials_v1_2_freeze.py",
        "tests/test_industrials_valuation_v1_2.py",
    ]
    output_paths = [
        path.relative_to(root).as_posix()
        for path in sorted((root / OUTPUT).iterdir())
        if path.is_file()
    ]
    return source_paths + output_paths


def freeze_v12_architecture(root: Path) -> dict[str, object]:
    parent = verify_v11(root)
    gate = pd.read_csv(root / OUTPUT / "industrials_v1_2_gate.csv").iloc[0]
    data_gate = pd.read_csv(root / OUTPUT / "industry_data_gate.csv").iloc[0]
    registry = pd.read_csv(root / OUTPUT / "industry_sensor_registry.csv")
    parser = pd.read_csv(root / OUTPUT / "parser_quality_summary.csv").iloc[0]
    surface = pd.read_csv(root / OUTPUT / "expectations_surface_summary.csv").iloc[0]
    finance = pd.read_csv(root / OUTPUT / "financial_products_perimeter_audit.csv").iloc[0]
    if not bool(gate["research_complete"]) or not bool(parser["parser_quality_gate_pass"]):
        raise ValueError("Industrials V1.2 architecture gates are incomplete")
    if bool(gate["production_promoted"]) or bool(gate["terminal_input_allowed"]):
        raise ValueError("V1.2 architecture cannot freeze with production/terminal authority")
    return freeze_manifest(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_V1_2_CAT_ARCHITECTURE_RESEARCH_BENCHMARK",
        version="1.2-architecture",
        relative_paths=_frozen_paths(root),
        parents={"industrials_v1_1": parent["manifest_sha256"]},
        assertions={
            "benchmark_scope": "ARCHITECTURE_NOT_FORECAST_PERFORMANCE",
            "gics_sector_count": int(registry["sector"].nunique()),
            "sensor_count": int(len(registry)),
            "cat_sensor_count": int(data_gate["sensor_count"]),
            "historical_pit_backtest_allowed": bool(data_gate["historical_pit_backtest_allowed"]),
            "parser_cross_filing_cells": int(parser["cross_filing_cells"]),
            "parser_cross_filing_mismatches": int(parser["cross_filing_mismatches"]),
            "expectations_surface_points": int(surface["surface_points"]),
            "non_identification_preserved": bool(surface["non_identification_preserved"]),
            "cfsc_exact_economics_available": bool(finance["exact_cfsc_economics_available"]),
            "whole_fp_exact_economics_available": bool(finance["whole_fp_exact_economics_available"]),
            "backlog_model_changed": bool(gate["backlog_model_changed"]),
            "terminal_input_allowed": False,
            "production_promoted": False,
            "live_matched_observations": "0/20",
        },
    )


def verify_v12_architecture(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
