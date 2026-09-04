from __future__ import annotations

import pandas as pd

from equity_platform.certification import verify_lineage_manifest
from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.build_energy_ep_lineage_manifest import build_manifest
from scripts.architecture.universe_certification_v21 import _verified_energy_hashes


MANIFEST = PROJECT_ROOT / "data-lake/gold/certification/energy_ep_source_manifest.csv"


def test_ep_lineage_manifest_is_complete_hash_verified_and_reproducible() -> None:
    frozen = pd.read_csv(MANIFEST)
    rebuilt = build_manifest()
    assert set(frozen["ticker"]) == set(rebuilt["ticker"])
    assert frozen.set_index("ticker")["source_sha256"].to_dict() == rebuilt.set_index("ticker")[
        "source_sha256"
    ].to_dict()
    verification = verify_lineage_manifest(frozen)
    assert len(verification) == 14
    assert verification["lineage_hash_coverage"].eq(1.0).all()


def test_energy_lineage_combines_ep_and_non_ep_without_duplicate_issuers() -> None:
    verification = _verified_energy_hashes()
    assert len(verification) == 26
    assert verification["ticker"].is_unique
    assert verification["lineage_hash_coverage"].eq(1.0).all()
