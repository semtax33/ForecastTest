from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.artifacts import verify_manifest
from equity_platform.core.freeze import freeze_research_benchmark
from equity_platform.sectors.industrials.aerospace_defense.hii_v54 import (
    verify_hii_v54_margin_mechanism_research,
)


MANIFEST = Path("benchmarks/industrials_v6_gd_fourth_company/manifest.json")
OUTPUT = Path("output/industrials_v6_gd_fourth_company_research")


def freeze_gd_v6_research(root: Path) -> dict[str, object]:
    gate = pd.read_csv(root / OUTPUT / "industrials_v6_gd_gate.csv").iloc[0]
    valuation = pd.read_csv(root / OUTPUT / "gd_conditional_valuation_summary.csv").iloc[0]
    parent = verify_hii_v54_margin_mechanism_research(root)
    files = [
        "configs/industrials_v6_gd.toml",
        "configs/industrials_v6_gd_bls_sensors.csv",
        "data-lake/bronze/industrials/v6/sec/gd/manifest.json",
        "data-lake/bronze/industrials/v6/market/gd/adjusted_close_daily.csv",
        "data-lake/bronze/industrials/v6/market/gd/adjusted_close_weekly.csv",
        "data-lake/bronze/industrials/v6/market/gd/fred_dgs10.csv",
        "data-lake/bronze/industrials/v6/market/gd/metadata.json",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/benchmark.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/forecast.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/industry.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/ir.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/market.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/research.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/sec.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/valuation.py",
        "scripts/industrials/fetch_gd_periodic_filings_v6.py",
        "scripts/industrials/fetch_gd_v6_market.py",
        "scripts/industrials/freeze_v6_gd.py",
        "scripts/industrials/valuation_v6_gd.py",
        "tests/test_industrials_v6_gd.py",
        "tests/test_industrials_v6_gd_freeze.py",
        *[
            path.relative_to(root).as_posix()
            for path in sorted((root / OUTPUT).glob("*"))
            if path.is_file()
        ],
    ]
    assertions = {
        "research_freeze_eligible": bool(
            gate["forecast_research_freeze_eligible"]
        ),
        "source_gate_pass": bool(gate["source_gate_pass"]),
        "ir_parser_gate_pass": bool(gate["ir_parser_gate_pass"]),
        "sec_ir_revenue_reconciliation_pass": bool(
            gate["sec_ir_revenue_reconciliation_pass"]
        ),
        "sec_ir_operating_income_reconciliation_complete": bool(
            gate["sec_ir_operating_income_reconciliation_complete"]
        ),
        "unidentified_operating_income_bridge_rows": int(
            gate["unidentified_operating_income_bridge_rows"]
        ),
        "historical_pit_industry_gate_pass": bool(
            gate["historical_pit_industry_gate_pass"]
        ),
        "fixed_oos_window_pass": bool(gate["fixed_oos_window_pass"]),
        "company_revenue_mase": float(gate["company_revenue_mase"]),
        "company_margin_mase": float(gate["company_margin_mase"]),
        "evidence_freeze_eligible": bool(gate["evidence_freeze_eligible"]),
        "forecast_research_freeze_eligible": bool(
            gate["forecast_research_freeze_eligible"]
        ),
        "conditional_dcf_run": bool(gate["conditional_dcf_run"]),
        "conditional_reverse_dcf_run": bool(gate["conditional_reverse_dcf_run"]),
        "terminal_gate_pass": bool(gate["terminal_gate_pass"]),
        "terminal_input_allowed": False,
        "fair_value_claim_allowed": bool(gate["fair_value_claim_allowed"]),
        "production_gate_pass": bool(gate["production_gate_pass"]),
        "production_promoted": False,
        "reverse_solver_fail_closed": bool(valuation["reverse_solver_fail_closed"]),
        "high_terminal_dependence": bool(valuation["high_terminal_dependence"]),
    }
    return freeze_research_benchmark(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_V6_GD_FOURTH_COMPANY_RESEARCH_BENCHMARK",
        version="6.0-research",
        relative_paths=files,
        assertions=assertions,
        parents={"hii_v54_margin_mechanism_manifest": parent["manifest_sha256"]},
    )


def verify_gd_v6_research(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
