from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import verify_manifest
from equity_platform.core.freeze import freeze_research_benchmark


MANIFEST = Path("benchmarks/industrials_platform_v4_noc_evidence/manifest.json")
OUTPUT = Path("output/industrials_v4_noc_cross_company_research")


def _files(root: Path) -> list[str]:
    code = [
        "configs/industrials_v4_noc.toml",
        "configs/industrials_v4_noc_bls_sensors.csv",
        "data-lake/bronze/industrials/v4/sec/noc/manifest.json",
        "equity_platform/sectors/industrials/aerospace_defense/noc/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/noc/benchmark.py",
        "equity_platform/sectors/industrials/aerospace_defense/noc/forecast.py",
        "equity_platform/sectors/industrials/aerospace_defense/noc/ir.py",
        "equity_platform/sectors/industrials/aerospace_defense/noc/sec.py",
        "scripts/industrials/fetch_noc_periodic_filings_v4.py",
        "scripts/industrials/freeze_v4_noc_evidence.py",
        "scripts/industrials/valuation_v4_noc.py",
        "tests/test_industrials_v4_noc.py",
        "tests/test_industrials_v4_noc_evidence_freeze.py",
    ]
    outputs = [
        path.relative_to(root).as_posix()
        for path in sorted((root / OUTPUT).glob("*"))
        if path.is_file()
    ]
    return code + outputs


def _assertions(root: Path) -> dict[str, object]:
    source = pd.read_csv(root / OUTPUT / "noc_source_audit_summary.csv").iloc[0]
    parser = pd.read_csv(root / OUTPUT / "noc_ir_parser_summary.csv").iloc[0]
    reconciliation = pd.read_csv(root / OUTPUT / "noc_sec_ir_segment_reconciliation_summary.csv").iloc[0]
    company = pd.read_csv(root / OUTPUT / "noc_company_portability_summary.csv").iloc[0]
    coverage = pd.read_csv(root / OUTPUT / "noc_segment_model_coverage.csv")
    gate = pd.read_csv(root / OUTPUT / "industrials_v4_noc_gate.csv").iloc[0]
    metadata = json.loads((root / OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    return {
        "benchmark_scope": "NOC_EVIDENCE_PARSER_AND_CROSS_COMPANY_EXPERIMENT_RECORD_ONLY",
        "source_gate_pass": bool(source["source_gate_pass"]),
        "parser_gate_pass": bool(parser["parser_gate_pass"]),
        "sec_filings": int(source["sec_filings"]),
        "ir_earnings_releases": int(source["ir_earnings_releases"]),
        "segment_quarter_rows": int(parser["segment_quarter_rows"]),
        "funded_backlog_coverage_pct": float(parser["funded_backlog_coverage_pct"]),
        "scope_recast_excluded_cells": int(reconciliation["scope_recast_excluded_cells"]),
        "scope_comparable_identity_pass_cells": int(reconciliation["sec_ir_segment_identity_pass_cells"]),
        "company_oos_observations": int(company["validation_observations"]),
        "company_revenue_mase": float(company["funded_backlog_revenue_mase"]),
        "funded_vs_total_mase_improvement_pct": float(company["funded_vs_total_mase_improvement_pct"]),
        "segment_expected_rows": int(coverage["expected_validation_rows"].sum()),
        "segment_model_rows": int(coverage["model_validation_rows"].sum()),
        "missing_segment_rows_imputed": bool(coverage["missing_rows_imputed"].any()),
        "research_freeze_eligible": bool(gate["evidence_parser_freeze_eligible"]),
        "evidence_parser_freeze_eligible": bool(gate["evidence_parser_freeze_eligible"]),
        "forecast_freeze_eligible": bool(gate["forecast_freeze_eligible"]),
        "fixed_validation_window": metadata["fixed_validation_window"],
        "lmt_v31_parent_unchanged": bool(metadata["lmt_v31_evidence_parent_unchanged"]),
        "terminal_input_allowed": bool(gate["terminal_gate_pass"]),
        "production_promoted": bool(gate["production_gate_pass"]),
        "new_dcf_run": bool(gate["new_dcf_run"]),
        "new_reverse_dcf_run": bool(gate["new_reverse_dcf_run"]),
        "pdf_parsing_used": bool(metadata["pdf_parsing_deferred"] is False),
    }


def freeze_noc_v4_evidence(root: Path) -> dict[str, object]:
    metadata = json.loads((root / OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    return freeze_research_benchmark(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_PLATFORM_V4_NOC_EVIDENCE_AND_CROSS_COMPANY_EXPERIMENT",
        version="4.0-evidence",
        relative_paths=_files(root),
        assertions=_assertions(root),
        parents={"lmt_v31_evidence_manifest": metadata["lmt_v31_evidence_manifest_sha256"]},
    )


def verify_noc_v4_evidence(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
