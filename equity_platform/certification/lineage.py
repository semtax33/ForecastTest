from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.artifacts import sha256_file


LINEAGE_COLUMNS = {
    "ticker",
    "source_kind",
    "source_path",
    "source_sha256",
    "available_at",
}


def verify_lineage_manifest(manifest: pd.DataFrame) -> pd.DataFrame:
    """Verify explicit source paths and hashes, returning issuer coverage.

    Missing or mutated sources remain visible as failed rows.  A manifest never
    grants readiness merely because it contains a hash-shaped string.
    """

    missing = LINEAGE_COLUMNS - set(manifest.columns)
    if missing:
        raise ValueError(f"Lineage manifest missing columns: {sorted(missing)}")
    if manifest.empty or manifest[["ticker", "source_path"]].duplicated().any():
        raise ValueError("Lineage manifest must contain unique source rows")
    detail = manifest.copy()
    detail["source_exists"] = detail["source_path"].map(lambda raw: Path(str(raw)).is_file())
    detail["hash_verified"] = detail.apply(
        lambda row: bool(
            row["source_exists"]
            and sha256_file(Path(str(row["source_path"]))) == str(row["source_sha256"])
        ),
        axis=1,
    )
    return (
        detail.groupby("ticker", as_index=False)
        .agg(
            hashed_sources=("source_path", "size"),
            verified_hashed_sources=("hash_verified", "sum"),
        )
        .assign(
            lineage_hash_coverage=lambda frame: (
                frame["verified_hashed_sources"] / frame["hashed_sources"]
            )
        )
    )
