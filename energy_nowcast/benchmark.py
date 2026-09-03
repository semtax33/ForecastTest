from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from equity_platform.data_catalog import DataCatalog

from .config import ProjectPaths


def load_manifest(paths: ProjectPaths) -> dict[str, Any]:
    manifest_path = paths.root / "benchmarks" / "v3_3" / "manifest.json"
    with manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_frozen_benchmark(paths: ProjectPaths) -> dict[str, Any]:
    manifest = load_manifest(paths)
    mismatches: list[str] = []
    for relative, expected in manifest["artifacts"].items():
        artifact = paths.root / relative
        if not artifact.exists():
            mismatches.append(f"missing: {relative}")
            continue
        actual = sha256_file(artifact)
        if actual.lower() != expected.lower():
            mismatches.append(f"hash mismatch: {relative}")
    if mismatches:
        raise RuntimeError("V3.3 benchmark verification failed: " + "; ".join(mismatches))
    assert paths.data_lake is not None
    validation = pd.read_csv(
        DataCatalog(paths.data_lake).v33 / "energy_v3_3_validation.csv"
    )
    expected = manifest["expected_metrics"]
    actual_log_mae = float(
        (validation["actual_log_yoy"] - validation["blend_log_yoy"]).abs().mean()
    )
    actual_pct_mae = float(
        (
            100.0 * np.expm1(validation["actual_log_yoy"] / 100.0)
            - 100.0 * np.expm1(validation["blend_log_yoy"] / 100.0)
        ).abs().mean()
    )
    if not np.isclose(actual_log_mae, expected["overall_mae_log_points"], atol=1e-12):
        raise RuntimeError("V3.3 benchmark metric mismatch: overall log MAE")
    if not np.isclose(actual_pct_mae, expected["overall_mae_yoy_pct_points"], atol=1e-12):
        raise RuntimeError("V3.3 benchmark metric mismatch: overall YoY MAE")
    return manifest
