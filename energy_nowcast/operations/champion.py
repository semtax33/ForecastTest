from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def schema_signature(path: Path) -> dict[str, Any]:
    """Return a stable, content-independent CSV schema signature."""
    frame = pd.read_csv(path, nrows=64)
    return {
        "columns": list(frame.columns),
        "dtypes": {column: str(dtype) for column, dtype in frame.dtypes.items()},
    }


def manifest_sha256(manifest_path: Path) -> str:
    return sha256_file(manifest_path)


def load_champion_manifest(root: Path, version: str = "3.4") -> dict[str, Any]:
    path = root / "benchmarks" / f"v{version.replace('.', '_')}" / "manifest.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def verify_champion(root: Path, version: str = "3.4") -> dict[str, Any]:
    """Fail closed if any frozen V3.4 byte or declared input schema changed."""
    root = root.resolve()
    manifest_path = root / "benchmarks" / f"v{version.replace('.', '_')}" / "manifest.json"
    manifest = load_champion_manifest(root, version)
    mismatches: list[str] = []
    for group in ("code", "config", "inputs", "model_artifacts"):
        for relative, expected in manifest["hashes"].get(group, {}).items():
            path = (root / relative).resolve()
            if not path.exists():
                mismatches.append(f"missing {group}: {relative}")
            elif sha256_file(path).lower() != str(expected).lower():
                mismatches.append(f"hash mismatch {group}: {relative}")
    for relative, expected in manifest.get("input_schemas", {}).items():
        path = (root / relative).resolve()
        if not path.exists():
            mismatches.append(f"missing schema input: {relative}")
            continue
        actual = schema_signature(path)
        if actual != expected:
            mismatches.append(f"schema mismatch: {relative}")
    if mismatches:
        raise RuntimeError("Frozen V3.4 champion verification failed: " + "; ".join(mismatches))
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = manifest_sha256(manifest_path)
    return manifest

