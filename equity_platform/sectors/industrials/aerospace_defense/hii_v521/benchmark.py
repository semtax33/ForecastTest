from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.artifacts import verify_manifest
from equity_platform.core.freeze import freeze_research_benchmark
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    verify_hii_v52_valuation,
)


MANIFEST = Path("benchmarks/industrials_v5_2_1_hii_consensus_overlay/manifest.json")
OUTPUT = Path("output/industrials_v5_2_1_hii_consensus_overlay_research")


def freeze_hii_v521_consensus(root: Path) -> dict[str, object]:
    gate = pd.read_csv(root / OUTPUT / "hii_v521_consensus_gate.csv").iloc[0]
    parent = verify_hii_v52_valuation(root)
    files = [
        "equity_platform/sectors/industrials/aerospace_defense/hii_v521/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v521/benchmark.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii_v521/research.py",
        "scripts/industrials/valuation_v5_2_1_hii_consensus.py",
        "tests/test_industrials_v5_2_1_hii_consensus.py",
        *[
            path.relative_to(root).as_posix()
            for path in sorted((root / OUTPUT).glob("*"))
            if path.is_file()
        ],
    ]
    return freeze_research_benchmark(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_V5_2_1_HII_CONSENSUS_EXPECTATIONS_OVERLAY",
        version="5.2.1-research",
        relative_paths=files,
        assertions={
            "research_freeze_eligible": bool(gate["research_freeze_eligible"]),
            "required_providers_present": bool(gate["required_providers_present"]),
            "all_consensus_is_out_of_model_fit": bool(gate["all_consensus_is_out_of_model_fit"]),
            "bad_reference_price_cannot_replace_official_close": bool(gate["bad_reference_price_cannot_replace_official_close"]),
            "terminal_input_allowed": bool(gate["terminal_input_allowed"]),
            "production_promoted": bool(gate["production_promoted"]),
        },
        parents={"hii_v52_valuation_manifest": parent["manifest_sha256"]},
    )


def verify_hii_v521_consensus(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
