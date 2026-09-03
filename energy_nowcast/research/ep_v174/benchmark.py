from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.research.ep_v161.benchmark import verify_v161
from scripts.energy.research.ep.v1_7_4_cohort_closure import (
    _v173_snapshot,
)


MANIFEST = Path("benchmarks") / "ep_cohort_closure_v1_7_4" / "manifest.json"
FROZEN_FILES = (
    "energy_nowcast/research/ep_v174/__init__.py",
    "energy_nowcast/research/ep_v174/benchmark.py",
    "energy_nowcast/research/ep_v174/closure.py",
    "energy_nowcast/research/ep_v174/gate.py",
    "energy_nowcast/research/ep_v174/reconciliation.py",
    "configs/ep_v174_transaction_perimeter_evidence.csv",
    "scripts/energy/research/ep/v1_7_4_cohort_closure.py",
    "scripts/energy/research/freeze/ep_v1_7_4.py",
    "tests/test_ep_cohort_closure_organic_roic_validation_v1_7_4.py",
    "output/energy_valuation_v1_7_4_research/fang_transaction_perimeter_evidence.csv",
    "output/energy_valuation_v1_7_4_research/fang_divestiture_nopat_range.csv",
    "output/energy_valuation_v1_7_4_research/dvn_nopat_discrepancy_reconciliation.csv",
    "output/energy_valuation_v1_7_4_research/scope_adjusted_nopat_triangulation.csv",
    "output/energy_valuation_v1_7_4_research/closed_three_year_cohorts.csv",
    "output/energy_valuation_v1_7_4_research/organic_roic_validation_ranges.csv",
    "output/energy_valuation_v1_7_4_research/v1_7_4_gate.csv",
    "output/energy_valuation_v1_7_4_research/metadata.json",
    "output/energy_valuation_v1_7_4_research/report.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_v174(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    if manifest_path.exists():
        return verify_v174(root)
    missing = [relative for relative in FROZEN_FILES if not (root / relative).exists()]
    if missing:
        raise FileNotFoundError(f"Cannot freeze incomplete E&P V1.7.4: {missing}")

    v161 = verify_v161(root)
    v173_snapshot = _v173_snapshot()
    output = root / "output" / "energy_valuation_v1_7_4_research"
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    gate = pd.read_csv(output / "v1_7_4_gate.csv").iloc[0]
    validation = pd.read_csv(output / "organic_roic_validation_ranges.csv")

    if metadata.get("v1_6_1_manifest_sha256") != v161["manifest_sha256"]:
        raise ValueError("V1.7.4 frozen V1.6.1 parent mismatch")
    if metadata.get("v1_7_3_parent_snapshot_sha256") != v173_snapshot:
        raise ValueError("V1.7.4 V1.7.3 parent snapshot mismatch")
    if metadata.get("research_freeze_eligible") is not True:
        raise ValueError("V1.7.4 metadata freeze gate is not satisfied")
    if not bool(gate["v1_7_4_research_freeze_eligible"]):
        raise ValueError("V1.7.4 CSV freeze gate is not satisfied")
    exact_counts = {
        "complete_reported_3y_cohort_tickers": 2,
        "complete_independent_full_cycle_cohort_tickers": 2,
        "triangulated_nopat_validated_cohort_tickers": 2,
        "validated_organic_roic_tickers": 2,
        "unresolved_material_transaction_perimeters": 0,
    }
    for column, expected in exact_counts.items():
        if int(gate[column]) != expected:
            raise ValueError(f"V1.7.4 freeze count changed: {column}")
    if int(validation["organic_company_roic_validated"].sum()) != 2:
        raise ValueError("V1.7.4 must validate exactly two company cohorts")
    if validation["normal_roic_claimed"].any():
        raise ValueError("V1.7.4 cannot claim a normal ROIC")
    if validation["terminal_input_allowed"].any():
        raise ValueError("V1.7.4 cannot unlock terminal inputs")
    if bool(gate["terminal_anchor_replacement_allowed"]):
        raise ValueError("V1.7.4 terminal replacement must remain locked")
    if bool(gate["production_promoted"]):
        raise ValueError("V1.7.4 cannot promote production")

    manifest = {
        "name": "E&P_COHORT_CLOSURE_ORGANIC_ROIC_VALIDATION_V1_7_4_RESEARCH",
        "version": "1.7.4",
        "frozen_as_of": str(date.today()),
        "immutable": True,
        "research_frozen": True,
        "cohort_closure_framework_frozen": True,
        "dvn_nopat_reconciliation_frozen": True,
        "complete_reported_3y_cohort_tickers": 2,
        "complete_independent_full_cycle_cohort_tickers": 2,
        "triangulated_nopat_validated_cohort_tickers": 2,
        "validated_organic_roic_tickers": 2,
        "unresolved_material_transaction_perimeters": 0,
        "normal_roic_claimed": False,
        "terminal_anchor_ready": 0,
        "terminal_anchor_replacement_allowed": False,
        "wacc_recalibrated": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "parent_v1_6_1_manifest_sha256": v161["manifest_sha256"],
        "parent_v1_7_3_snapshot_sha256": v173_snapshot,
        "files": {relative: _sha256(root / relative) for relative in FROZEN_FILES},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return verify_v174(root)


def verify_v174(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for relative, expected in manifest["files"].items():
        path = root / relative
        if not path.exists():
            failures.append(f"missing:{relative}")
        elif _sha256(path) != expected:
            failures.append(f"hash:{relative}")
    if failures:
        raise ValueError(f"E&P V1.7.4 freeze verification failed: {failures}")
    v161 = verify_v161(root)
    if manifest["parent_v1_6_1_manifest_sha256"] != v161["manifest_sha256"]:
        raise ValueError("Frozen V1.7.4 V1.6.1 parent changed")
    if manifest["parent_v1_7_3_snapshot_sha256"] != _v173_snapshot():
        raise ValueError("Frozen V1.7.4 V1.7.3 parent changed")
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = _sha256(manifest_path)
    manifest["verified_files"] = len(manifest["files"])
    return manifest
