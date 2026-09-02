from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path


MANIFEST = Path("benchmarks") / "energy_valuation_v1_1" / "manifest.json"
FROZEN_FILES = (
    "configs/energy_valuation_v1_1.toml",
    "energy_nowcast/valuation_v11/__init__.py",
    "energy_nowcast/valuation_v11/benchmark.py",
    "energy_nowcast/valuation_v11/engine.py",
    "energy_nowcast/valuation_v11/financial_adjustments.py",
    "energy_nowcast/valuation_v11/perimeter.py",
    "energy_nowcast/valuation_v11/sanity.py",
    "run_energy_valuation_v1_1.py",
    "tests/test_energy_valuation_v1_1.py",
    "output/energy_valuation_v1_1/capex_semantics_audit.csv",
    "output/energy_valuation_v1_1/capital_claims_reconciliation.csv",
    "output/energy_valuation_v1_1/scenario_assumptions.csv",
    "output/energy_valuation_v1_1/dcf_projections.csv",
    "output/energy_valuation_v1_1/forward_dcf_scenario_values.csv",
    "output/energy_valuation_v1_1/forward_dcf_probability_weighted.csv",
    "output/energy_valuation_v1_1/reverse_dcf_expectations.csv",
    "output/energy_valuation_v1_1/reverse_dcf_roundtrip.csv",
    "output/energy_valuation_v1_1/scenario_boundary_summary.csv",
    "output/energy_valuation_v1_1/terminal_value_audit.csv",
    "output/energy_valuation_v1_1/terminal_value_summary.csv",
    "output/energy_valuation_v1_1/historical_fcff_subindustry_summary.csv",
    "output/energy_valuation_v1_1/reverse_dcf_roundtrip_summary.csv",
    "output/energy_valuation_v1_1/subindustry_value_comparison.csv",
    "output/energy_valuation_v1_1/v1_1_requirement_audit.csv",
    "output/energy_valuation_v1_1/v1_1_completion_status.csv",
    "output/energy_valuation_v1_1/metadata.json",
    "output/energy_valuation_v1_1/report.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_v11(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    if manifest_path.exists():
        return verify_v11(root)
    missing = [path for path in FROZEN_FILES if not (root / path).exists()]
    if missing:
        raise FileNotFoundError(f"Cannot freeze incomplete Energy V1.1: {missing}")
    status_path = root / "output" / "energy_valuation_v1_1" / "v1_1_completion_status.csv"
    status = json.loads(
        (root / "output" / "energy_valuation_v1_1" / "metadata.json").read_text(
            encoding="utf-8"
        )
    )
    if not status.get("freeze_eligible", False):
        raise ValueError(f"V1.1 sanity audit is not freeze eligible: {status_path}")
    manifest = {
        "name": "ENERGY_VALUATION_PLATFORM_V1_1_SANITY_AUDITED",
        "version": "1.1",
        "frozen_as_of": str(date.today()),
        "immutable": True,
        "sanity_audit_passed": True,
        "code_frozen": True,
        "research_frozen": True,
        "data_schema_frozen": True,
        "parser_specs_frozen": True,
        "anchors_frozen": True,
        "bridges_frozen": True,
        "dcf_engine_frozen": True,
        "reverse_dcf_frozen": True,
        "scenarios_frozen": True,
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "files": {path: _sha256(root / path) for path in FROZEN_FILES},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return verify_v11(root)


def verify_v11(root: Path) -> dict[str, object]:
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
        raise ValueError(f"Energy V1.1 freeze verification failed: {failures}")
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = _sha256(manifest_path)
    manifest["verified_files"] = len(manifest["files"])
    return manifest
