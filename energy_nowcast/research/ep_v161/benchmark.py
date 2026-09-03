from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v12.benchmark import verify_v12
from energy_nowcast.research.ep_v13.benchmark import verify_v13
from energy_nowcast.research.ep_v14.benchmark import verify_v14
from energy_nowcast.research.ep_v15.benchmark import verify_v15
from energy_nowcast.valuation.benchmark import verify_v1
from energy_nowcast.valuation_v11.benchmark import verify_v11


MANIFEST = Path("benchmarks") / "ep_accounting_proof_v1_6_1" / "manifest.json"
FROZEN_FILES = (
    "energy_nowcast/research/ep_v161/__init__.py",
    "energy_nowcast/research/ep_v161/accounting.py",
    "energy_nowcast/research/ep_v161/benchmark.py",
    "energy_nowcast/research/ep_v161/capital.py",
    "energy_nowcast/research/ep_v161/gate.py",
    "scripts/energy/research/ep/v1_6_1_accounting_proof.py",
    "scripts/energy/research/freeze/ep_v1_6_1.py",
    "tests/test_ep_accounting_proof_v1_6_1.py",
    "output/energy_valuation_v1_6_1_research/annual_mna_normalized_capital_bridge.csv",
    "output/energy_valuation_v1_6_1_research/ar_composite_cost_scope_proof.csv",
    "output/energy_valuation_v1_6_1_research/cnx_hedge_accounting_reconciliation.csv",
    "output/energy_valuation_v1_6_1_research/core_accounting_proof_summary.csv",
    "output/energy_valuation_v1_6_1_research/fang_margin_gap_attribution.csv",
    "output/energy_valuation_v1_6_1_research/metadata.json",
    "output/energy_valuation_v1_6_1_research/mna_normalized_roic_summary.csv",
    "output/energy_valuation_v1_6_1_research/report.md",
    "output/energy_valuation_v1_6_1_research/v1_6_1_freeze_gate.csv",
)
V16_SOURCE_DEPENDENCIES = (
    "output/energy_valuation_v1_6_research/fang_v16_accounting_reconciliation.csv",
    "output/energy_valuation_v1_6_research/terminal_candidate_gate.csv",
    "output/energy_valuation_v1_6_research/three_level_roic_summary.csv",
    "output/energy_valuation_v1_6_research/v16_coverage_completion_gate.csv",
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
        "v14": verify_v14(root),
        "v15": verify_v15(root),
    }


def freeze_v161(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    if manifest_path.exists():
        return verify_v161(root)
    required = (*FROZEN_FILES, *V16_SOURCE_DEPENDENCIES)
    missing = [relative for relative in required if not (root / relative).exists()]
    if missing:
        raise FileNotFoundError(f"Cannot freeze incomplete E&P V1.6.1: {missing}")

    parents = _parents(root)
    output = root / "output" / "energy_valuation_v1_6_1_research"
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    expected_parents = {
        "v1_manifest_sha256": parents["v1"]["manifest_sha256"],
        "v11_manifest_sha256": parents["v11"]["manifest_sha256"],
        "v12_manifest_sha256": parents["v12"]["manifest_sha256"],
        "v13_manifest_sha256": parents["v13"]["manifest_sha256"],
        "v14_manifest_sha256": parents["v14"]["manifest_sha256"],
        "v15_manifest_sha256": parents["v15"]["manifest_sha256"],
    }
    for key, value in expected_parents.items():
        if metadata.get(key) != value:
            raise ValueError(f"V1.6.1 parent mismatch: {key}")
    if metadata.get("freeze_eligible") is not True:
        raise ValueError("V1.6.1 freeze gate is not satisfied")
    if metadata.get("core_accounting_pass_tickers") != 3:
        raise ValueError("V1.6.1 core accounting proof must pass 3/3")
    if metadata.get("mna_normalization_diagnostic_implemented") is not True:
        raise ValueError("V1.6.1 M&A diagnostic is missing")
    if metadata.get("mna_normalization_validated") is not False:
        raise ValueError("V1.6.1 must not overclaim validated M&A normalization")
    gate = pd.read_csv(output / "v1_6_1_freeze_gate.csv").iloc[0]
    if not bool(gate["v1_6_1_research_freeze_eligible"]):
        raise ValueError("V1.6.1 CSV freeze gate is not satisfied")
    if int(gate["terminal_candidate_ready_tickers"]) != 0:
        raise ValueError("V1.6.1 terminal replacement must remain locked")
    if bool(gate["production_promoted"]):
        raise ValueError("V1.6.1 cannot promote production")

    manifest = {
        "name": "E&P_ACCOUNTING_PROVEN_V1_6_1_RESEARCH",
        "version": "1.6.1",
        "frozen_as_of": str(date.today()),
        "immutable": True,
        "research_frozen": True,
        "accounting_proof_frozen": True,
        "v1_6_source_dependencies_hash_pinned": True,
        "reserve_chain_ready_tickers": 9,
        "reserve_coverage_target_met": True,
        "all_group_coverage_targets_met": True,
        "core_accounting_pass_tickers": 3,
        "core_accounting_target_tickers": 2,
        "mna_normalization_diagnostic_implemented": True,
        "mna_normalization_validated": False,
        "terminal_anchor_ready": 0,
        "terminal_anchor_replacement_allowed": False,
        "wacc_recalibrated": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
        **{
            f"parent_{key}_manifest_sha256": value["manifest_sha256"]
            for key, value in parents.items()
        },
        "source_dependencies": {
            relative: _sha256(root / relative)
            for relative in V16_SOURCE_DEPENDENCIES
        },
        "files": {relative: _sha256(root / relative) for relative in FROZEN_FILES},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return verify_v161(root)


def verify_v161(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for section in ("files", "source_dependencies"):
        for relative, expected in manifest[section].items():
            path = root / relative
            if not path.exists():
                failures.append(f"missing:{relative}")
            elif _sha256(path) != expected:
                failures.append(f"hash:{relative}")
    if failures:
        raise ValueError(f"E&P V1.6.1 freeze verification failed: {failures}")
    parents = _parents(root)
    for key, value in parents.items():
        if manifest[f"parent_{key}_manifest_sha256"] != value["manifest_sha256"]:
            raise ValueError(f"Frozen V1.6.1 parent changed: {key}")
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = _sha256(manifest_path)
    manifest["verified_files"] = len(manifest["files"])
    manifest["verified_source_dependencies"] = len(manifest["source_dependencies"])
    return manifest
