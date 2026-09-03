from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path


MANIFEST = Path("benchmarks") / "energy_valuation_v1" / "manifest.json"
FROZEN_FILES = (
    "configs/energy_valuation_v1.toml",
    "configs/energy_v1_market_price_overrides.csv",
    "energy_nowcast/valuation/__init__.py",
    "energy_nowcast/valuation/benchmark.py",
    "energy_nowcast/valuation/financials.py",
    "energy_nowcast/valuation/market.py",
    "energy_nowcast/valuation/valuation.py",
    "scripts/energy/research/valuation/v1.py",
    "tests/test_energy_valuation_v1.py",
    "output/energy_valuation_v1/v1_completion_status.csv",
    "output/energy_valuation_v1/v1_requirement_audit.csv",
    "output/energy_valuation_v1/quarterly_financial_bridge.parquet",
    "output/energy_valuation_v1/ttm_financial_bridge.parquet",
    "output/energy_valuation_v1/latest_financial_bridge.csv",
    "output/energy_valuation_v1/source_coverage.csv",
    "output/energy_valuation_v1/anchor_growth_inputs.csv",
    "output/energy_valuation_v1/market_inputs.csv",
    "output/energy_valuation_v1/market_input_coverage.csv",
    "output/energy_valuation_v1/scenario_assumptions.csv",
    "output/energy_valuation_v1/dcf_projections.csv",
    "output/energy_valuation_v1/forward_dcf_scenario_values.csv",
    "output/energy_valuation_v1/forward_dcf_probability_weighted.csv",
    "output/energy_valuation_v1/reverse_dcf_expectations.csv",
    "output/energy_valuation_v1/expectations_gap.csv",
    "output/energy_valuation_v1/latest_valuation_scorecard.csv",
    "output/energy_valuation_v1/subindustry_valuation_scorecard.csv",
    "output/energy_valuation_v1/metadata.json",
    "output/energy_valuation_v1/report.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_v1(root: Path) -> dict[str, object]:
    manifest_path = root / MANIFEST
    if manifest_path.exists():
        return verify_v1(root)
    missing = [path for path in FROZEN_FILES if not (root / path).exists()]
    if missing:
        raise FileNotFoundError(f"Cannot freeze incomplete Energy V1: {missing}")
    manifest = {
        "name": "ENERGY_VALUATION_PLATFORM_V1_RESEARCH",
        "version": "1.0",
        "frozen_as_of": str(date.today()),
        "immutable": True,
        "code_complete": True,
        "research_complete": True,
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "files": {path: _sha256(root / path) for path in FROZEN_FILES},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return verify_v1(root)


def verify_v1(root: Path) -> dict[str, object]:
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
        raise ValueError(f"Energy V1 freeze verification failed: {failures}")
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = _sha256(manifest_path)
    manifest["verified_files"] = len(manifest["files"])
    return manifest
