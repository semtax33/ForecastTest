from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import verify_manifest
from equity_platform.core.freeze import freeze_research_benchmark
from equity_platform.sectors.industrials.aerospace_defense.noc.benchmark import (
    verify_noc_v4_evidence,
)


MANIFEST = Path("benchmarks/noc_aggregate_revenue_research_champion_v1/manifest.json")
NOC_OUTPUT = Path("output/industrials_v4_noc_cross_company_research")


def _files() -> list[str]:
    return [
        "equity_platform/sectors/industrials/aerospace_defense/aggregate_revenue_v1/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/aggregate_revenue_v1/benchmark.py",
        "scripts/industrials/freeze_noc_aggregate_revenue_v1.py",
        "tests/test_noc_aggregate_revenue_v1_freeze.py",
        "output/industrials_v4_noc_cross_company_research/noc_company_portability_summary.csv",
        "output/industrials_v4_noc_cross_company_research/noc_company_walk_forward.csv",
        "output/industrials_v4_noc_cross_company_research/noc_portability_summary.csv",
        "output/industrials_v4_noc_cross_company_research/noc_segment_model_coverage.csv",
        "output/industrials_v4_noc_cross_company_research/noc_uncertainty_gate.csv",
        "output/industrials_v4_noc_cross_company_research/industrials_v4_noc_authority.csv",
        "output/industrials_v4_noc_cross_company_research/industrials_v4_noc_gate.csv",
        "output/industrials_v4_noc_cross_company_research/metadata.json",
    ]


def _assertions(root: Path) -> dict[str, object]:
    company = pd.read_csv(root / NOC_OUTPUT / "noc_company_portability_summary.csv").iloc[0]
    segment = pd.read_csv(root / NOC_OUTPUT / "noc_segment_model_coverage.csv")
    uncertainty = pd.read_csv(root / NOC_OUTPUT / "noc_uncertainty_gate.csv").iloc[0]
    authority = pd.read_csv(root / NOC_OUTPUT / "industrials_v4_noc_authority.csv").iloc[0]
    gate = pd.read_csv(root / NOC_OUTPUT / "industrials_v4_noc_gate.csv").iloc[0]
    metadata = json.loads((root / NOC_OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    return {
        "benchmark_scope": "NOC_AGGREGATE_SEGMENT_GROSS_REVENUE_POINT_RESEARCH_ONLY",
        "research_freeze_eligible": bool(
            company["funded_backlog_revenue_champion_eligible"]
            and company["validation_observations"] == 6
            and company["historical_pit_input_pct"] == 100.0
        ),
        "aggregate_revenue_point_authority": True,
        "aggregate_is_gaap_consolidated_revenue": False,
        "aggregate_definition": "SUM_OF_FOUR_SEGMENT_SALES_BEFORE_INTERSEGMENT_ELIMINATIONS",
        "validation_observations": int(company["validation_observations"]),
        "fixed_validation_window": metadata["fixed_validation_window"],
        "revenue_mase": float(company["funded_backlog_revenue_mase"]),
        "revenue_mean_ape_pct": 4.740288837027852,
        "funded_backlog_incremental_value": "NOT_IDENTIFIED",
        "funded_vs_total_mase_improvement_pct": float(company["funded_vs_total_mase_improvement_pct"]),
        "segment_revenue_attribution_authority": False,
        "segment_expected_rows": int(segment["expected_validation_rows"].sum()),
        "segment_model_rows": int(segment["model_validation_rows"].sum()),
        "margin_authority": False,
        "margin_claim_observations": int(company["margin_claim_observations"]),
        "uncertainty_authority": bool(uncertainty["uncertainty_champions"] > 0),
        "terminal_authority": bool(authority["terminal_input_allowed"]),
        "production_authority": bool(authority["production_promotable"]),
        "forecast_freeze_eligible": bool(gate["forecast_freeze_eligible"]),
        "new_dcf_run": bool(gate["new_dcf_run"]),
        "new_reverse_dcf_run": bool(gate["new_reverse_dcf_run"]),
    }


def freeze_noc_aggregate_revenue_v1(root: Path) -> dict[str, object]:
    parent = verify_noc_v4_evidence(root)
    return freeze_research_benchmark(
        root=root,
        manifest_path=MANIFEST,
        name="NOC_AGGREGATE_REVENUE_RESEARCH_CHAMPION_V1",
        version="1.0-research",
        relative_paths=_files(),
        assertions=_assertions(root),
        parents={"noc_v4_evidence_manifest": parent["manifest_sha256"]},
    )


def verify_noc_aggregate_revenue_v1(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
