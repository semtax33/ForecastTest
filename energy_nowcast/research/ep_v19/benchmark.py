from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.artifacts import freeze_manifest, verify_manifest
from energy_nowcast.research.ep_v174.benchmark import verify_v174

from .parent import v18_parent_snapshot


MANIFEST = Path("benchmarks") / "ep_sample_stability_v1_9" / "manifest.json"
FROZEN_FILES = (
    "equity_platform/artifacts.py",
    "configs/ep_v19_rrc_sources.csv",
    "configs/ep_v19_selection_policy.csv",
    "energy_nowcast/research/ep_v19/__init__.py",
    "energy_nowcast/research/ep_v19/attribution.py",
    "energy_nowcast/research/ep_v19/benchmark.py",
    "energy_nowcast/research/ep_v19/cohort.py",
    "energy_nowcast/research/ep_v19/gate.py",
    "energy_nowcast/research/ep_v19/parent.py",
    "energy_nowcast/research/ep_v19/stability.py",
    "scripts/energy/research/ep/v1_9_sample_stability.py",
    "scripts/energy/research/freeze/ep_v1_9.py",
    "tests/test_ep_sample_stability_uncertainty_decomposition_v1_9.py",
    "tests/test_ep_sample_stability_v1_9_freeze.py",
    "output/energy_valuation_v1_9_research/dvn_fang_range_width_attribution.csv",
    "output/energy_valuation_v1_9_research/expanded_company_organic_roic_ranges.csv",
    "output/energy_valuation_v1_9_research/expanded_leave_one_cohort_out_robustness.csv",
    "output/energy_valuation_v1_9_research/expanded_through_cycle_roic_distribution.csv",
    "output/energy_valuation_v1_9_research/metadata.json",
    "output/energy_valuation_v1_9_research/range_width_component_attribution.csv",
    "output/energy_valuation_v1_9_research/report.md",
    "output/energy_valuation_v1_9_research/rrc_annual_source_evidence.csv",
    "output/energy_valuation_v1_9_research/rrc_clean_organic_cohort.csv",
    "output/energy_valuation_v1_9_research/rrc_clean_window_candidate_audit.csv",
    "output/energy_valuation_v1_9_research/rrc_selected_normalization_evidence.csv",
    "output/energy_valuation_v1_9_research/sample_stability_comparison.csv",
    "output/energy_valuation_v1_9_research/v1_9_gate.csv",
)


def _freeze_assertions(root: Path) -> dict[str, object]:
    gate = pd.read_csv(
        root / "output/energy_valuation_v1_9_research/v1_9_gate.csv"
    ).iloc[0]
    ranges = pd.read_csv(
        root
        / "output/energy_valuation_v1_9_research/expanded_company_organic_roic_ranges.csv"
    )
    required_true = (
        "v1_9_research_gate",
        "sample_stability_issue_resolved",
        "uncertainty_decomposition_issue_resolved",
        "v1_9_research_freeze_eligible",
        "terminal_replacement_remains_locked",
    )
    failed = [column for column in required_true if not bool(gate[column])]
    if failed:
        raise ValueError(f"V1.9 freeze gate failed: {failed}")
    if int(gate["cohort_count"]) != 4 or int(gate["strong_or_usable_range_count"]) < 2:
        raise ValueError("V1.9 freeze requires four cohorts and two usable ranges")
    if float(gate["max_abs_loco_p50_shift_pct_points"]) > 10.0:
        raise ValueError("V1.9 LOCO stability threshold failed")
    if ranges["normal_roic_claimed"].any() or ranges["terminal_input_allowed"].any():
        raise ValueError("V1.9 cannot claim normal ROIC or unlock terminal inputs")
    if bool(gate["production_promoted"]):
        raise ValueError("V1.9 cannot promote production")
    return {
        "cohort_count": 4,
        "strong_or_usable_range_count": int(gate["strong_or_usable_range_count"]),
        "max_abs_loco_p50_shift_pct_points": float(
            gate["max_abs_loco_p50_shift_pct_points"]
        ),
        "sample_stability_issue_resolved": True,
        "uncertainty_decomposition_issue_resolved": True,
        "normal_roic_claimed": False,
        "terminal_anchor_replacement_allowed": False,
        "wacc_recalibrated": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
    }


def freeze_v19(root: Path) -> dict[str, object]:
    assertions = _freeze_assertions(root)
    v18 = v18_parent_snapshot(root)
    v174 = verify_v174(root)
    return freeze_manifest(
        root=root,
        manifest_path=MANIFEST,
        name="E&P_SAMPLE_STABILITY_UNCERTAINTY_DECOMPOSITION_V1_9_RESEARCH",
        version="1.9",
        relative_paths=FROZEN_FILES,
        assertions=assertions,
        parents={
            "v1_8_snapshot_sha256": str(v18["snapshot_sha256"]),
            "v1_7_4_manifest_sha256": str(v174["manifest_sha256"]),
        },
    )


def verify_v19(root: Path) -> dict[str, object]:
    manifest = verify_manifest(root=root, manifest_path=MANIFEST)
    v18 = v18_parent_snapshot(root)
    v174 = verify_v174(root)
    if manifest["parents"]["v1_8_snapshot_sha256"] != v18["snapshot_sha256"]:
        raise ValueError("Frozen V1.9 V1.8 parent changed")
    if manifest["parents"]["v1_7_4_manifest_sha256"] != v174["manifest_sha256"]:
        raise ValueError("Frozen V1.9 V1.7.4 parent changed")
    return manifest
