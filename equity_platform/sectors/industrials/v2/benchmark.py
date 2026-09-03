from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import verify_manifest
from equity_platform.core.freeze import freeze_research_benchmark
from equity_platform.sectors.industrials.v17.benchmark import verify_margin_v1_7


MANIFEST = Path("benchmarks/industrials_platform_v2_cmi/manifest.json")
OUTPUT = Path("output/industrials_v2_cmi_portability_research")
SEC_MANIFEST = Path("data-lake/bronze/industrials/v2/sec/cmi/manifest.json")


def _files(root: Path) -> list[str]:
    sec = json.loads((root / SEC_MANIFEST).read_text(encoding="utf-8"))
    sec_files = [str(item["local_path"]) for item in sec["files"]]
    code = [
        "configs/industrials_v2_cmi.toml",
        "configs/industrials_v2_cmi_bls_sensors.csv",
        SEC_MANIFEST.as_posix(),
        "equity_platform/core/__init__.py",
        "equity_platform/core/forecast.py",
        "equity_platform/core/freeze.py",
        "equity_platform/core/gates.py",
        "equity_platform/core/pit.py",
        "equity_platform/core/uncertainty.py",
        "equity_platform/sectors/industrials/common/__init__.py",
        "equity_platform/sectors/industrials/common/sensors.py",
        "equity_platform/sectors/industrials/v2/__init__.py",
        "equity_platform/sectors/industrials/v2/benchmark.py",
        "equity_platform/sectors/industrials/v2/forecast.py",
        "equity_platform/sectors/industrials/v2/ir.py",
        "equity_platform/sectors/industrials/v2/reinvestment.py",
        "equity_platform/sectors/industrials/v2/research.py",
        "equity_platform/sectors/industrials/v2/sources.py",
        "equity_platform/sectors/industrials/v2/uncertainty.py",
        "scripts/industrials/fetch_cmi_periodic_filings_v2.py",
        "scripts/industrials/freeze_v2_cmi.py",
        "scripts/industrials/valuation_v2_cmi.py",
        "tests/test_industrials_v2_cmi.py",
        "tests/test_industrials_v2_cmi_freeze.py",
    ]
    outputs = [
        path.relative_to(root).as_posix()
        for path in sorted((root / OUTPUT).glob("*"))
        if path.is_file()
    ]
    return code + sec_files + outputs


def _assertions(root: Path) -> dict[str, object]:
    gate = pd.read_csv(root / OUTPUT / "industrials_v2_gate.csv").iloc[0]
    source = pd.read_csv(root / OUTPUT / "cmi_source_audit_summary.csv").iloc[0]
    parser = pd.read_csv(root / OUTPUT / "cmi_ir_parser_summary.csv").iloc[0]
    performance = pd.read_csv(root / OUTPUT / "cmi_portability_summary.csv")
    industry = pd.read_csv(root / OUTPUT / "cmi_industry_data_summary.csv").iloc[0]
    uncertainty = pd.read_csv(root / OUTPUT / "portability_uncertainty_gate.csv").iloc[0]
    return {
        "benchmark_scope": "CMI_CROSS_COMPANY_PORTABILITY_RESEARCH_ONLY",
        "research_freeze_eligible": bool(gate["research_freeze_eligible"]),
        "sec_periodic_filings": int(source["sec_filings"]),
        "ir_earnings_releases": int(source["ir_earnings_releases"]),
        "segment_quarters": int(parser["segment_quarter_rows"]),
        "segment_sales_coverage_pct": float(parser["segment_sales_coverage_pct"]),
        "segment_ebitda_coverage_pct": float(parser["segment_ebitda_coverage_pct"]),
        "historical_pit_coverage_pct": float(performance["historical_pit_input_pct"].min()),
        "cutoff_violations": int(industry["cutoff_violations"]),
        "revenue_champions": int(performance["revenue_champion_eligible"].sum()),
        "margin_champions": int(performance["margin_champion_eligible"].sum()),
        "joint_champions": int(performance["joint_champion"].sum()),
        "structural_joint_champion": "engine",
        "uncertainty_champions": int(uncertainty["uncertainty_champions"]),
        "terminal_input_allowed": bool(gate["terminal_gate_pass"]),
        "production_promoted": bool(gate["production_gate_pass"]),
        "pdf_parsing_used": False,
    }


def freeze_cmi_v2(root: Path) -> dict[str, object]:
    cat = verify_margin_v1_7(root)
    pit = verify_manifest(
        root=root,
        manifest_path=Path("benchmarks/industrials_v1_5_pit_data/manifest.json"),
    )
    return freeze_research_benchmark(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_PLATFORM_V2_CMI_PORTABILITY_RESEARCH",
        version="2.0",
        relative_paths=_files(root),
        assertions=_assertions(root),
        parents={
            "industrials_cat_margin_v1_7": cat["manifest_sha256"],
            "industrials_v1_5_pit_data": pit["manifest_sha256"],
        },
    )


def verify_cmi_v2(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
