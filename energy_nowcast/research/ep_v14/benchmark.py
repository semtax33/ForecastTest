from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11
from energy_nowcast.research.ep_v12.benchmark import verify_v12


MANIFEST = Path("benchmarks") / "ep_cost_scope_v1_4" / "manifest.json"
FROZEN_FILES = (
    "energy_nowcast/research/ep_v14/__init__.py",
    "energy_nowcast/research/ep_v14/benchmark.py",
    "energy_nowcast/research/ep_v14/cost_scope.py",
    "scripts/energy/research/ep/v1_4_cost_scope.py",
    "scripts/energy/research/freeze/ep_v1_4.py",
    "tests/test_ep_cost_scope_v1_4.py",
    "output/energy_valuation_v1_4_research/annual_cost_scope_panel.csv",
    "output/energy_valuation_v1_4_research/annual_realized_basis_panel.csv",
    "output/energy_valuation_v1_4_research/cost_scope_coverage.csv",
    "output/energy_valuation_v1_4_research/cost_scope_gate.csv",
    "output/energy_valuation_v1_4_research/expanded_core_cross_check.csv",
    "output/energy_valuation_v1_4_research/metadata.json",
    "output/energy_valuation_v1_4_research/report.md",
    "output/energy_valuation_v1_4_research/standardized_tag_coverage.csv",
    "output/energy_valuation_v1_4_research/standardized_tag_summary.csv",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parents(root: Path) -> dict[str, dict[str, object]]:
    return {
        "v1": verify_v1(root),
        "v11": verify_v11(root),
        "v12": verify_v12(root),
        "v13": verify_v13(root),
    }


def freeze_v14(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    if manifest_path.exists():
        return verify_v14(root)
    missing = [relative for relative in FROZEN_FILES if not (root / relative).exists()]
    if missing:
        raise FileNotFoundError(f"Cannot freeze incomplete E&P V1.4: {missing}")
    parents = _parents(root)
    metadata = json.loads(
        (root / "output/energy_valuation_v1_4_research/metadata.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        "v1_manifest_sha256": parents["v1"]["manifest_sha256"],
        "v1_1_manifest_sha256": parents["v11"]["manifest_sha256"],
        "v1_2_manifest_sha256": parents["v12"]["manifest_sha256"],
        "v1_3_manifest_sha256": parents["v13"]["manifest_sha256"],
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"V1.4 parent mismatch: {key}")
    if metadata.get("standardized_complete_cost_scope_tickers") != 1:
        raise ValueError("V1.4 approved complete cost-scope count changed")
    if metadata.get("terminal_anchor_ready") != 0:
        raise ValueError("V1.4 terminal anchor must remain locked")
    if metadata.get("wacc_range_recalibrated") is not False:
        raise ValueError("V1.4 cannot recalibrate the frozen WACC range")
    if metadata.get("production_promoted") is not False:
        raise ValueError("V1.4 research cannot be production promoted")

    manifest = {
        "name": "E&P_STANDARDIZED_COST_SCOPE_V1_4_RESEARCH",
        "version": "1.4",
        "frozen_as_of": str(date.today()),
        "immutable": True,
        "research_frozen": True,
        "cost_scope_framework_frozen": True,
        "realized_basis_diagnostic_frozen": True,
        "hedge_non_netting_policy_frozen": True,
        "standardized_complete_cost_scope_tickers": 1,
        "terminal_anchor_ready": 0,
        "terminal_anchor_replacement_allowed": False,
        "single_appropriate_wacc_claim_allowed": False,
        "parent_v1_manifest_sha256": parents["v1"]["manifest_sha256"],
        "parent_v1_1_manifest_sha256": parents["v11"]["manifest_sha256"],
        "parent_v1_2_manifest_sha256": parents["v12"]["manifest_sha256"],
        "parent_v1_3_manifest_sha256": parents["v13"]["manifest_sha256"],
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "files": {relative: _sha256(root / relative) for relative in FROZEN_FILES},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return verify_v14(root)


def verify_v14(root: Path) -> dict[str, object]:
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
        raise ValueError(f"E&P V1.4 freeze verification failed: {failures}")
    parents = _parents(root)
    expected_parents = {
        "parent_v1_manifest_sha256": parents["v1"]["manifest_sha256"],
        "parent_v1_1_manifest_sha256": parents["v11"]["manifest_sha256"],
        "parent_v1_2_manifest_sha256": parents["v12"]["manifest_sha256"],
        "parent_v1_3_manifest_sha256": parents["v13"]["manifest_sha256"],
    }
    for key, value in expected_parents.items():
        if manifest[key] != value:
            raise ValueError(f"Frozen V1.4 parent changed: {key}")
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = _sha256(manifest_path)
    manifest["verified_files"] = len(manifest["files"])
    return manifest
