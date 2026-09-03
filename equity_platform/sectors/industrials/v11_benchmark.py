from __future__ import annotations

from pathlib import Path

import pandas as pd

from equity_platform.artifacts import freeze_manifest, verify_manifest


MANIFEST = Path("benchmarks/industrials_v1_1/manifest.json")
OUTPUT = Path("output/industrials_valuation_v1_1_research")


def _frozen_paths(root: Path) -> list[str]:
    source_paths = [
        "configs/industrials_v1_1.toml",
        "configs/industrials_v1_1_cat_10k_sources.csv",
        "equity_platform/metrics.py",
        "equity_platform/sec.py",
        "equity_platform/valuation.py",
        "equity_platform/sectors/industrials/backlog.py",
        "equity_platform/sectors/industrials/financials.py",
        "equity_platform/sectors/industrials/market.py",
        "equity_platform/sectors/industrials/segments.py",
        "equity_platform/sectors/industrials/sources.py",
        "equity_platform/sectors/industrials/sotp.py",
        "equity_platform/sectors/industrials/v11_benchmark.py",
        "scripts/industrials/valuation_v1_1.py",
        "scripts/industrials/freeze_v1_1.py",
        "tests/test_industrials_valuation_v1_1.py",
    ]
    output_paths = [
        path.relative_to(root).as_posix()
        for path in sorted((root / OUTPUT).iterdir())
        if path.is_file()
    ]
    return source_paths + output_paths


def freeze_v11(root: Path) -> dict[str, object]:
    gate = pd.read_csv(root / OUTPUT / "industrials_v1_1_gate.csv").iloc[0]
    sotp = pd.read_csv(root / OUTPUT / "sotp_valuation.csv").iloc[0]
    anchor = pd.read_csv(root / OUTPUT / "backlog_anchor_gate.csv").iloc[0]
    if not bool(gate["research_audit_complete"]):
        raise ValueError("Industrials V1.1 research audit is not complete")
    if bool(gate["production_promoted"]) or bool(gate["terminal_input_allowed"]):
        raise ValueError("Industrials V1.1 cannot freeze with production/terminal authority")
    return freeze_manifest(
        root=root,
        manifest_path=MANIFEST,
        name="INDUSTRIALS_V1_1_CAT_SEMANTIC_SOTP_AUDIT",
        version="1.1",
        relative_paths=_frozen_paths(root),
        assertions={
            "direct_firm_backlog_years": int(gate["direct_firm_backlog_years"]),
            "rpo_anchor_retired": bool(gate["rpo_anchor_retired"]),
            "backlog_anchor_promoted": bool(anchor["anchor_promoted"]),
            "backlog_oos_validation_observations": int(
                anchor["walk_forward_validation_observations"]
            ),
            "segment_reconciliation_pass": bool(gate["segment_reconciliation_pass"]),
            "financial_products_separately_valued": bool(
                gate["financial_products_separately_valued"]
            ),
            "financial_products_funding_debt_double_counted": bool(
                sotp["financial_products_funding_debt_double_counted"]
            ),
            "sotp_component_identity_pass": bool(gate["sotp_component_identity_pass"]),
            "sotp_value_per_share": float(sotp["sotp_value_per_share"]),
            "valuation_interpretation": str(sotp["valuation_status"]),
            "terminal_input_allowed": False,
            "production_promoted": False,
            "live_matched_observations": "0/20",
        },
    )


def verify_v11(root: Path) -> dict[str, object]:
    return verify_manifest(root=root, manifest_path=MANIFEST)
