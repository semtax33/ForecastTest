from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


MANIFEST = Path("benchmarks") / "ep_expectations_surface_v1_2" / "manifest.json"
FROZEN_FILES = (
    "energy_nowcast/research/ep_v12/__init__.py",
    "energy_nowcast/research/ep_v12/benchmark.py",
    "energy_nowcast/research/ep_v12/expectations_surface.py",
    "run_ep_expectations_surface_v1_2.py",
    "freeze_ep_expectations_surface_v1_2.py",
    "tests/test_ep_expectations_surface_v1_2.py",
    "output/energy_valuation_v1_2_research/expectations_surface_sector_summary.csv",
    "output/energy_valuation_v1_2_research/expectations_surface_ticker_detail.csv",
    "output/energy_valuation_v1_2_research/frozen_v1_1_reproduction.csv",
    "output/energy_valuation_v1_2_research/iso_value_curve_summary.csv",
    "output/energy_valuation_v1_2_research/iso_value_curves.csv",
    "output/energy_valuation_v1_2_research/metadata.json",
    "output/energy_valuation_v1_2_research/report.md",
    "output/energy_valuation_v1_2_research/terminal_margin_wacc_above_market_count_matrix.csv",
    "output/energy_valuation_v1_2_research/terminal_margin_wacc_gap_matrix.csv",
    "output/energy_valuation_v1_2_research/through_cycle_economics.csv",
    "output/energy_valuation_v1_2_research/through_cycle_margin_wacc_summary.csv",
    "output/energy_valuation_v1_2_research/through_cycle_margin_wacc_tradeoffs.csv",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_v12(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    if manifest_path.exists():
        return verify_v12(root)
    missing = [relative for relative in FROZEN_FILES if not (root / relative).exists()]
    if missing:
        raise FileNotFoundError(f"Cannot freeze incomplete E&P V1.2: {missing}")

    v1 = verify_v1(root)
    v11 = verify_v11(root)
    metadata = json.loads(
        (root / "output/energy_valuation_v1_2_research/metadata.json").read_text(
            encoding="utf-8"
        )
    )
    if metadata["v1_0_manifest_sha256"] != v1["manifest_sha256"]:
        raise ValueError("V1.2 parent V1.0 manifest mismatch")
    if metadata["v1_1_manifest_sha256"] != v11["manifest_sha256"]:
        raise ValueError("V1.2 parent V1.1 manifest mismatch")
    if metadata.get("single_point_market_implied_claim_allowed") is not False:
        raise ValueError("V1.2 permits an unidentified single-point market claim")
    if metadata.get("production_promoted") is not False:
        raise ValueError("Research-only V1.2 cannot be production promoted")
    if metadata.get("live_matched_observations") != "0/20":
        raise ValueError("Unexpected V1.2 live-forward state")

    manifest = {
        "name": "E&P_EXPECTATIONS_SURFACE_V1_2_RESEARCH",
        "version": "1.2",
        "frozen_as_of": str(date.today()),
        "immutable": True,
        "research_frozen": True,
        "expectations_surface_frozen": True,
        "non_identification_policy_frozen": True,
        "iso_value_solver_frozen": True,
        "single_point_market_implied_claim_allowed": False,
        "parent_v1_0_manifest_sha256": v1["manifest_sha256"],
        "parent_v1_1_manifest_sha256": v11["manifest_sha256"],
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "files": {relative: _sha256(root / relative) for relative in FROZEN_FILES},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return verify_v12(root)


def verify_v12(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    for relative, expected in manifest["files"].items():
        path = root / relative
        if not path.exists():
            failures.append(f"missing:{relative}")
        elif _sha256(path) != expected:
            failures.append(f"hash:{relative}")
    if failures:
        raise ValueError(f"E&P V1.2 freeze verification failed: {failures}")
    v1 = verify_v1(root)
    v11 = verify_v11(root)
    if manifest["parent_v1_0_manifest_sha256"] != v1["manifest_sha256"]:
        raise ValueError("Frozen V1.2 parent V1.0 changed")
    if manifest["parent_v1_1_manifest_sha256"] != v11["manifest_sha256"]:
        raise ValueError("Frozen V1.2 parent V1.1 changed")
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = _sha256(manifest_path)
    manifest["verified_files"] = len(manifest["files"])
    return manifest
