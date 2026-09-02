from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path


BENCHMARK = Path("benchmarks") / "phase5_revenue_research" / "manifest.json"

FROZEN_FILES = (
    "benchmarks/v3_4/manifest.json",
    "benchmarks/v3_5_3_research/manifest.json",
    "benchmarks/phase2_4_structural_proxy/manifest.toml",
    "benchmarks/phase2_1_refining_kpi/manifest.toml",
    "output/phase2_5_target_aligned_research/phase5_routing_table.csv",
    "output/phase2_5_target_aligned_research/phase5_common_forecast_schema_time.csv",
    "output/phase2_5_target_aligned_research/phase5_common_forecast_schema_loco.csv",
    "output/phase2_5_target_aligned_research/phase5_sector_scorecard.csv",
    "output/phase2_5_target_aligned_research/macro_research_decisions.csv",
    "output/phase2_5_target_aligned_research/metadata.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_revenue_research_benchmark(root: Path) -> dict[str, object]:
    """Create the Phase-5 revenue freeze once; later calls only verify it."""
    manifest_path = root / BENCHMARK
    if manifest_path.exists():
        return verify_revenue_research_benchmark(root)
    missing = [relative for relative in FROZEN_FILES if not (root / relative).exists()]
    if missing:
        raise FileNotFoundError(f"Cannot freeze missing revenue artifacts: {missing}")
    manifest = {
        "name": "PHASE5_REVENUE_RESEARCH_CHAMPION",
        "version": "PHASE5_REVENUE_RESEARCH_FREEZE_V1",
        "frozen_as_of": str(date.today()),
        "immutable": True,
        "scope": "Revenue routes, validation outputs, and upstream benchmark manifests",
        "policy": "Revenue research is live-forward only; financial-target work cannot mutate these files.",
        "production_champion": "V3.4_FROZEN",
        "live_model_change_matches": "0/20",
        "files": {
            relative: _sha256(root / relative) for relative in FROZEN_FILES
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return verify_revenue_research_benchmark(root)


def verify_revenue_research_benchmark(root: Path) -> dict[str, object]:
    manifest_path = root / BENCHMARK
    if not manifest_path.exists():
        raise FileNotFoundError(f"Revenue freeze is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("immutable") is not True:
        raise ValueError("Revenue research benchmark is not immutable")
    failures: list[str] = []
    for relative, expected in manifest.get("files", {}).items():
        path = root / relative
        if not path.exists():
            failures.append(f"missing:{relative}")
        elif _sha256(path).lower() != str(expected).lower():
            failures.append(f"hash:{relative}")
    if failures:
        raise ValueError(f"Revenue research benchmark verification failed: {failures}")
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = _sha256(manifest_path)
    manifest["verified_files"] = len(manifest.get("files", {}))
    return manifest

