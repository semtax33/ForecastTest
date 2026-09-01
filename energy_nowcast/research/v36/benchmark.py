from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...operations.champion import sha256_file


def verify_research_champion(
    root: Path,
    version: str = "3.5.3",
) -> dict[str, Any]:
    """Fail closed if any byte declared by the research benchmark changed."""
    root = root.resolve()
    benchmark = f"v{version.replace('.', '_')}_research"
    manifest_path = root / "benchmarks" / benchmark / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Research benchmark manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches: list[str] = []
    for category, files in manifest.get("hashes", {}).items():
        for relative, expected in files.items():
            path = (root / relative).resolve()
            if not path.exists():
                mismatches.append(f"missing {category}: {relative}")
            elif sha256_file(path).lower() != str(expected).lower():
                mismatches.append(f"hash mismatch {category}: {relative}")
    if mismatches:
        raise RuntimeError(
            "Frozen V3.5.3 research champion verification failed: "
            + "; ".join(mismatches)
        )
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = sha256_file(manifest_path)
    return manifest
