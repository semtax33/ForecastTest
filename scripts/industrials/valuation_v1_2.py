from __future__ import annotations

from datetime import datetime, timezone
import json
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files
from equity_platform.industry_data.registry import build_registry_coverage, load_industry_sensor_registry
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.sectors.industrials import build_cat_backlog_history, build_cat_segment_history, load_cat_10k_sources
from equity_platform.sectors.industrials.v11_benchmark import verify_v11
from equity_platform.sectors.industrials.v12 import (
    build_cat_industry_forecast,
    build_cat_v12_research,
    build_cfsc_economics,
    build_expectations_surfaces,
    build_mpe_roic_audit,
    build_parser_quality_audit,
    load_cfsc_sources,
)
from equity_platform.valuation import DcfAssumptions


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v1_2.toml"
OUTPUT = ROOT / "output/industrials_valuation_v1_2_research"
ARCANA_PQCI = ROOT.parent / "Arcana/data-lake/bronze/pqci"


def markdown(frame: pd.DataFrame) -> str:
    """Small dependency-free renderer for the research report."""
    if frame.empty:
        return "_No rows._"
    values = frame.copy().fillna("").astype(str)
    header = "| " + " | ".join(values.columns) + " |"
    separator = "| " + " | ".join("---" for _ in values.columns) + " |"
    rows = [
        "| " + " | ".join(value.replace("|", "\\|") for value in row) + " |"
        for row in values.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    cutoff = pd.Timestamp(config["as_of_date"])
    parent_before = verify_v11(ROOT)
    registry = load_industry_sensor_registry(ROOT / "configs/industry_sensor_registry.csv")
    registry_coverage = build_registry_coverage(registry)
    cat_sources = load_cat_10k_sources(ROOT, ROOT / config["cat_source_catalog"], cutoff)
    cat_segments = build_cat_segment_history(cat_sources)
    cat_backlog = build_cat_backlog_history(cat_sources)
    cfsc_sources = load_cfsc_sources(ROOT, ROOT / config["cfsc_source_catalog"], cutoff)
    cfsc = build_cfsc_economics(cfsc_sources, cat_segments)
    industry = build_cat_industry_forecast(
        segment_history=cat_segments,
        sensor_map_path=ROOT / "configs/industrials_v1_2_cat_industry_sensor_map.csv",
        category_weights_path=ROOT / "configs/industrials_v1_2_cat_industry_weights.csv",
        census_snapshot_path=ARCANA_PQCI / "census/latest_manufacturing_orders_shipments_inventories.json",
        bls_snapshot_path=ARCANA_PQCI / "bls/latest_price_labor_activity.json",
        cutoff=cutoff,
    )
    roic = build_mpe_roic_audit(cat_segments)
    parser = build_parser_quality_audit(
        cat_sources=cat_sources,
        cat_segments=cat_segments,
        cat_backlog=cat_backlog,
        cfsc_sources=cfsc_sources,
        cfsc_history=cfsc["cfsc_standalone_economics_history"],
        tolerance_usd=float(config["parser_cross_filing_tolerance_usd"]),
    )
    parser_pass = bool(parser["parser_quality_summary"].iloc[0]["parser_quality_gate_pass"])
    frozen_bridge = pd.read_csv(ROOT / "output/industrials_valuation_v1_1_research/mpe_forecast_financial_bridge.csv")
    frozen_sotp = pd.read_csv(ROOT / "output/industrials_valuation_v1_1_research/sotp_valuation.csv")
    frozen_reverse = pd.read_csv(ROOT / "output/industrials_valuation_v1_1_research/sotp_reverse_dcf.csv")
    base = frozen_bridge.iloc[0]
    baseline = DcfAssumptions(
        base_revenue_usd=float(base["base_revenue_usd"]),
        near_term_growth_pct=float(base["near_term_growth_pct"]),
        operating_margin_pct=float(base["normalized_operating_margin_pct"]),
        tax_rate_pct=float(base["normalized_tax_rate_pct"]),
        roic_pct=float(base["normalized_roic_pct"]),
        wacc_pct=float(base["mpe_wacc_pct"]),
        terminal_growth_pct=float(config["terminal_growth_pct"]),
        horizon_years=int(config["forecast_horizon_years"]),
    )
    old_sotp = frozen_sotp.iloc[0]
    surfaces = build_expectations_surfaces(
        baseline=baseline,
        target_mpe_ev_usd=float(frozen_reverse.iloc[0]["market_target_mpe_enterprise_value_usd"]),
        debt_usd=float(base["mpe_debt_used_usd"]),
        cash_usd=float(base["mpe_cash_used_usd"]),
        fp_value_usd=float(old_sotp["financial_products_equity_value_usd"]),
        shares=float(old_sotp["shares_outstanding"]),
        margin_grid_pct=[float(v) for v in config["surface_margin_grid_pct"]],
        wacc_grid_pct=[float(v) for v in config["surface_wacc_grid_pct"]],
        growth_grid_pct=[float(v) for v in config["surface_growth_grid_pct"]],
        roic_grid_pct=[float(v) for v in config["surface_roic_grid_pct"]],
        match_tolerance_pct=float(config["market_match_tolerance_pct"]),
        iso_margin_bounds_pct=(float(config["iso_margin_lower_pct"]), float(config["iso_margin_upper_pct"])),
        iso_wacc_bounds_pct=(float(config["iso_wacc_lower_pct"]), float(config["iso_wacc_upper_pct"])),
        solver_tolerance_usd=float(config["solver_tolerance_usd"]),
    )
    research = build_cat_v12_research(
        industry_results=industry,
        frozen_mpe_bridge=frozen_bridge,
        frozen_sotp=frozen_sotp,
        terminal_growth_pct=float(config["terminal_growth_pct"]),
        horizon_years=int(config["forecast_horizon_years"]),
        parser_quality_gate_pass=parser_pass,
    )
    artifacts = {
        "industry_sensor_registry": registry,
        "industry_sensor_registry_coverage": registry_coverage,
        "cat_10k_sources": cat_sources.drop(columns="resolved_path"),
        "cfsc_10k_sources": cfsc_sources.drop(columns="resolved_path"),
        **industry,
        **roic,
        **cfsc,
        **parser,
        **surfaces,
        **research,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    parent_after = verify_v11(ROOT)
    gate = research["industrials_v1_2_gate"].iloc[0]
    valuation = research["v1_2_sotp_valuation"].iloc[0]
    source_hashes = hash_files(
        ROOT,
        [
            "configs/industrials_v1_2.toml",
            "configs/industry_sensor_registry.csv",
            "configs/industrials_v1_2_cat_industry_sensor_map.csv",
            "configs/industrials_v1_2_cat_industry_weights.csv",
            "configs/industrials_v1_2_cfsc_10k_sources.csv",
            "equity_platform/industry_data/registry.py",
            "equity_platform/industry_data/pqci.py",
            "equity_platform/sectors/industrials/v12/industry_forecast.py",
            "equity_platform/sectors/industrials/v12/surfaces.py",
            "equity_platform/sectors/industrials/v12/roic_audit.py",
            "equity_platform/sectors/industrials/v12/finance_economics.py",
            "equity_platform/sectors/industrials/v12/parser_audit.py",
            "equity_platform/sectors/industrials/v12/research.py",
            "scripts/industrials/valuation_v1_2.py",
        ],
    )
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "ticker": "CAT",
        "parent_manifest_verified_before": parent_before["verified_files"] > 0,
        "parent_manifest_verified_after": parent_after["verified_files"] > 0,
        "research_complete": bool(gate["research_complete"]),
        "historical_industry_pit_vintages_available": False,
        "terminal_input_allowed": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "v1_2_sotp_value_per_share": float(valuation["sotp_value_per_share"]),
        "market_price": float(valuation["market_price"]),
        "valuation_interpretation": valuation["valuation_status"],
        "source_hashes": source_hashes,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = f"""# Industrials Valuation V1.2 — CAT expectations and economics audit

## Research gate

{markdown(research['industrials_v1_2_gate'])}

## Industry P/Q/C/I bridge

{markdown(industry['industry_financial_bridge'])}

Public Census M3 and BLS observations are available at the research cutoff, but
the current Arcana snapshots do not preserve historical release dates/vintages.
They may drive this current research nowcast, not a historical PIT backtest or
production model.

## Research DCF

{markdown(research['v1_2_sotp_valuation'])}

The industry bridge controls year one. Later years fade to V1.1 frozen normalized
margin and ROIC, so V1.2 does not silently replace terminal economics.

## Expectations surfaces

{markdown(surfaces['expectations_surface_summary'])}

{markdown(surfaces['expectations_iso_value_curve'])}

## MP&E ROIC perimeter

{markdown(roic['mpe_roic_measure_summary'])}

Historical, annual incremental, through-cycle, and terminal ROIC are kept as
different concepts. The audit does not identify a terminal ROIC.

## Financial Products exact economics

{markdown(cfsc['financial_products_perimeter_audit'])}

CFSC standalone economics are exact to its SEC statements. CAT's broader
Financial Products segment includes an explicit residual perimeter and is not
misrepresented as identical to CFSC.

## Parser quality

{markdown(parser['parser_quality_summary'])}

Backlog logic remains unchanged with only 2/3 OOS validations. V1.1 remains
manifest-verified, terminal promotion is prohibited, and production stays 0/20.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(research["industrials_v1_2_gate"].to_string(index=False))
    print(industry["industry_financial_bridge"].to_string(index=False))
    print(research["v1_2_sotp_valuation"].to_string(index=False))
    print(parser["parser_quality_summary"].to_string(index=False))
    return 0 if bool(gate["research_complete"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
