from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.artifacts import verify_manifest
from equity_platform.core.freeze import freeze_research_benchmark
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_hii_v52_valuation,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v53 import (
    verify_hii_v53_margin_research,
)


MANIFEST = Path("benchmarks/industrials_v5_4_hii_margin_mechanisms/manifest.json")
OUTPUT = Path("output/industrials_v5_4_hii_margin_mechanism_research")


def freeze_hii_v54_margin_mechanism_research(root: Path) -> dict[str, object]:
    gate = pd.read_csv(root / OUTPUT / "hii_v54_gate.csv").iloc[0]
    summary = pd.read_csv(root / OUTPUT / "hii_v54_research_summary.csv").iloc[0]
    v52 = verify_hii_v52_valuation(root)
    v53 = verify_hii_v53_margin_research(root)
    files = [
        "configs/industrials_v5_4_hii_margin_mechanisms.toml",
        "data-lake/bronze/industrials/v5_4/bls/hii_shipbuilding_labor_current_revised_2026-09-03.json",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v54/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v54/benchmark.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v54/research.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v54/sources.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v54/valuation.py",
        "scripts/industrials/fetch_hii_v5_4_bls_labor.py",
        "scripts/industrials/freeze_hii_v5_4.py",
        "scripts/industrials/valuation_v5_4_hii_margin_mechanisms.py",
        "tests/test_industrials_v5_4_hii_margin_mechanisms.py",
        "tests/test_industrials_v5_4_hii_margin_mechanisms_freeze.py",
        *[
            path.relative_to(root).as_posix()
            for path in sorted((root / OUTPUT).glob("*"))
            if path.is_file()
        ],
    ]
    assertions = {
        "research_freeze_eligible": bool(gate["research_freeze_eligible"]),
        "all_10k_available": bool(gate["all_10k_available"]),
        "all_10q_available": bool(gate["all_10q_available"]),
        "all_ir_hashes_verified": bool(gate["all_ir_hashes_verified"]),
        "guidance_vintage_coverage_complete": bool(
            gate["guidance_vintage_coverage_complete"]
        ),
        "bls_series_complete": bool(gate["bls_series_complete"]),
        "bls_cutoff_enforced": bool(gate["bls_cutoff_enforced"]),
        "all_lineage_hashes_verified": bool(gate["all_lineage_hashes_verified"]),
        "contract_vintage_margin_identified": bool(
            gate["contract_vintage_margin_identified"]
        ),
        "direct_labor_hours_identified": bool(gate["direct_labor_hours_identified"]),
        "price_reset_lag_identified": bool(gate["price_reset_lag_identified"]),
        "contemporaneous_eight_pct_observed": bool(
            gate["contemporaneous_eight_pct_observed"]
        ),
        "structural_eight_to_ten_mechanism_proven": bool(
            gate["operational_mechanism_for_structural_eight_to_ten_proven"]
        ),
        "dcf_reverse_crosscheck_run": bool(gate["dcf_reverse_crosscheck_run"]),
        "recent_contemporaneous_normalized_max_pct": float(
            summary["recent_contemporaneous_normalized_max_pct"]
        ),
        "valuation_upgrade_allowed": bool(gate["valuation_upgrade_allowed"]),
        "fair_value_claim_allowed": bool(gate["fair_value_claim_allowed"]),
        "terminal_input_allowed": bool(gate["terminal_input_allowed"]),
        "production_promoted": bool(gate["production_promoted"]),
    }
    return freeze_research_benchmark(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_V5_4_HII_MARGIN_MECHANISM_RESEARCH_BENCHMARK",
        version="5.4-research",
        relative_paths=files,
        assertions=assertions,
        parents={
            "hii_v53_through_cycle_margin_manifest": v53["manifest_sha256"],
            "hii_v52_conditional_valuation_manifest": v52["manifest_sha256"],
        },
    )


def verify_hii_v54_margin_mechanism_research(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
