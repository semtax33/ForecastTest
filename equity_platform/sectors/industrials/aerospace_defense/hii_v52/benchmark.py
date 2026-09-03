from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.artifacts import verify_manifest
from equity_platform.core.freeze import freeze_research_benchmark
from equity_platform.sectors.industrials.aerospace_defense.hii.benchmark import (
    verify_hii_v5_evidence,
)


GOVERNANCE_MANIFEST = Path("benchmarks/industrials_v5_1_hii_governance/manifest.json")
REPLICATION_MANIFEST = Path("benchmarks/aerospace_defense_aggregate_revenue_replication_v1/manifest.json")
VALUATION_MANIFEST = Path("benchmarks/industrials_v5_2_hii_conditional_valuation/manifest.json")
GOVERNANCE_OUTPUT = Path("output/industrials_v5_1_hii_governance_research")
REPLICATION_OUTPUT = Path("output/aerospace_defense_aggregate_revenue_replication_v1")
VALUATION_OUTPUT = Path("output/industrials_v5_2_hii_conditional_valuation_research")


def _output_files(root: Path, directory: Path) -> list[str]:
    return [
        path.relative_to(root).as_posix()
        for path in sorted((root / directory).glob("*"))
        if path.is_file()
    ]


def freeze_hii_v51_governance(root: Path) -> dict[str, object]:
    audit = pd.read_csv(root / GOVERNANCE_OUTPUT / "hii_route_selection_leakage_audit.csv").iloc[0]
    namespaces = pd.read_csv(root / GOVERNANCE_OUTPUT / "hii_authority_namespaces.csv")
    parent = verify_hii_v5_evidence(root)
    assertions = {
        "research_freeze_eligible": True,
        "routes_tested_on_same_oos": int(audit["routes_tested_on_same_oos"]),
        "v5_best_tested_diagnostic_mase": float(audit["v5_reported_mase"]),
        "clean_predeclared_mase": float(audit["clean_predeclared_mase"]),
        "route_selection_leakage_present": bool(audit["route_selection_leakage_present"]),
        "authority_namespaces": int(len(namespaces)),
        "terminal_input_allowed": False,
        "production_promoted": False,
    }
    files = [
        "equity_platform/sectors/industrials/aerospace_defense/hii_v52/governance.py",
        "scripts/industrials/valuation_v5_2_hii.py",
        "tests/test_industrials_v5_1_hii_governance.py",
        *_output_files(root, GOVERNANCE_OUTPUT),
    ]
    return freeze_research_benchmark(
        root=root,
        manifest_path=GOVERNANCE_MANIFEST,
        name="INDUSTRIALS_V5_1_HII_ROUTE_GOVERNANCE",
        version="5.1-research",
        relative_paths=files,
        assertions=assertions,
        parents={"hii_v5_evidence_manifest": parent["manifest_sha256"]},
    )


def verify_hii_v51_governance(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=GOVERNANCE_MANIFEST)


def freeze_ad_aggregate_replication_v1(root: Path) -> dict[str, object]:
    summary = pd.read_csv(root / REPLICATION_OUTPUT / "ad_aggregate_replication_summary.csv").iloc[0]
    parent = verify_hii_v5_evidence(root)
    assertions = {
        "research_freeze_eligible": bool(summary["research_freeze_eligible"]),
        "companies": int(summary["companies"]),
        "aggregate_pass": int(summary["aggregate_pass"]),
        "aggregate_total": int(summary["aggregate_total"]),
        "segment_pass": int(summary["segment_pass"]),
        "segment_total": int(summary["segment_total"]),
        "cross_company_replication": bool(summary["cross_company_replication"]),
        "cross_regime_replication": bool(summary["cross_regime_replication"]),
        "status": summary["status"],
        "terminal_input_allowed": bool(summary["terminal_input_allowed"]),
        "production_promoted": bool(summary["production_promoted"]),
    }
    files = [
        "equity_platform/sectors/industrials/aerospace_defense/hii_v52/governance.py",
        "tests/test_ad_aggregate_replication_v1_freeze.py",
        *_output_files(root, REPLICATION_OUTPUT),
    ]
    return freeze_research_benchmark(
        root=root,
        manifest_path=REPLICATION_MANIFEST,
        name="AEROSPACE_DEFENSE_AGGREGATE_REVENUE_REPLICATION_V1",
        version="1.0-research",
        relative_paths=files,
        assertions=assertions,
        parents={"hii_v5_evidence_manifest": parent["manifest_sha256"]},
    )


def verify_ad_aggregate_replication_v1(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=REPLICATION_MANIFEST)


def freeze_hii_v52_valuation(root: Path) -> dict[str, object]:
    gate = pd.read_csv(root / VALUATION_OUTPUT / "hii_v52_gate.csv").iloc[0]
    summary = pd.read_csv(root / VALUATION_OUTPUT / "hii_conditional_valuation_summary.csv").iloc[0]
    governance = verify_hii_v51_governance(root)
    replication = verify_ad_aggregate_replication_v1(root)
    assertions = {
        "research_freeze_eligible": bool(gate["research_freeze_eligible"]),
        "quarterly_nwc_chain_complete": bool(gate["quarterly_nwc_chain_complete"]),
        "fcff_identity_pass": bool(gate["fcff_identity_pass"]),
        "solver_round_trip_pass": bool(gate["solver_round_trip_pass"]),
        "ev_to_equity_identity_pass": bool(gate["ev_to_equity_identity_pass"]),
        "dcf_run": bool(gate["dcf_run"]),
        "reverse_dcf_run": bool(gate["reverse_dcf_run"]),
        "high_terminal_dependence": bool(summary["high_terminal_dependence"]),
        "terminal_input_allowed": bool(gate["terminal_authority"]),
        "production_promoted": bool(gate["production_promoted"]),
    }
    files = [
        "configs/industrials_v5_2_hii_valuation.toml",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v52/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v52/benchmark.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v52/evidence.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v52/governance.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v52/valuation.py",
        "scripts/industrials/freeze_hii_v5_2.py",
        "scripts/industrials/valuation_v5_2_hii.py",
        "tests/test_industrials_v5_2_hii_valuation.py",
        "tests/test_industrials_v5_2_hii_valuation_freeze.py",
        "data-lake/bronze/industrials/v5_2/market/ad_weekly_adjusted_close_through_2026-07-31.csv",
        *_output_files(root, VALUATION_OUTPUT),
    ]
    return freeze_research_benchmark(
        root=root,
        manifest_path=VALUATION_MANIFEST,
        name="INDUSTRIALS_V5_2_HII_CONDITIONAL_VALUATION_RESEARCH",
        version="5.2-research",
        relative_paths=files,
        assertions=assertions,
        parents={
            "hii_v51_governance_manifest": governance["manifest_sha256"],
            "ad_replication_v1_manifest": replication["manifest_sha256"],
        },
    )


def verify_hii_v52_valuation(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=VALUATION_MANIFEST)
