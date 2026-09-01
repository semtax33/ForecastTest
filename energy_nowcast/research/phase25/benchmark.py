from __future__ import annotations

import hashlib
from pathlib import Path
import tomllib


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_refining_kpi_benchmark(root: Path) -> dict[str, object]:
    benchmark = root / "benchmarks" / "phase2_1_refining_kpi"
    manifest_path = benchmark / "manifest.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    checked = 0
    for item in manifest["files"]:
        path = benchmark / str(item["path"])
        if not path.exists():
            raise FileNotFoundError(f"Frozen P2.1 benchmark file is missing: {path}")
        actual = _sha256(path)
        expected = str(item["sha256"])
        if actual != expected:
            raise ValueError(
                f"Frozen P2.1 benchmark changed: {path.name} "
                f"expected={expected} actual={actual}"
            )
        checked += 1
    return {
        "version": manifest["version"],
        "files": checked,
        "manifest_sha256": _sha256(manifest_path),
    }
