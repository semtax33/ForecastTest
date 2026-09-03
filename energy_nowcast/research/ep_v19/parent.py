from __future__ import annotations

import hashlib
import json
from pathlib import Path


V18_PARENT_PATHS = (
    "configs/ep_v18_ar_segment_sources.csv",
    "configs/ep_v18_distribution_policy.csv",
    "energy_nowcast/research/ep_v18/__init__.py",
    "energy_nowcast/research/ep_v18/distribution.py",
    "energy_nowcast/research/ep_v18/gas_cohort.py",
    "energy_nowcast/research/ep_v18/gate.py",
    "scripts/energy/research/ep/v1_8_through_cycle_distribution.py",
    "tests/test_ep_through_cycle_organic_roic_distribution_v1_8.py",
    "output/energy_valuation_v1_8_research/ar_clean_organic_cohort.csv",
    "output/energy_valuation_v1_8_research/ar_segment_annual_evidence.csv",
    "output/energy_valuation_v1_8_research/company_organic_roic_ranges.csv",
    "output/energy_valuation_v1_8_research/gas_heavy_candidate_audit.csv",
    "output/energy_valuation_v1_8_research/leave_one_cohort_out_robustness.csv",
    "output/energy_valuation_v1_8_research/metadata.json",
    "output/energy_valuation_v1_8_research/report.md",
    "output/energy_valuation_v1_8_research/roic_range_width_gate.csv",
    "output/energy_valuation_v1_8_research/three_level_roic_comparison.csv",
    "output/energy_valuation_v1_8_research/through_cycle_roic_distribution.csv",
    "output/energy_valuation_v1_8_research/v1_8_gate.csv",
)


def v18_parent_snapshot(root: Path) -> dict[str, object]:
    hashes: dict[str, str] = {}
    for relative in V18_PARENT_PATHS:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Missing V1.8 parent file: {relative}")
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = json.dumps(hashes, sort_keys=True, separators=(",", ":"))
    return {
        "snapshot_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "verified_files": len(hashes),
        "files": hashes,
    }
