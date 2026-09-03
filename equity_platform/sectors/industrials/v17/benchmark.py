from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import freeze_manifest, verify_manifest


MANIFEST = Path("benchmarks/industrials_cat_margin_v1_7/manifest.json")


def _files(root: Path) -> list[str]:
    source_manifest = json.loads(
        (root / "data-lake/bronze/industrials/v1_7/sec/cat/manifest.json").read_text(encoding="utf-8")
    )
    sec_files = [str(item["local_path"]) for item in source_manifest["files"]]
    code = [
        "configs/industrials_v1_7.toml",
        "data-lake/bronze/industrials/v1_7/sec/cat/manifest.json",
        "equity_platform/sectors/industrials/v17/__init__.py",
        "equity_platform/sectors/industrials/v17/application_mix.py",
        "equity_platform/sectors/industrials/v17/benchmark.py",
        "equity_platform/sectors/industrials/v17/margin.py",
        "equity_platform/sectors/industrials/v17/profit_drivers.py",
        "equity_platform/sectors/industrials/v17/reinvestment.py",
        "equity_platform/sectors/industrials/v17/research.py",
        "equity_platform/sectors/industrials/v17/sources.py",
        "scripts/industrials/fetch_cat_periodic_filings_v1_7.py",
        "scripts/industrials/freeze_margin_v1_7.py",
        "scripts/industrials/valuation_v1_7.py",
        "tests/test_industrials_margin_v1_7_freeze.py",
        "tests/test_industrials_valuation_v1_7.py",
    ]
    outputs = [path.relative_to(root).as_posix() for path in sorted((root / "output/industrials_valuation_v1_7_research").glob("*")) if path.is_file()]
    return code + sec_files + outputs


def _assertions(root: Path) -> dict[str, object]:
    output = root / "output/industrials_valuation_v1_7_research"
    gate = pd.read_csv(output / "industrials_v1_7_gate.csv").iloc[0]
    margin = pd.read_csv(output / "margin_route_summary.csv")
    source = pd.read_csv(output / "v1_7_source_audit_summary.csv").iloc[0]
    notes = pd.read_csv(output / "reinvestment_roic_evidence_summary.csv").iloc[0]
    return {
        "benchmark_scope": "CAT_SEGMENT_MARGIN_RESEARCH_ONLY",
        "research_freeze_eligible": bool(gate["research_freeze_eligible"]),
        "margin_champion_segments": int(margin["margin_champion_eligible"].sum()),
        "maximum_selected_margin_mase": float(margin["selected_margin_mase"].max()),
        "oos_observations_per_segment": int(margin["validation_observations"].min()),
        "historical_pit_coverage_pct": float(gate["historical_pit_coverage_pct"]),
        "sec_periodic_filings": int(source["sec_filings"]),
        "ir_earnings_releases": int(source["ir_earnings_releases"]),
        "quarterly_discrete_note_rows_complete": int(notes["quarterly_discrete_complete_rows"]),
        "unforecastable_scope_change_rows": int(gate["unforecastable_scope_change_rows"]),
        "terminal_input_allowed": bool(gate["terminal_input_allowed"]),
        "new_dcf_run": bool(gate["new_dcf_run"]),
        "new_reverse_dcf_run": bool(gate["new_reverse_dcf_run"]),
        "production_promoted": bool(gate["production_promotable"]),
        "pdf_parsing_used": False,
    }


def freeze_margin_v1_7(root: Path) -> dict[str, object]:
    parent = verify_manifest(root=root, manifest_path=Path("benchmarks/industrials_cat_revenue_champion_v1/manifest.json"))
    assertions = _assertions(root)
    if not assertions["research_freeze_eligible"]:
        raise ValueError("V1.7 margin research gate is not eligible for freeze")
    return freeze_manifest(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_CAT_MARGIN_V1_7",
        version="1.7",
        relative_paths=_files(root),
        assertions=assertions,
        parents={"industrials_cat_revenue_champion_v1": parent["manifest_sha256"]},
    )


def verify_margin_v1_7(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
