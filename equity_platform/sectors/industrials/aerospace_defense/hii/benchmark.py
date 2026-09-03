from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import verify_manifest
from equity_platform.core.freeze import freeze_research_benchmark


MANIFEST = Path("benchmarks/industrials_platform_v5_hii_evidence/manifest.json")
OUTPUT = Path("output/industrials_v5_hii_third_company_research")
SEC_ROOT = Path("data-lake/bronze/industrials/v5/sec/hii")


def _files(root: Path) -> list[str]:
    code = [
        "configs/industrials_v5_ad_third_company_candidates.csv",
        "configs/industrials_v5_hii.toml",
        "configs/industrials_v5_hii_bls_sensors.csv",
        "equity_platform/sectors/industrials/aerospace_defense/hii/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/benchmark.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/forecast.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/industry.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/ir.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/sec.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/selection.py",
        "scripts/industrials/fetch_hii_periodic_filings_v5.py",
        "scripts/industrials/freeze_v5_hii_evidence.py",
        "scripts/industrials/select_ad_third_company_v5.py",
        "scripts/industrials/valuation_v5_hii.py",
        "tests/test_industrials_v5_hii.py",
        "tests/test_industrials_v5_hii_evidence_freeze.py",
    ]
    sources = [
        path.relative_to(root).as_posix()
        for path in sorted((root / SEC_ROOT).rglob("*")) if path.is_file()
    ]
    outputs = [
        path.relative_to(root).as_posix()
        for path in sorted((root / OUTPUT).glob("*")) if path.is_file()
    ]
    return code + sources + outputs


def _assertions(root: Path) -> dict[str, object]:
    selection = pd.read_csv(root / OUTPUT / "ad_third_company_selected.csv").iloc[0]
    source = pd.read_csv(root / OUTPUT / "hii_sec_source_summary.csv").iloc[0]
    parser = pd.read_csv(root / OUTPUT / "hii_ir_parser_summary.csv").iloc[0]
    industry = pd.read_csv(root / OUTPUT / "hii_industry_data_summary.csv").iloc[0]
    authority = pd.read_csv(root / OUTPUT / "hii_forecast_authority.csv").iloc[0]
    gate = pd.read_csv(root / OUTPUT / "industrials_v5_hii_gate.csv").iloc[0]
    hypothesis = pd.read_csv(root / OUTPUT / "aerospace_defense_three_company_hypothesis.csv").iloc[0]
    roic = pd.read_csv(root / OUTPUT / "hii_reinvestment_roic_summary.csv").iloc[0]
    uncertainty = pd.read_csv(root / OUTPUT / "hii_uncertainty_gate.csv").iloc[0]
    metadata = json.loads((root / OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    return {
        "benchmark_scope": "HII_THIRD_COMPANY_EVIDENCE_PARSER_AND_FIXED_OOS_RESEARCH_RECORD",
        "research_freeze_eligible": bool(gate["evidence_parser_freeze_eligible"]),
        "selected_ticker": selection["ticker"],
        "selection_outcome_blind": bool(selection["selection_outcome_blind"]),
        "performance_fields_used_for_selection": 0,
        "sec_filings": int(source["sec_filings"]),
        "sec_10k_filings": int(source["sec_10k_filings"]),
        "sec_10q_filings": int(source["sec_10q_filings"]),
        "sec_ir_comparable_cells": int(source["segment_metric_comparable_cells"]),
        "sec_ir_identity_pass_cells": int(source["segment_metric_identity_pass_cells"]),
        "ir_earnings_releases": int(parser["selected_quarterly_ir_releases"]),
        "segment_quarter_rows": int(parser["segment_quarter_rows"]),
        "dual_history_authorities_separate": bool(parser["as_reported_and_currently_recast_histories_separate"]),
        "bls_as_released_vintage_rows": int(industry["bls_archive_vintage_rows"]),
        "dedicated_shipbuilding_output_series_available": bool(industry["dedicated_shipbuilding_output_series_available"]),
        "fixed_validation_window": metadata["fixed_validation_window"],
        "aggregate_revenue_point_authority": bool(authority["aggregate_revenue_point_authority"]),
        "aggregate_revenue_champion_route": authority["aggregate_revenue_champion_route"],
        "aggregate_revenue_mase": float(authority["aggregate_revenue_mase"]),
        "aggregate_revenue_mean_ape_pct": float(authority["aggregate_revenue_mean_ape_pct"]),
        "funded_backlog_incremental_value": authority["funded_backlog_incremental_value"],
        "segment_revenue_attribution_authority": bool(authority["segment_revenue_attribution_authority"]),
        "margin_authority": bool(authority["margin_authority"]),
        "uncertainty_authority": bool(uncertainty["uncertainty_authority"]),
        "historical_roic_reinvestment_diagnostic_ready": bool(roic["research_evidence_ready"]),
        "roic_reinvestment_authority": authority["roic_reinvestment_authority"],
        "three_company_aggregate_pass": bool(hypothesis["all_three_aggregate_revenue_pass"]),
        "three_company_segment_timing_mixed": bool(hypothesis["segment_timing_mixed_across_three_companies"]),
        "industry_conclusion_allowed": bool(hypothesis["industry_conclusion_allowed"]),
        "forecast_freeze_eligible": bool(gate["forecast_freeze_eligible"]),
        "terminal_input_allowed": bool(gate["terminal_gate_pass"]),
        "production_promoted": bool(gate["production_gate_pass"]),
        "new_dcf_run": bool(gate["new_dcf_run"]),
        "new_reverse_dcf_run": bool(gate["new_reverse_dcf_run"]),
        "pdf_parsing_used": bool(metadata["pdf_parsing_used"]),
    }


def freeze_hii_v5_evidence(root: Path) -> dict[str, object]:
    metadata = json.loads((root / OUTPUT / "metadata.json").read_text(encoding="utf-8"))
    return freeze_research_benchmark(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_PLATFORM_V5_HII_EVIDENCE_AND_THIRD_COMPANY_EXPERIMENT",
        version="5.0-evidence",
        relative_paths=_files(root),
        assertions=_assertions(root),
        parents={
            "lmt_v31_evidence_manifest": metadata["parent_manifest_sha256"]["lmt_v31"],
            "noc_v4_evidence_manifest": metadata["parent_manifest_sha256"]["noc_v4"],
            "noc_aggregate_v1_manifest": metadata["parent_manifest_sha256"]["noc_aggregate_v1"],
        },
    )


def verify_hii_v5_evidence(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
