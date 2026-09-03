from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.artifacts import verify_manifest
from equity_platform.core.freeze import freeze_research_benchmark
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_hii_v52_valuation,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v521 import (
    verify_hii_v521_consensus,
)


MANIFEST = Path("benchmarks/industrials_v5_3_hii_through_cycle_margin/manifest.json")
OUTPUT = Path("output/industrials_v5_3_hii_through_cycle_margin_research")


def freeze_hii_v53_margin_research(root: Path) -> dict[str, object]:
    gate = pd.read_csv(root / OUTPUT / "hii_v53_gate.csv").iloc[0]
    summary = pd.read_csv(root / OUTPUT / "hii_v53_research_summary.csv").iloc[0]
    v52 = verify_hii_v52_valuation(root)
    v521 = verify_hii_v521_consensus(root)
    files = [
        "configs/industrials_v5_3_hii_margin.toml",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v53/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v53/benchmark.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v53/research.py",
        "scripts/industrials/freeze_hii_v5_3.py",
        "scripts/industrials/valuation_v5_3_hii_margin.py",
        "tests/test_industrials_v5_3_hii_margin.py",
        "tests/test_industrials_v5_3_hii_margin_freeze.py",
        *[
            path.relative_to(root).as_posix()
            for path in sorted((root / OUTPUT).glob("*"))
            if path.is_file()
        ],
    ]
    assertions = {
        "research_freeze_eligible": bool(gate["research_freeze_eligible"]),
        "all_10k_parsed": bool(gate["all_10k_parsed"]),
        "all_10q_parsed": bool(gate["all_10q_parsed"]),
        "ir_history_coverage_complete": bool(gate["ir_history_coverage_complete"]),
        "ir_source_hashes_verified": bool(gate["ir_source_hashes_verified"]),
        "contract_mix_identities_pass": bool(gate["contract_mix_identities_pass"]),
        "catchup_identities_pass": bool(gate["catchup_identities_pass"]),
        "fas_cas_identities_pass": bool(gate["fas_cas_identities_pass"]),
        "backlog_identities_pass": bool(gate["backlog_identities_pass"]),
        "dcf_crosscheck_run": bool(gate["dcf_crosscheck_run"]),
        "eight_pct_assessment": summary["eight_pct_assessment"],
        "ten_pct_assessment": summary["ten_pct_assessment"],
        "twelve_pct_assessment": summary["twelve_pct_assessment"],
        "fair_value_claim_allowed": bool(gate["fair_value_claim_allowed"]),
        "terminal_input_allowed": bool(gate["terminal_input_allowed"]),
        "production_promoted": bool(gate["production_promoted"]),
    }
    return freeze_research_benchmark(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_V5_3_HII_THROUGH_CYCLE_MARGIN_RESEARCH_BENCHMARK",
        version="5.3-research",
        relative_paths=files,
        assertions=assertions,
        parents={
            "hii_v52_conditional_valuation_manifest": v52["manifest_sha256"],
            "hii_v521_consensus_overlay_manifest": v521["manifest_sha256"],
        },
    )


def verify_hii_v53_margin_research(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
