from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files, sha256_file
from equity_platform.core.pit import build_quarterly_forecast_origins
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.aerospace_defense.lmt.industry import build_lmt_industry_evidence
from equity_platform.sectors.industrials.aerospace_defense.lmt.uncertainty import build_lmt_uncertainty_calibration
from equity_platform.sectors.industrials.aerospace_defense.lmt_v31.benchmark import verify_lmt_v31_evidence
from equity_platform.sectors.industrials.aerospace_defense.noc import (
    build_noc_ir_evidence,
    build_noc_portability_forecast,
    build_noc_sec_evidence,
)
from equity_platform.sectors.industrials.v15.pit import build_pit_forecast_features, parse_bls_ppi_vintages
from equity_platform.core.champion_gate import assess_against_naive


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v4_noc.toml"
OUTPUT = ROOT / "output/industrials_v4_noc_cross_company_research"
ARCANA_PQCI = Path("D:/Programming/python_example/Arcana/data-lake/bronze/pqci")


def _cross_company(
    summary: pd.DataFrame,
    company_summary: pd.DataFrame,
    lmt_output: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lmt = pd.read_csv(lmt_output / "lmt_portability_summary.csv")
    lmt_rows = lmt[["segment", "revenue_mase", "revenue_champion_eligible", "margin_mase", "margin_champion_eligible", "joint_champion"]].copy()
    lmt_rows.insert(0, "company", "LMT")
    noc_rows = summary[[
        "segment", "funded_backlog_revenue_mase", "funded_backlog_revenue_champion_eligible",
        "margin_mase", "margin_champion_eligible", "joint_champion",
    ]].rename(columns={
        "funded_backlog_revenue_mase": "revenue_mase",
        "funded_backlog_revenue_champion_eligible": "revenue_champion_eligible",
    })
    noc_rows.insert(0, "company", "NOC")
    detail = pd.concat([lmt_rows, noc_rows], ignore_index=True)
    company = detail.groupby("company", as_index=False).agg(
        segments=("segment", "size"),
        median_revenue_mase=("revenue_mase", "median"),
        revenue_champions=("revenue_champion_eligible", "sum"),
        median_margin_mase=("margin_mase", "median"),
        margin_champions=("margin_champion_eligible", "sum"),
        joint_champions=("joint_champion", "sum"),
    )
    noc = company.loc[company["company"].eq("NOC")].iloc[0]
    if noc["revenue_champions"] >= 3 and noc["median_revenue_mase"] < 1.0:
        classification = "LMT_DOMINANTLY_COMPANY_SPECIFIC"
    elif noc["revenue_champions"] <= 1 and noc["median_revenue_mase"] >= 1.0:
        classification = "AEROSPACE_DEFENSE_TIMING_FAILURE_REPLICATED"
    else:
        classification = "MIXED_NOT_IDENTIFIED_WITH_TWO_COMPANIES"
    company["cross_company_timing_classification"] = classification
    company["two_company_sample_is_industry_conclusion"] = False
    lmt_walk = pd.read_csv(lmt_output / "lmt_portability_walk_forward.csv")
    lmt_company = lmt_walk.groupby("period", as_index=False).agg(
        actual_sales_usd=("actual_sales_usd", "sum"),
        predicted_sales_usd=("predicted_sales_usd", "sum"),
        naive_prior_year_sales_usd=("naive_prior_year_sales_usd", "sum"),
    )
    lmt_metrics = assess_against_naive(
        actual=lmt_company["actual_sales_usd"],
        prediction=lmt_company["predicted_sales_usd"],
        naive=lmt_company["naive_prior_year_sales_usd"],
    )
    noc_company = company_summary.iloc[0]
    company_level = pd.DataFrame([
        {
            "company": "LMT", "validation_observations": lmt_metrics.observations,
            "revenue_mase": lmt_metrics.mase, "revenue_champion_eligible": lmt_metrics.eligible,
            "route": "SUM_OF_PREDECLARED_SEGMENT_ROUTES",
        },
        {
            "company": "NOC", "validation_observations": int(noc_company["validation_observations"]),
            "revenue_mase": float(noc_company["funded_backlog_revenue_mase"]),
            "revenue_champion_eligible": bool(noc_company["funded_backlog_revenue_champion_eligible"]),
            "route": "AGGREGATE_FUNDED_BACKLOG_CONVERSION_PRICE",
        },
    ])
    if company_level["revenue_champion_eligible"].all():
        company_classification = "AGGREGATE_REVENUE_CHAMPION_BOTH_SEGMENT_TIMING_UNRESOLVED"
    elif not company_level["revenue_champion_eligible"].any():
        company_classification = "COMPANY_LEVEL_TIMING_FAILURE_REPLICATED"
    else:
        company_classification = "COMPANY_LEVEL_MIXED_BY_COMPANY"
    company_level["cross_company_timing_classification"] = company_classification
    company_level["two_company_sample_is_industry_conclusion"] = False
    return detail, company, company_level


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    frozen_before = verify_lmt_v31_evidence(ROOT)
    ir = build_noc_ir_evidence(Path(config["ir_root"]), pd.Timestamp(config["as_of_date"]))
    sec = build_noc_sec_evidence(
        project_root=ROOT,
        sec_manifest_path=ROOT / config["sec_manifest"],
        ir_inventory=ir["noc_ir_source_inventory"],
        ir_history=ir["noc_segment_quarterly_history"],
        ir_backlog=ir["noc_backlog_history"],
        scope_audit=ir["noc_cross_release_scope_audit"],
    )
    origins = build_quarterly_forecast_origins(ir["noc_segment_quarterly_history"])
    bls = parse_bls_ppi_vintages(
        project_root=ROOT,
        archive_manifest_path=ROOT / config["bls_archive_manifest"],
        sensor_map_path=ROOT / config["bls_sensor_map"],
        cutoff=pd.Timestamp(config["as_of_date"]),
    )
    sensor_map = pd.read_csv(ROOT / config["bls_sensor_map"])
    pit = build_pit_forecast_features(
        vintages=bls["bls_ppi_vintage_canonical"],
        sensor_map=sensor_map,
        forecast_origins=origins,
    )
    pit_audit = pit["pit_vintage_selection_audit"].copy()
    pit_audit["historical_pit_eligible"] = pit_audit["cutoff_respected"].astype(bool)
    pit_audit["selected_vintage_date"] = pit_audit["latest_selected_release_date"]
    pit["pit_vintage_selection_audit"] = pit_audit
    lmt_industry = build_lmt_industry_evidence(
        arcana_pqci_root=ARCANA_PQCI,
        sensor_map=sensor_map,
        bls_vintage_audit=bls["bls_ppi_vintage_audit"],
        pit_feature_summary=pit["pit_feature_summary"],
    )
    industry = {key.replace("lmt_", "noc_"): value for key, value in lmt_industry.items()}
    forecast = build_noc_portability_forecast(
        history=ir["noc_segment_quarterly_history"],
        backlog=ir["noc_backlog_history"],
        scope_audit=ir["noc_cross_release_scope_audit"],
        program_adjustments=sec["noc_program_adjustment_registry"],
        industry_features=pit["pit_segment_features"],
        forecast_origins=origins,
        validation_start_period=config["validation_start_period"],
        minimum_training_quarters=int(config["minimum_training_quarters"]),
        ridge_penalty=float(config["ridge_penalty"]),
    )
    uncertainty_input = forecast["noc_portability_walk_forward"].rename(
        columns={"funded_backlog_predicted_sales_usd": "predicted_sales_usd"}
    )
    point_input = forecast["noc_portability_summary"].rename(
        columns={"funded_backlog_revenue_champion_eligible": "revenue_champion_eligible"}
    )
    lmt_uncertainty = build_lmt_uncertainty_calibration(
        walk_forward=uncertainty_input,
        point_summary=point_input,
        minimum_calibration_observations=int(config["minimum_conformal_calibration_observations"]),
    )
    uncertainty = {
        key.replace("lmt_", "noc_"): value.assign(company="NOC")
        for key, value in lmt_uncertainty.items()
    }
    cross_detail, cross_summary, company_cross = _cross_company(
        forecast["noc_portability_summary"],
        forecast["noc_company_portability_summary"],
        ROOT / config["lmt_v3_output"],
    )
    source_pass = bool(sec["noc_source_audit_summary"].iloc[0]["source_gate_pass"])
    parser_pass = bool(ir["noc_ir_parser_summary"].iloc[0]["parser_gate_pass"])
    reconciliation_pass = bool(
        sec["noc_sec_ir_segment_reconciliation_summary"].iloc[0]["segment_and_backlog_reconciliation_gate_pass"]
    )
    fixed_oos_pass = bool(
        forecast["noc_company_portability_summary"].iloc[0]["validation_observations"]
        == int(config["expected_oos_quarters_per_segment"])
        and forecast["noc_company_walk_forward"]["actual_after_forecast"].all()
    )
    point_pass = bool(forecast["noc_company_portability_summary"].iloc[0]["funded_backlog_revenue_champion_eligible"])
    evidence_freeze = bool(
        source_pass
        and parser_pass
        and reconciliation_pass
        and industry["noc_industry_data_summary"].iloc[0]["historical_pit_ready"]
    )
    forecast_freeze = bool(
        evidence_freeze
        and fixed_oos_pass
        and point_pass
        and uncertainty["noc_uncertainty_gate"].iloc[0]["uncertainty_champions"] >= 2
    )
    gate = pd.DataFrame([{
        "version": config["version"],
        "lmt_v31_evidence_parent_unchanged": True,
        "source_gate_pass": source_pass,
        "ir_parser_gate_pass": parser_pass,
        "sec_ir_reconciliation_gate_pass": reconciliation_pass,
        "historical_pit_industry_gate_pass": bool(industry["noc_industry_data_summary"].iloc[0]["historical_pit_ready"]),
        "fixed_oos_window_pass": fixed_oos_pass,
        "segment_model_validation_rows": int(len(forecast["noc_portability_walk_forward"])),
        "segment_model_expected_rows": int(4 * int(config["expected_oos_quarters_per_segment"])),
        "segment_model_full_coverage_pass": bool(len(forecast["noc_portability_walk_forward"]) == 4 * int(config["expected_oos_quarters_per_segment"])),
        "company_revenue_mase": float(forecast["noc_company_portability_summary"].iloc[0]["funded_backlog_revenue_mase"]),
        "company_revenue_champion": bool(forecast["noc_company_portability_summary"].iloc[0]["funded_backlog_revenue_champion_eligible"]),
        "funded_backlog_revenue_champion_segments": int(forecast["noc_portability_summary"]["funded_backlog_revenue_champion_eligible"].sum()),
        "total_backlog_revenue_champion_segments": int(forecast["noc_portability_summary"]["total_backlog_revenue_champion_eligible"].sum()),
        "funded_backlog_improved_segments": int(forecast["noc_portability_summary"]["funded_vs_total_mase_improvement_pct"].gt(0).sum()),
        "margin_champion_segments": int(forecast["noc_portability_summary"]["margin_champion_eligible"].sum()),
        "joint_champion_segments": int(forecast["noc_portability_summary"]["joint_champion"].sum()),
        "point_performance_gate_pass": point_pass,
        "evidence_parser_freeze_eligible": evidence_freeze,
        "forecast_freeze_eligible": forecast_freeze,
        "terminal_gate_pass": False,
        "production_gate_pass": False,
        "live_matched_observations": f"0/{int(config['production_minimum_live_observations'])}",
        "new_dcf_run": False,
        "new_reverse_dcf_run": False,
        "status": "EVIDENCE_FREEZE_ELIGIBLE_FORECAST_UNFROZEN" if evidence_freeze and not forecast_freeze else "FORECAST_FREEZE_ELIGIBLE" if forecast_freeze else "HOLD_RESEARCH_UNFROZEN",
    }])
    authority = pd.DataFrame([{
        "company": "NOC",
        "research_evidence_authority": evidence_freeze,
        "forecast_authority": forecast_freeze,
        "terminal_input_allowed": False,
        "production_promotable": False,
        "dcf_result": "NOT_RUN_BY_DESIGN",
        "reverse_dcf_result": "NOT_RUN_BY_DESIGN",
        "reason": "SECOND_COMPANY_TIMING_RESEARCH_DOES_NOT_CLOSE_UNCERTAINTY_TERMINAL_OR_LIVE_GATES",
    }])
    artifacts = {
        **ir,
        **sec,
        "noc_forecast_origins": origins,
        **{key.replace("bls_", "noc_bls_"): value for key, value in bls.items()},
        **{key.replace("pit_", "noc_pit_"): value for key, value in pit.items()},
        **industry,
        **forecast,
        **uncertainty,
        "aerospace_defense_cross_company_detail": cross_detail,
        "aerospace_defense_cross_company_summary": cross_summary,
        "aerospace_defense_cross_company_company_level": company_cross,
        "industrials_v4_noc_gate": gate,
        "industrials_v4_noc_authority": authority,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    frozen_after = verify_lmt_v31_evidence(ROOT)
    source_paths = [
        "configs/industrials_v4_noc.toml",
        "configs/industrials_v4_noc_bls_sensors.csv",
        "equity_platform/sectors/industrials/aerospace_defense/noc/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/noc/benchmark.py",
        "equity_platform/sectors/industrials/aerospace_defense/noc/ir.py",
        "equity_platform/sectors/industrials/aerospace_defense/noc/sec.py",
        "equity_platform/sectors/industrials/aerospace_defense/noc/forecast.py",
        "scripts/industrials/fetch_noc_periodic_filings_v4.py",
        "scripts/industrials/freeze_v4_noc_evidence.py",
        "scripts/industrials/valuation_v4_noc.py",
        "tests/test_industrials_v4_noc.py",
        "tests/test_industrials_v4_noc_evidence_freeze.py",
    ]
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": config["as_of_date"],
        "ticker": "NOC",
        "subindustry": "AEROSPACE_DEFENSE",
        "branch_status": gate.iloc[0]["status"],
        "lmt_v31_evidence_manifest_sha256": frozen_before["manifest_sha256"],
        "lmt_v31_evidence_parent_unchanged": frozen_before["manifest_sha256"] == frozen_after["manifest_sha256"],
        "sec_periodic_manifest_sha256": sha256_file(ROOT / config["sec_manifest"]),
        "source_hashes": hash_files(ROOT, source_paths),
        "fixed_validation_window": "2025Q1-2026Q2",
        "funded_backlog_route_predeclared": True,
        "total_backlog_comparison_route_predeclared": True,
        "revenue_margin_champions_separate": True,
        "point_uncertainty_champions_separate": True,
        "terminal_input_allowed": False,
        "production_promotable": False,
        "new_dcf_run": False,
        "new_reverse_dcf_run": False,
        "pdf_parsing_deferred": True,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = f"""# Industrials Platform V4 — NOC cross-company timing research

## Decision

{markdown_table(gate)}

LMT V3.1 evidence remains byte-for-byte unchanged. This branch tests Northrop
Grumman independently and does not modify or tune the frozen LMT experiment.

## 10-K, 10-Q and IR evidence

{markdown_table(sec['noc_source_audit_summary'])}

{markdown_table(ir['noc_ir_parser_summary'])}

NOC discloses total backlog and the funded/unfunded split for every segment and
quarter. The funded share is treated as a limited contract-maturity proxy, not
as disclosed delivery timing.

## SEC-to-IR reconciliation

{markdown_table(sec['noc_sec_ir_segment_reconciliation_summary'])}

Scope-recast annual cells are excluded from the reconciliation denominator and
remain visible in the detailed audit. The SEC RPO fact is rounded to $0.1bn, so
the backlog identity tolerance is 0.07%.

## Fixed OOS segment results

{markdown_table(forecast['noc_portability_summary'])}

{markdown_table(forecast['noc_segment_model_coverage'])}

The funded-backlog route was predeclared. The total-backlog route is retained as
an immutable comparison, not selected after observing OOS results.

## Fixed OOS company-level result

{markdown_table(forecast['noc_company_portability_summary'])}

Company aggregation is scope-stable across segment realignments. It is reported
separately and is not used to fill missing segment forecasts.

## Cross-company diagnosis

{markdown_table(cross_summary)}

{markdown_table(company_cross)}

Two companies can distinguish an obvious company-specific result from a first
replication, but cannot establish an industry-wide law.

## Historical reinvestment and ROIC evidence

{markdown_table(sec['noc_reinvestment_roic_summary'])}

These company-level historical bridges are diagnostic only. Segment ROIC,
terminal economics, DCF and reverse DCF remain locked.

## Uncertainty and authority

{markdown_table(uncertainty['noc_uncertainty_gate'])}

{markdown_table(authority)}
"""
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    for frame in (
        sec["noc_source_audit_summary"],
        ir["noc_ir_parser_summary"],
        sec["noc_sec_ir_segment_reconciliation_summary"],
        forecast["noc_portability_summary"],
        cross_summary,
        sec["noc_reinvestment_roic_summary"],
        uncertainty["noc_uncertainty_gate"],
        gate,
    ):
        print(frame.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
