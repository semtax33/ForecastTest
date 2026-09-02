from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


MANIFEST = Path("benchmarks") / "ep_normalized_unit_economics_v1_3" / "manifest.json"
FROZEN_FILES = (
    "energy_nowcast/research/ep_v13/__init__.py",
    "energy_nowcast/research/ep_v13/benchmark.py",
    "energy_nowcast/research/ep_v13/unit_economics.py",
    "energy_nowcast/research/ep_v13/wacc_research.py",
    "run_ep_normalized_unit_economics_v1_3.py",
    "freeze_ep_normalized_unit_economics_v1_3.py",
    "tests/test_ep_normalized_unit_economics_v1_3.py",
    "output/energy_valuation_v1_3_research/annual_unit_economics_panel.csv",
    "output/energy_valuation_v1_3_research/beta_term_structure.csv",
    "output/energy_valuation_v1_3_research/data_coverage.csv",
    "output/energy_valuation_v1_3_research/double_count_gate.csv",
    "output/energy_valuation_v1_3_research/metadata.json",
    "output/energy_valuation_v1_3_research/normalized_price_reference.csv",
    "output/energy_valuation_v1_3_research/production_mix_price_proxy.csv",
    "output/energy_valuation_v1_3_research/report.md",
    "output/energy_valuation_v1_3_research/reserve_quantity_panel.csv",
    "output/energy_valuation_v1_3_research/risk_allocation_policy.csv",
    "output/energy_valuation_v1_3_research/unit_economics_cross_check.csv",
    "output/energy_valuation_v1_3_research/unit_economics_summary.csv",
    "output/energy_valuation_v1_3_research/v11_scenario_risk_coupling_audit.csv",
    "output/energy_valuation_v1_3_research/wacc_cross_comparison.csv",
    "output/energy_valuation_v1_3_research/wacc_reference_range.csv",
    "output/energy_valuation_v1_3_research/wacc_reference_summary.csv",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_v13(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    if manifest_path.exists():
        return verify_v13(root)
    missing = [relative for relative in FROZEN_FILES if not (root / relative).exists()]
    if missing:
        raise FileNotFoundError(f"Cannot freeze incomplete E&P V1.3: {missing}")
    parents = {
        "v1": verify_v1(root),
        "v11": verify_v11(root),
        "v12": verify_v12(root),
    }
    metadata = json.loads(
        (root / "output/energy_valuation_v1_3_research/metadata.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        "v1_manifest_sha256": parents["v1"]["manifest_sha256"],
        "v1_1_manifest_sha256": parents["v11"]["manifest_sha256"],
        "v1_2_manifest_sha256": parents["v12"]["manifest_sha256"],
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"V1.3 parent mismatch: {key}")
    if metadata.get("terminal_anchor_ready") != 0:
        raise ValueError("V1.3 terminal anchor must remain locked")
    if metadata.get("single_appropriate_wacc_claim_allowed") is not False:
        raise ValueError("V1.3 cannot freeze a single appropriate WACC claim")
    if metadata.get("double_count_gate") is not True:
        raise ValueError("V1.3 risk-channel gate did not pass")
    if metadata.get("production_promoted") is not False:
        raise ValueError("V1.3 research cannot be production promoted")

    manifest = {
        "name": "E&P_NORMALIZED_UNIT_ECONOMICS_V1_3_RESEARCH",
        "version": "1.3",
        "frozen_as_of": str(date.today()),
        "immutable": True,
        "research_frozen": True,
        "unit_economics_cross_check_frozen": True,
        "independent_wacc_range_frozen": True,
        "risk_channel_policy_frozen": True,
        "terminal_anchor_ready": 0,
        "single_appropriate_wacc_claim_allowed": False,
        "parent_v1_manifest_sha256": parents["v1"]["manifest_sha256"],
        "parent_v1_1_manifest_sha256": parents["v11"]["manifest_sha256"],
        "parent_v1_2_manifest_sha256": parents["v12"]["manifest_sha256"],
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "files": {relative: _sha256(root / relative) for relative in FROZEN_FILES},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return verify_v13(root)


def verify_v13(root: Path) -> dict[str, object]:
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
        raise ValueError(f"E&P V1.3 freeze verification failed: {failures}")
    parents = {
        "parent_v1_manifest_sha256": verify_v1(root)["manifest_sha256"],
        "parent_v1_1_manifest_sha256": verify_v11(root)["manifest_sha256"],
        "parent_v1_2_manifest_sha256": verify_v12(root)["manifest_sha256"],
    }
    for key, value in parents.items():
        if manifest[key] != value:
            raise ValueError(f"Frozen V1.3 parent changed: {key}")
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = _sha256(manifest_path)
    manifest["verified_files"] = len(manifest["files"])
    return manifest
