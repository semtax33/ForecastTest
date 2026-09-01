from __future__ import annotations

import hashlib
from pathlib import Path
import tomllib


MANIFEST = Path("benchmarks") / "phase2_4_structural_proxy" / "manifest.toml"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_proxy_benchmark(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches: list[str] = []
    for item in manifest["files"]:
        path = root / item["path"]
        if not path.exists():
            mismatches.append(f"missing: {item['path']}")
        elif _sha256(path) != item["sha256"]:
            mismatches.append(f"hash mismatch: {item['path']}")
    if mismatches:
        raise RuntimeError("Frozen Phase 2-4 proxy benchmark failed: " + "; ".join(mismatches))
    return {
        "version": manifest["version"],
        "files": len(manifest["files"]),
        "manifest_sha256": _sha256(manifest_path),
    }
