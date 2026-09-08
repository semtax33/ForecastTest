from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.learned import download_span_model_snapshots


DEFAULT_DESTINATION = (
    PROJECT_ROOT / "data-lake" / "bronze" / "models" / "text_ie"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download pinned Text IE span challengers into Bronze storage",
    )
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = _arguments()
    snapshots = download_span_model_snapshots(args.destination)
    manifest = {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "storage_tier": "BRONZE_EXTERNAL_MODEL_SNAPSHOT",
        "runtime_authority": "RESEARCH_CHALLENGER_ONLY",
        "models": [
            {
                "model_id": snapshot.model_id,
                "revision": snapshot.revision,
                "local_path": str(snapshot.local_path),
                "size_bytes": snapshot.size_bytes,
                "config_sha256": _sha256(snapshot.config_path),
                "weight_sha256": _sha256(snapshot.weight_path),
            }
            for snapshot in snapshots
        ],
    }
    manifest_path = args.destination / "model_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
