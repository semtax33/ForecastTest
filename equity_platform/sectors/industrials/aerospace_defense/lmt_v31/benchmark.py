from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import verify_manifest
from equity_platform.core.freeze import freeze_research_benchmark


MANIFEST = Path("benchmarks/industrials_platform_v3_1_lmt_evidence/manifest.json")
OUTPUT = Path("output/industrials_v3_1_lmt_program_conversion_research")


def _files(root: Path) -> list[str]:
    code = [
        "configs/industrials_v3_1_lmt.toml",
        "equity_platform/sectors/industrials/aerospace_defense/lmt_v31/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt_v31/benchmark.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt_v31/evidence.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt_v31/model.py",
        "equity_platform/sectors/industrials/aerospace_defense/lmt_v31/research.py",
        "scripts/industrials/freeze_v3_1_lmt_evidence.py",
        "scripts/industrials/valuation_v3_1_lmt.py",
        "tests/test_industrials_v3_1_lmt.py",
        "tests/test_industrials_v3_1_lmt_evidence_freeze.py",
    ]
    outputs = [
        path.relative_to(root).as_posix()
        for path in sorted((root / OUTPUT).glob("*"))
        if path.is_file()
    ]
    return code + outputs


def _assertions(root: Path) -> dict[str, object]:
    evidence = pd.read_csv(root / OUTPUT / "lmt_v31_program_evidence_summary.csv").iloc[0]
    gate = pd.read_csv(root / OUTPUT / "industrials_v3_1_lmt_gate.csv").iloc[0]
    decisions = pd.read_csv(root / OUTPUT / "lmt_v31_route_decisions.csv")
    summary = pd.read_csv(root / OUTPUT / "lmt_v31_summary.csv")
    metadata = json.loads((root / OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    return {
        "benchmark_scope": "LMT_PROGRAM_EVIDENCE_AND_REJECTED_CHALLENGER_RECORD_ONLY",
        "research_freeze_eligible": bool(evidence["evidence_gate_pass"]),
        "forecast_research_freeze_eligible": bool(gate["research_freeze_eligible"]),
        "program_narrative_cells": int(evidence["parsed_segment_metric_narratives"]),
        "program_narrative_coverage_pct": float(evidence["segment_metric_narrative_coverage_pct"]),
        "sec_10q_program_identity_cells": int(evidence["sec_10q_program_amount_identity_pass_cells"]),
        "backlog_horizon_10k_filings": int(evidence["annual_backlog_horizon_filings"]),
        "program_level_backlog_amount_coverage_pct": float(evidence["program_level_backlog_amount_coverage_pct"]),
        "program_level_backlog_fail_closed": bool(evidence["program_level_backlog_fail_closed"]),
        "challengers_tested": int(
            decisions["revenue_challenger_tested"].sum()
            + decisions["margin_challenger_tested"].sum()
        ),
        "challengers_accepted": int(
            decisions["revenue_challenger_accepted"].sum()
            + decisions["margin_challenger_accepted"].sum()
        ),
        "rejected_experiment_record_immutable": True,
        "selected_joint_champions": int(summary["joint_champion"].sum()),
        "fixed_validation_window": metadata["fixed_validation_window"],
        "terminal_input_allowed": bool(gate["terminal_gate_pass"]),
        "production_promoted": bool(gate["production_gate_pass"]),
        "new_dcf_run": bool(gate["new_dcf_run"]),
        "new_reverse_dcf_run": bool(gate["new_reverse_dcf_run"]),
        "pdf_parsing_used": bool(metadata["pdf_parsing_used"]),
    }


def freeze_lmt_v31_evidence(root: Path) -> dict[str, object]:
    metadata = json.loads((root / OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    return freeze_research_benchmark(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_PLATFORM_V3_1_LMT_EVIDENCE_AND_REJECTED_EXPERIMENTS",
        version="3.1-evidence",
        relative_paths=_files(root),
        assertions=_assertions(root),
        parents={"lmt_v3_parent_metadata": metadata["parent_metadata_sha256"]},
    )


def verify_lmt_v31_evidence(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
