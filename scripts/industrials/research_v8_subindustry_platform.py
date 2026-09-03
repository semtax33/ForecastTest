from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from time import perf_counter

import pandas as pd

from equity_platform.artifacts import hash_files, sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.platform import (
    INDUSTRIALS_SUBINDUSTRIES,
    build_arcana_ir_evidence,
    build_company_forecast_origins,
    build_company_forecast_panel,
    build_company_pit_industry_features,
    build_conditional_valuation_research,
    build_industrials_bls_sensor_map,
    build_market_wacc_evidence,
    build_arcana_pqci_context,
    build_ifrs_evidence,
    build_subindustry_companyfacts_evidence,
    run_fixed_oos_company_forecasts,
)
from equity_platform.sectors.industrials.platform.registry import registry_frame
from equity_platform.sectors.industrials.v15.pit import parse_bls_ppi_vintages


ROOT = PROJECT_ROOT
AS_OF = pd.Timestamp("2026-09-04")
BRONZE = ROOT / "data-lake/bronze/industrials/v8/subindustries"
SILVER = ROOT / "data-lake/silver/industrials/v8/subindustries"
GOLD = ROOT / "data-lake/gold/industrials/v8/subindustries"
OUTPUT = ROOT / "output/industrials_v8_subindustry_platform_research"
ARCANA_IR = Path(
    "D:/Programming/python_example/Arcana/data-lake/bronze/sec/fillings/ir"
)


def _stage(name: str, started: float) -> float:
    now = perf_counter()
    print(f"stage={name} elapsed_seconds={now - started:.2f}", flush=True)
    return now


