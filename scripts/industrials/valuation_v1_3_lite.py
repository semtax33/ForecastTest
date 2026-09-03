from __future__ import annotations

from datetime import datetime, timezone
import json
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.sectors.industrials import build_cat_segment_history, load_cat_10k_sources
from equity_platform.sectors.industrials.v12.benchmark import verify_v12_architecture
from equity_platform.sectors.industrials.v12.finance_economics import build_cfsc_economics, load_cfsc_sources
from equity_platform.sectors.industrials.v13lite import build_capture_research, build_ir_segment_history, build_segment_capex_history, build_v13_lite_research


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v1_3_lite.toml"
OUTPUT = ROOT / "output/industrials_valuation_v1_3_lite_research"
ARCANA = ROOT.parent / "Arcana"


def markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    values = frame.copy().fillna("").astype(str)
    header = "| " + " | ".join(values.columns) + " |"
    separator = "| " + " | ".join("---" for _ in values.columns) + " |"
    rows = ["| " + " | ".join(value.replace("|", "\\|") for value in row) + " |" for row in values.itertuples(index=False, name=None)]
    return "\n".join([header, separator, *rows])


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    cutoff = pd.Timestamp(config["as_of_date"])
    parent_before = verify_v12_architecture(ROOT)
    cat_sources = load_cat_10k_sources(ROOT, ROOT / config["cat_10k_source_catalog"], cutoff)
    annual_history = build_cat_segment_history(cat_sources)
    capex = build_segment_capex_history(cat_sources)
    cfsc_sources = load_cfsc_sources(ROOT, ROOT / "configs/industrials_v1_2_cfsc_10k_sources.csv", cutoff)
    cfsc = build_cfsc_economics(cfsc_sources, annual_history)
    ir = build_ir_segment_history(ARCANA / config["arcana_ir_relative_path"], cutoff)
    capture = build_capture_research(
        ir_history=ir["ir_segment_quarterly_history"],
        census_snapshot_path=ARCANA / "data-lake/bronze/pqci/census/latest_manufacturing_orders_shipments_inventories.json",
        bls_snapshot_path=ARCANA / "data-lake/bronze/pqci/bls/latest_price_labor_activity.json",
        cutoff=cutoff,
        minimum_training_quarters=int(config["minimum_training_quarters"]),
        minimum_validation_quarters=int(config["minimum_validation_quarters"]),
        prior_strength=float(config["capture_prior_strength"]),
        cost_driver_industry_weight=float(config["cost_driver_industry_weight"]),
        cost_driver_inflation_weight=float(config["cost_driver_inflation_weight"]),
        interval_z=float(config["prediction_interval_z"]),
    )
    frozen_bridge = pd.read_csv(ROOT / "output/industrials_valuation_v1_1_research/mpe_forecast_financial_bridge.csv")
    frozen_sotp = pd.read_csv(ROOT / "output/industrials_valuation_v1_1_research/sotp_valuation.csv")
    frozen_reverse = pd.read_csv(ROOT / "output/industrials_valuation_v1_1_research/sotp_reverse_dcf.csv")
    v12_sotp = pd.read_csv(ROOT / "output/industrials_valuation_v1_2_research/v1_2_sotp_valuation.csv")
    latest_cat_path = ROOT / str(cat_sources.iloc[-1]["local_path"])
    research = build_v13_lite_research(
        capture_results=capture,
        annual_history=annual_history,
        cfsc_history=cfsc["cfsc_standalone_economics_history"],
        latest_cat_path=latest_cat_path,
        frozen_bridge=frozen_bridge,
        frozen_sotp=frozen_sotp,
        frozen_reverse=frozen_reverse,
        v12_sotp=v12_sotp,
        segment_capex_history=capex["segment_capex_history"],
        terminal_growth_pct=float(config["terminal_growth_pct"]),
        cap_years=[int(value) for value in config["cap_duration_years"]],
        cap_margins=[float(value) for value in config["cap_margin_grid_pct"]],
        cap_roics=[float(value) for value in config["cap_roic_grid_pct"]],
        market_match_tolerance_pct=float(config["market_match_tolerance_pct"]),
        minimum_validation_observations=int(config["minimum_validation_quarters"]),
        ir_parser_gate_pass=bool(ir["ir_parser_summary"].iloc[0]["parser_gate_pass"]),
    )
    artifacts = {**ir, **capex, **capture, **research}
    write_csv_artifacts(OUTPUT, artifacts)
    parent_after = verify_v12_architecture(ROOT)
    gate = research["industrials_v1_3_lite_gate"].iloc[0]
    valuation = research["v1_3_lite_sotp_valuation"].iloc[0]
    bridge = research["capture_calibrated_financial_bridge"].iloc[0]
    source_hashes = hash_files(
        ROOT,
        [
            "configs/industrials_v1_3_lite.toml",
            "equity_platform/sectors/industrials/v13lite/__init__.py",
            "equity_platform/sectors/industrials/v13lite/annual_capex.py",
            "equity_platform/sectors/industrials/v13lite/ir_segments.py",
            "equity_platform/sectors/industrials/v13lite/capture.py",
            "equity_platform/sectors/industrials/v13lite/research.py",
            "scripts/industrials/valuation_v1_3_lite.py",
        ],
    )
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "ticker": "CAT",
        "parent_v1_2_manifest_sha256": parent_before["manifest_sha256"],
        "parent_verified_after": parent_after["manifest_sha256"] == parent_before["manifest_sha256"],
        "benchmark_scope": "CALIBRATION_ARCHITECTURE_NOT_FORECAST_PERFORMANCE",
        "pdf_parsing_deferred": True,
        "historical_industry_pit_vintages_available": False,
        "forecast_performance_claim_allowed": False,
        "terminal_input_allowed": False,
        "production_promoted": False,
        "live_matched_observations": "0/20",
        "forecast_revenue_growth_pct": float(bridge["forecast_revenue_growth_pct"]),
        "forecast_operating_margin_pct": float(bridge["forecast_operating_margin_pct"]),
        "incremental_roic_pct": float(bridge["incremental_roic_pct"]),
        "v1_3_lite_value_per_share": float(valuation["sotp_value_per_share"]),
        "source_hashes": source_hashes,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = f"""# Industrials V1.3-lite — CAT segment capture calibration

## Gate

{markdown(research['industrials_v1_3_lite_gate'])}

PDF parsing was explicitly deferred. CAT SEC-filed IR HTML supplies quarterly
segment actuals. Census/BLS history remains latest-revised rather than historical
PIT vintage, so all temporal results are calibration diagnostics only.

## IR parser

{markdown(ir['ir_parser_summary'])}

## Segment capture

{markdown(capture['capture_calibration_summary'])}

Revenue and cost capture are estimated separately and shrunk toward the pooled
CAT segment relationship. Unit capture of 1.0 is no longer assumed.

## Margin validation

{markdown(capture['margin_validation_summary'])}

## FY2026 financial bridge

{markdown(research['capture_calibrated_financial_bridge'])}

## Valuation diagnostic

{markdown(research['v1_3_lite_sotp_valuation'])}

## Reinvestment

{markdown(research['reinvestment_validation_summary'])}

{markdown(capex['segment_capex_summary'])}

{markdown(research['reinvestment_capex_context'])}

## Financial Products residual

{markdown(research['financial_products_residual_bridge_audit'])}

## Competitive-advantage-period surface

{markdown(research['cap_surface_summary'])}

Backlog remains unchanged at 2/3 OOS. Terminal replacement and production stay
locked at 0/20.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(research["industrials_v1_3_lite_gate"].to_string(index=False))
    print(ir["ir_parser_summary"].to_string(index=False))
    print(capture["capture_calibration_summary"].to_string(index=False))
    print(research["capture_calibrated_financial_bridge"].to_string(index=False))
    print(research["v1_3_lite_sotp_valuation"].to_string(index=False))
    print(research["cap_surface_summary"].to_string(index=False))
    return 0 if bool(gate["research_complete"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