def _read_stage_cache(root: Path, names: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    missing = [name for name in names if not (root / f"{name}.csv").exists()]
    if missing:
        raise FileNotFoundError(f"Verified stage cache is incomplete: {missing}")
    return {name: pd.read_csv(root / f"{name}.csv") for name in names}


def _coverage_matrix(
    *,
    sec_summary: pd.DataFrame,
    ir_inventory: pd.DataFrame,
    sensors: pd.DataFrame,
    annual: pd.DataFrame,
    performance: pd.DataFrame,
    forecast_routes: pd.DataFrame,
    pqci_context_routes: pd.DataFrame,
    ifrs_inventory: pd.DataFrame,
    valuation_gates: pd.DataFrame,
) -> pd.DataFrame:
    profiles = registry_frame().rename(
        columns={"representative_ticker": "ticker"}
    )
    source = profiles.merge(sec_summary, on=["subindustry_code", "ticker"], how="left")
    source = source.merge(ir_inventory, on=["subindustry_code", "ticker"], how="left")
    source = source.merge(
        ifrs_inventory[
            [
                "subindustry_code",
                "ticker",
                "status",
                "annual_rows",
                "operating_margin_rows",
                "roic_rows",
                "core_reinvestment_rows",
                "quantity_anchor_rows",
                "parser_rule_count",
            ]
        ].rename(
            columns={
                "status": "ifrs_status",
                "annual_rows": "ifrs_annual_rows",
                "operating_margin_rows": "ifrs_operating_margin_rows",
                "roic_rows": "ifrs_roic_rows",
                "core_reinvestment_rows": "ifrs_core_reinvestment_rows",
            }
        ),
        on=["subindustry_code", "ticker"],
        how="left",
    )
    bls = sensors.groupby("segment", as_index=False).agg(
        bls_series=("series_id", "nunique"),
        dedicated_output_route=(
            "route_note",
            lambda values: bool(values.str.contains("DEDICATED_INDUSTRY_OUTPUT").any()),
        ),
        structural_cost_series=("structural_cost_claim_allowed", "sum"),
    ).rename(columns={"segment": "subindustry_code"})
    source = source.merge(bls, on="subindustry_code", how="left")
    reinvestment = annual.groupby("ticker", as_index=False).agg(
        roic_observations=("reported_roic_pct", lambda values: values.notna().sum()),
        core_reinvestment_observations=(
            "core_reinvestment_claim_allowed",
            "sum",
        ),
        innovation_reinvestment_observations=(
            "innovation_adjusted_reinvestment_claim_allowed",
            "sum",
        ),
    )
    source = source.merge(reinvestment, on="ticker", how="left")
    source = source.merge(
        performance[
            [
                "ticker",
                "oos_observations",
                "revenue_mase",
                "profit_margin_mase",
                "forecast_authority",
            ]
        ],
        on="ticker",
        how="left",
    )
    source = source.merge(
        forecast_routes[
            [
                "ticker",
                "route",
                "rpo_quantity_route_ready",
                "structural_cost_route_ready",
            ]
        ],
        on="ticker",
        how="left",
    )
    source = source.merge(
        pqci_context_routes,
        on=["subindustry_code", "ticker"],
        how="left",
        validate="one_to_one",
    )
    source = source.merge(
        valuation_gates[
            ["ticker", "conditional_dcf_run", "failed_gates"]
        ],
        on="ticker",
        how="left",
    )
    source["sec_status"] = source["company_forecast_history_ready"].map(
        {True: "SEC_FORECAST_HISTORY_READY", False: "SEC_HISTORY_INSUFFICIENT"}
    )
    foreign_ready = source["ifrs_status"].eq("READY")
    source.loc[
        source["sec_status"].isna()
        & foreign_ready
        & source["quantity_anchor_rows"].fillna(0).gt(0),
        "sec_status",
    ] = "IFRS_ANNUAL_AND_COMPANY_Q_ANCHOR_READY"
    source.loc[
        source["sec_status"].isna() & foreign_ready,
        "sec_status",
    ] = "IFRS_ANNUAL_SHORT_HISTORY"
    source["sec_status"] = source["sec_status"].fillna("SOURCE_ADAPTER_NOT_READY")
    for destination, foreign_column in (
        ("roic_observations", "ifrs_roic_rows"),
        ("core_reinvestment_observations", "ifrs_core_reinvestment_rows"),
    ):
        source[destination] = source[destination].fillna(source[foreign_column]).fillna(0)
    source["quantity_status"] = source.apply(
        lambda row: (
            "SEC_RPO_ROUTE_TESTED"
            if pd.notna(row.get("rpo_quantity_route_ready"))
            and bool(row.get("rpo_quantity_route_ready"))
            else (
                "COMPANY_DISCLOSED_MONTHLY_QUANTITY_DSL_READY"
                if row.get("quantity_anchor_rows", 0) > 0
                else (
                "IR_KPI_DISCOVERY_READY_NUMERIC_PARSER_REQUIRED"
                if row.get("ir_documents_in_window", 0) > 0
                else "NOT_IDENTIFIED"
                )
            )
        ),
        axis=1,
    )
    source["terminal_evidence_eligible"] = False
    source["production_promotable"] = False
    return source


def main() -> int:
    stage_started = perf_counter()
    use_stage_cache = os.environ.get("V8_USE_VERIFIED_STAGE_CACHE") == "1"
    sensors = build_industrials_bls_sensor_map()
    stage_started = _stage("sensor_registry", stage_started)
    sensor_path = ROOT / "data-lake/silver/industrials/v8/reference/industrials_bls_sensor_map.csv"
    sensor_path.parent.mkdir(parents=True, exist_ok=True)
    sensors.to_csv(sensor_path, index=False)
    if use_stage_cache:
        bls = _read_stage_cache(
            SILVER,
            (
                "bls_ppi_archive_sources",
                "bls_ppi_vintage_audit",
                "bls_ppi_vintage_canonical",
                "bls_ppi_vintage_coverage",
                "bls_release_schedule_sources",
            ),
        )
    else:
        bls = parse_bls_ppi_vintages(
            project_root=ROOT,
            archive_manifest_path=ROOT
            / "data-lake/bronze/industrials/v1_5/bls/archive_manifest.json",
            sensor_map_path=sensor_path,
            cutoff=AS_OF,
        )
    stage_started = _stage("bls_pit_vintages", stage_started)
    if use_stage_cache:
        sec = _read_stage_cache(
            SILVER,
            (
                "subindustry_sec_source_inventory",
                "subindustry_companyfacts_summary",
                "subindustry_companyfacts_metric_coverage",
                "subindustry_companyfacts_metric_selections",
                "subindustry_periodic_financial_history",
                "subindustry_quarterly_financial_history",
                "subindustry_annual_roic_reinvestment_history",
            ),
        )
    else:
        sec = build_subindustry_companyfacts_evidence(
            project_root=ROOT,
            catalog_manifest_path=BRONZE / "sec/catalog_manifest.json",
            cutoff=AS_OF,
        )
    stage_started = _stage("sec_companyfacts", stage_started)
    if use_stage_cache:
        ir = _read_stage_cache(
            SILVER,
            ("subindustry_ir_document_evidence", "subindustry_ir_coverage_inventory"),
        )
    else:
        ir = build_arcana_ir_evidence(
            ir_root=ARCANA_IR,
            start_date=pd.Timestamp("2021-01-01"),
            cutoff=AS_OF,
            verified_cache_path=SILVER / "subindustry_ir_document_evidence.csv",
        )
    stage_started = _stage("arcana_ir_audit", stage_started)
    pqci_context = build_arcana_pqci_context(
        pqci_root=Path(
            "D:/Programming/python_example/Arcana/data-lake/bronze/pqci"
        ),
        cutoff=AS_OF,
    )
    stage_started = _stage("arcana_pqci_context", stage_started)
    ifrs = build_ifrs_evidence(
        project_root=ROOT,
        catalog_manifest_path=BRONZE / "ifrs/catalog_manifest.json",
    )
    stage_started = _stage("ifrs_dsl", stage_started)
    origins = build_company_forecast_origins(
        sec["subindustry_quarterly_financial_history"]
    )
    stage_started = _stage("forecast_origins", stage_started)
    industry = build_company_pit_industry_features(
        vintages=bls["bls_ppi_vintage_canonical"],
        sensor_map=sensors,
        origins=origins,
    )
    stage_started = _stage("pit_industry_features", stage_started)
    panel = build_company_forecast_panel(
        quarterly=sec["subindustry_quarterly_financial_history"],
        origins=origins,
        industry_features=industry["subindustry_pit_industry_features"],
    )
    stage_started = _stage("forecast_panel", stage_started)
    forecast = run_fixed_oos_company_forecasts(panel)
    stage_started = _stage("fixed_oos_forecasts", stage_started)
    market_root = BRONZE / "market"
    market = build_market_wacc_evidence(
        annual=sec["subindustry_annual_roic_reinvestment_history"],
        periodic=sec["subindustry_periodic_financial_history"],
        daily_path=market_root / "adjusted_close_daily.csv",
        weekly_path=market_root / "adjusted_close_weekly.csv",
        risk_free_path=market_root / "fred_dgs10.csv",
        valuation_date=AS_OF,
    )
    stage_started = _stage("market_wacc", stage_started)
    valuation = build_conditional_valuation_research(
        annual=sec["subindustry_annual_roic_reinvestment_history"],
        quarterly=sec["subindustry_quarterly_financial_history"],
        forecast_performance=forecast["subindustry_forecast_performance"],
        fixed_oos_forecasts=forecast["subindustry_fixed_oos_forecasts"],
        market_ev=market["subindustry_market_ev_bridge"],
        wacc=market["subindustry_independent_wacc_range"],
    )
    stage_started = _stage("conditional_valuation", stage_started)
    coverage = _coverage_matrix(
        sec_summary=sec["subindustry_companyfacts_summary"],
        ir_inventory=ir["subindustry_ir_coverage_inventory"],
        sensors=sensors,
        annual=sec["subindustry_annual_roic_reinvestment_history"],
        performance=forecast["subindustry_forecast_performance"],
        forecast_routes=forecast["subindustry_forecast_routes"],
        pqci_context_routes=pqci_context["subindustry_pqci_context_routes"],
        ifrs_inventory=ifrs["ifrs_source_inventory"],
        valuation_gates=valuation["subindustry_valuation_gates"],
    )
    performance = forecast["subindustry_forecast_performance"]
    valuation_summary = valuation["subindustry_conditional_dcf_summary"]
    gate = pd.DataFrame(
        [
            {
                "version": "INDUSTRIALS_SUBINDUSTRY_PLATFORM_V8_RESEARCH",
                "verified_stage_cache_used": use_stage_cache,
                "registered_subindustries": len(INDUSTRIALS_SUBINDUSTRIES),
                "domestic_sec_companies_ready": int(
                    sec["subindustry_sec_source_inventory"]["hashes_verified"].sum()
                ),
                "sec_10k_10q_filings": int(
                    sec["subindustry_sec_source_inventory"]["filings"].sum()
                ),
                "ifrs_companies_ready": int(
                    ifrs["ifrs_source_inventory"]["hashes_verified"].sum()
                ),
                "ifrs_20f_6k_filings": int(
                    ifrs["ifrs_source_inventory"]["filing_count"].sum()
                ),
                "ifrs_annual_rows": len(ifrs["ifrs_annual_financial_history"]),
                "company_disclosed_monthly_quantity_rows": len(
                    ifrs["pac_monthly_passenger_traffic"]
                ),
                "compiled_parser_rules": len(ifrs["parser_rule_inventory"]),
                "parser_emitted_facts": len(ifrs["parser_fact_ir"]),
                "parser_failures": int(
                    ifrs["parser_rule_execution_audit"]["status"]
                    .astype(str)
                    .str.startswith("FAIL")
                    .sum()
                ),
                "arcana_ir_companies_ready": int(
                    ir["subindustry_ir_coverage_inventory"][
                        "ir_documents_in_window"
                    ].gt(0).sum()
                ),
                "arcana_ir_documents_audited": len(
                    ir["subindustry_ir_document_evidence"]
                ),
                "ir_hash_mismatches": int(
                    ir["subindustry_ir_coverage_inventory"]["hash_mismatches"].sum()
                ),
                "bls_pit_series": int(
                    bls["bls_ppi_vintage_audit"].iloc[0]["parsed_series"]
                ),
                "bls_pit_vintage_rows": len(bls["bls_ppi_vintage_canonical"]),
                "bls_pit_gate_pass": bool(
                    bls["bls_ppi_vintage_audit"].iloc[0]["historical_pit_ready"]
                ),
                "arcana_pqci_current_context_datasets": int(
                    pqci_context["arcana_pqci_context_audit"].iloc[0][
                        "datasets_ready"
                    ]
                ),
                "arcana_pqci_current_context_rows": int(
                    pqci_context["arcana_pqci_context_audit"].iloc[0][
                        "canonical_rows"
                    ]
                ),
                "subindustries_with_current_context_pqci": int(
                    pqci_context["arcana_pqci_context_audit"].iloc[0][
                        "subindustries_with_full_context_pqci"
                    ]
                ),
                "current_revised_context_used_in_oos": False,
                "fixed_oos_companies_with_4plus": int(
                    performance["oos_observations"].ge(4).sum()
                ),
                "strong_forecast_authority": int(
                    performance["forecast_authority"].eq("STRONG").sum()
                ),
                "mixed_forecast_authority": int(
                    performance["forecast_authority"].eq("MIXED").sum()
                ),
                "diagnostic_only_or_not_tested": int(
                    performance["forecast_authority"]
                    .isin(["DIAGNOSTIC_ONLY", "NOT_TESTED"])
                    .sum()
                ),
                "core_reinvestment_observations": int(
                    sec["subindustry_annual_roic_reinvestment_history"][
                        "core_reinvestment_claim_allowed"
                    ].sum()
                ),
                "conditional_dcf_companies": int(
                    valuation["subindustry_valuation_gates"][
                        "conditional_dcf_run"
                    ].sum()
                ),
                "dcf_identity_max_error": float(
                    valuation_summary[
                        "growth_reinvestment_roic_identity_max_error_pct_points"
                    ].max()
                )
                if not valuation_summary.empty
                else pd.NA,
                "ev_equity_identity_max_error_usd": float(
                    valuation_summary["ev_to_common_equity_identity_error_usd"].max()
                )
                if not valuation_summary.empty
                else pd.NA,
                "terminal_evidence_eligible": False,
                "fair_value_claim_allowed": False,
                "production_promotable": False,
                "live_matched_observations": "0/20",
                "pdf_parsing_used": False,
                "status": "HOLD_RESEARCH_UNFROZEN_COVERAGE_AND_ADAPTERS_PENDING",
            }
        ]
    )
    silver_artifacts = {
        "industrials_subindustry_registry": registry_frame(),
        "industrials_bls_sensor_map": sensors,
        **bls,
        **sec,
        "subindustry_forecast_origins": origins,
        **industry,
        "subindustry_forecast_panel": panel,
        **ir,
        **pqci_context,
        **ifrs,
    }
    gold_artifacts = {
        **forecast,
        **market,
        **valuation,
        "subindustry_coverage_matrix": coverage,
        "industrials_v8_gate": gate,
    }
    write_csv_artifacts(SILVER, silver_artifacts)
    stage_started = _stage("write_silver", stage_started)
    write_csv_artifacts(GOLD, gold_artifacts)
    stage_started = _stage("write_gold", stage_started)
    write_csv_artifacts(OUTPUT, gold_artifacts)
    stage_started = _stage("write_output", stage_started)
    source_paths = [
        "equity_platform/sectors/industrials/platform/domain.py",
        "equity_platform/sectors/industrials/platform/registry.py",
        "equity_platform/sectors/industrials/platform/bls.py",
        "equity_platform/sectors/industrials/platform/companyfacts.py",
        "equity_platform/sectors/industrials/platform/forecast.py",
        "equity_platform/sectors/industrials/platform/ir.py",
        "equity_platform/sectors/industrials/platform/pqci_context.py",
        "equity_platform/sectors/industrials/platform/ifrs.py",
        "equity_platform/sectors/industrials/platform/ifrs_rules.py",
        "equity_platform/ir/authority.py",
        "equity_platform/ir/fact.py",
        "equity_platform/ir/economic.py",
        "equity_platform/ir/evidence.py",
        "equity_platform/ir/causal.py",
        "equity_platform/documents/model.py",
        "equity_platform/documents/html.py",
        "equity_platform/parsing/rule_ir.py",
        "equity_platform/parsing/dsl/compiler.py",
        "equity_platform/parsing/executor.py",
        "configs/parser_rules/industrials/pac.arc",
        "equity_platform/sectors/industrials/platform/valuation.py",
        "equity_platform/sectors/industrials/platform/validation.py",
        "scripts/industrials/fetch_v8_subindustry_sec.py",
        "scripts/industrials/fetch_v8_subindustry_market.py",
        "scripts/industrials/research_v8_subindustry_platform.py",
    ]
    metadata = {
        "version": "INDUSTRIALS_SUBINDUSTRY_PLATFORM_V8_RESEARCH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": AS_OF.date().isoformat(),
        "source_hashes": hash_files(ROOT, source_paths),
        "sec_catalog_sha256": sha256_file(BRONZE / "sec/catalog_manifest.json"),
        "ifrs_catalog_sha256": sha256_file(BRONZE / "ifrs/catalog_manifest.json"),
        "uses_10k": True,
        "uses_10q": True,
        "uses_tagged_notes": True,
        "uses_arcana_ir_html": True,
        "uses_historical_pit_industry_data": True,
        "uses_current_revised_industry_context": True,
        "uses_current_revised_industry_data_in_oos": False,
        "uses_typed_parser_rule_ir": True,
        "uses_non_turing_complete_parser_dsl": True,
        "verified_stage_cache_used": use_stage_cache,
        "pdf_parsing_used": False,
        "terminal_input_allowed": False,
        "fair_value_claim_allowed": False,
        "production_promoted": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    display_performance = performance[
        [
            "ticker",
            "subindustry_code",
            "oos_observations",
            "revenue_mase",
            "profit_margin_mase",
            "forecast_authority",
        ]
    ]
    report = f"""# Industrials Subindustry Platform V8 — broad coverage research

## Decision

{markdown_table(gate)}

This is a broad portability and coverage layer, not a production valuation model.
All conditional DCF outputs remain expectations diagnostics. Terminal, fair-value and
production authority are locked.

## Architecture

The migration now separates canonical `FactIR / EconomicGraphIR / EvidenceGraphIR /
CausalGraphIR`, semantic documents, typed parser-rule IR, deterministic rule execution,
and research policy. Existing engines remain behind compatibility adapters while
golden results are preserved. Frozen CAT/CMI/LMT/NOC/HII/GD packages are not modified.

## Coverage

{markdown_table(coverage[["ticker", "subindustry_code", "sec_status", "ir_documents_in_window", "bls_series", "oos_observations", "forecast_authority", "core_reinvestment_observations", "conditional_dcf_run"]])}

## Fixed OOS results

{markdown_table(display_performance)}

Revenue and margin authority are measured separately before the combined authority
label is assigned. `PROFIT_PROXY_PRETAX` is never relabeled as operating margin.
Prediction intervals are reported separately from point-forecast authority.

## Conditional DCF and Reverse DCF

{markdown_table(valuation_summary)}

{markdown_table(valuation['subindustry_reverse_dcf_diagnostics'])}

Unbracketed reverse solutions remain non-identifiable. High terminal-value shares are
flagged; no conditional value is promoted to fair value.

## Remaining work

Arcana's BEA/BLS/Census/EIA/USDA snapshots provide current-revised P/Q/C/I context
for all 26 subindustries, but cannot enter historical OOS claims without vintages.
PAC now has hashed 20-F annual facts plus a DSL-parsed monthly passenger Q anchor;
its quarterly financial bridge remains unavailable. FER has only two 20-F years and
therefore fails closed. Other IR numerical KPI rules still require staged DSL migration.
GEV lacks enough post-spin history. Live settlement remains 0/20.
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(gate.to_string(index=False))
    print(display_performance.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
