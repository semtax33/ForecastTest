from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import hash_files
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.aerospace_defense.aggregate_revenue_v1 import (
    verify_noc_aggregate_revenue_v1,
)
from equity_platform.sectors.industrials.aerospace_defense.hii import (
    build_hii_forecast_research,
    build_hii_industry_evidence,
    build_hii_ir_evidence,
    build_hii_sec_evidence,
)
from equity_platform.sectors.industrials.aerospace_defense.lmt_v31.benchmark import (
    verify_lmt_v31_evidence,
)
from equity_platform.sectors.industrials.aerospace_defense.noc.benchmark import (
    verify_noc_v4_evidence,
)


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs/industrials_v5_hii.toml"
OUTPUT = ROOT / "output/industrials_v5_hii_third_company_research"


def _three_company(
    forecast: dict[str, pd.DataFrame]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    prior = pd.read_csv(
        ROOT / "output/industrials_v4_noc_cross_company_research/aerospace_defense_cross_company_company_level.csv"
    )[["company", "validation_observations", "revenue_mase", "revenue_champion_eligible", "route"]]
    authority = forecast["hii_forecast_authority"].iloc[0]
    hii = pd.DataFrame([{
        "company": "HII", "validation_observations": 6,
        "revenue_mase": authority["aggregate_revenue_mase"],
        "revenue_champion_eligible": authority["aggregate_revenue_point_authority"],
        "route": authority["aggregate_revenue_champion_route"],
    }])
    company = pd.concat([prior, hii], ignore_index=True)
    company["selection_outcome_blind"] = True
    all_pass = bool(company["revenue_champion_eligible"].all())
    prior_segment = pd.read_csv(
        ROOT / "output/industrials_v4_noc_cross_company_research/aerospace_defense_cross_company_detail.csv"
    )[["company", "segment", "revenue_mase", "revenue_champion_eligible", "margin_mase", "margin_champion_eligible"]]
    hii_revenue = forecast["hii_segment_revenue_champions"][[
        "segment", "mase", "beats_prior_year_naive"
    ]].rename(columns={"mase": "revenue_mase", "beats_prior_year_naive": "revenue_champion_eligible"})
    hii_margin = forecast["hii_segment_margin_champions"][[
        "segment", "mase", "beats_prior_year_naive"
    ]].rename(columns={"mase": "margin_mase", "beats_prior_year_naive": "margin_champion_eligible"})
    hii_segment = hii_revenue.merge(hii_margin, on="segment", validate="one_to_one")
    hii_segment.insert(0, "company", "HII")
    segment = pd.concat([prior_segment, hii_segment], ignore_index=True)
    segment["joint_champion"] = segment["revenue_champion_eligible"] & segment["margin_champion_eligible"]
    segment_mixed = bool(segment["revenue_champion_eligible"].any() and not segment["revenue_champion_eligible"].all())
    pattern = pd.DataFrame([{
        "companies": 3, "aggregate_revenue_pass_companies": int(company["revenue_champion_eligible"].sum()),
        "all_three_aggregate_revenue_pass": all_pass,
        "segments_compared": len(segment),
        "segments_beating_naive": int(segment["revenue_champion_eligible"].sum()),
        "segment_timing_mixed_across_three_companies": segment_mixed,
        "segment_timing_uniformly_identified": bool(segment["revenue_champion_eligible"].all()),
        "platform_hypothesis": (
            "THREE_COMPANY_AGGREGATE_REPEATED_SEGMENT_TIMING_MIXED_RESEARCH_HYPOTHESIS"
            if all_pass and segment_mixed
            else "THIRD_COMPANY_DOES_NOT_REPLICATE_AGGREGATE_PASS"
            if not all_pass else "AGGREGATE_AND_SEGMENT_PASS_REQUIRES_MORE_COMPANIES"
        ),
        "industry_conclusion_allowed": False,
        "production_authority": False,
    }])
    company["three_company_platform_hypothesis"] = pattern.iloc[0]["platform_hypothesis"]
    company["three_company_sample_is_production_evidence"] = False
    return company, segment, pattern


def main() -> int:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    parents_before = {
        "lmt_v31": verify_lmt_v31_evidence(ROOT),
        "noc_v4": verify_noc_v4_evidence(ROOT),
        "noc_aggregate_v1": verify_noc_aggregate_revenue_v1(ROOT),
    }
    selection = pd.read_csv(OUTPUT / "ad_third_company_selected.csv").iloc[0]
    if selection["ticker"] != "HII" or not bool(selection["selection_outcome_blind"]):
        raise ValueError("HII must be selected by the pre-run outcome-blind policy")
    ir = build_hii_ir_evidence(Path(config["ir_root"]), pd.Timestamp(config["as_of_date"]))
    sec = build_hii_sec_evidence(
        project_root=ROOT,
        manifest_path=ROOT / config["sec_manifest"],
        ir_history=ir["hii_segment_as_reported_pit_history"],
    )
    industry = build_hii_industry_evidence(
        project_root=ROOT,
        archive_manifest_path=ROOT / config["bls_archive_manifest"],
        sensor_map_path=ROOT / "configs/industrials_v5_hii_bls_sensors.csv",
        company_history=ir["hii_company_as_reported_pit_history"],
        cutoff=pd.Timestamp(config["as_of_date"]),
    )
    forecast = build_hii_forecast_research(
        company_history=ir["hii_company_as_reported_pit_history"],
        segment_history=ir["hii_segment_as_reported_pit_history"],
        backlog=ir["hii_contract_backlog_evidence"],
        programs=ir["hii_program_timing_evidence"],
        origins=industry["hii_forecast_origins"],
        industry_features=industry["hii_pit_segment_features"],
        validation_start=config["validation_start_period"],
        validation_end=config["validation_end_period"],
    )
    company_cross, segment_cross, hypothesis = _three_company(forecast)
    source_pass = bool(sec["hii_sec_source_summary"].iloc[0]["source_gate_pass"])
    parser_pass = bool(ir["hii_ir_parser_summary"].iloc[0]["parser_gate_pass"])
    pit_pass = bool(industry["hii_industry_data_summary"].iloc[0]["historical_pit_ready"])
    coverage_pass = bool(
        forecast["hii_forecast_coverage"].iloc[0]["company_model_oos_rows"] == 6
        and forecast["hii_forecast_coverage"].iloc[0]["segment_model_oos_rows"] == 18
        and forecast["hii_forecast_coverage"].iloc[0]["actual_after_forecast_all"]
    )
    aggregate_pass = bool(forecast["hii_forecast_authority"].iloc[0]["aggregate_revenue_point_authority"])
    evidence_freeze = source_pass and parser_pass and pit_pass
    gate = pd.DataFrame([{
        "version": config["version"], "selection_outcome_blind": True,
        "source_gate_pass": source_pass, "ir_parser_gate_pass": parser_pass,
        "historical_pit_industry_gate_pass": pit_pass, "fixed_oos_window_pass": coverage_pass,
        "evidence_parser_freeze_eligible": evidence_freeze,
        "aggregate_revenue_research_pass": aggregate_pass,
        "segment_revenue_attribution_authority": False, "margin_authority": False,
        "forecast_freeze_eligible": False, "terminal_gate_pass": False,
        "production_gate_pass": False, "live_matched_observations": "0/20",
        "new_dcf_run": False, "new_reverse_dcf_run": False,
        "status": "EVIDENCE_FREEZE_ELIGIBLE_FORECAST_UNFROZEN" if evidence_freeze else "HOLD_RESEARCH_UNFROZEN",
    }])
    artifacts = {
        **ir, **sec, **industry, **forecast,
        "aerospace_defense_three_company_company_level": company_cross,
        "aerospace_defense_three_company_segment_level": segment_cross,
        "aerospace_defense_three_company_hypothesis": hypothesis,
        "industrials_v5_hii_gate": gate,
    }
    write_csv_artifacts(OUTPUT, artifacts)
    parents_after = {
        "lmt_v31": verify_lmt_v31_evidence(ROOT),
        "noc_v4": verify_noc_v4_evidence(ROOT),
        "noc_aggregate_v1": verify_noc_aggregate_revenue_v1(ROOT),
    }
    source_paths = [
        "configs/industrials_v5_ad_third_company_candidates.csv",
        "configs/industrials_v5_hii.toml", "configs/industrials_v5_hii_bls_sensors.csv",
        "equity_platform/sectors/industrials/aerospace_defense/hii/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/selection.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/ir.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/sec.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/industry.py",
        "equity_platform/sectors/industrials/aerospace_defense/hii/forecast.py",
        "scripts/industrials/select_ad_third_company_v5.py",
        "scripts/industrials/fetch_hii_periodic_filings_v5.py",
        "scripts/industrials/valuation_v5_hii.py",
    ]
    metadata = {
        "version": config["version"], "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_ticker": "HII", "selection_outcome_blind": True,
        "fixed_validation_window": f"{config['validation_start_period']}-{config['validation_end_period']}",
        "source_layers": ["SEC_10K", "SEC_10Q", "SEC_FINANCIAL_STATEMENTS", "SEC_NOTES", "IR_HTML", "BLS_AS_RELEASED_VINTAGES", "CENSUS_BEA_CONTEXT_ONLY"],
        "history_authorities": ["AS_REPORTED_PIT_HISTORY", "CURRENTLY_RECAST_COMPARABLE_HISTORY"],
        "pdf_parsing_used": False,
        "authority": {
            "aggregate_revenue_point": bool(aggregate_pass), "segment_revenue_attribution": False,
            "margin": False, "roic_reinvestment": "HISTORICAL_DIAGNOSTIC_ONLY",
            "terminal": False, "production": False, "dcf": False, "reverse_dcf": False,
        },
        "parents_unchanged": all(
            parents_before[key]["manifest_sha256"] == parents_after[key]["manifest_sha256"]
            for key in parents_before
        ),
        "parent_manifest_sha256": {key: value["manifest_sha256"] for key, value in parents_after.items()},
        "source_code_sha256": hash_files(ROOT, source_paths),
    }
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    company_metrics = forecast["hii_company_route_metrics"]
    segment_champions = forecast["hii_segment_revenue_champions"]
    margin_champions = forecast["hii_segment_margin_champions"]
    report = "\n".join([
        "# HII V5 third-company A&D research", "",
        "HII was selected before forecast evaluation. This is research evidence, not production authority.", "",
        "## Company revenue routes", "", markdown_table(company_metrics), "",
        "## Segment revenue champions", "", markdown_table(segment_champions), "",
        "## Segment margin diagnostics", "", markdown_table(margin_champions), "",
        "## Three-company hypothesis", "", markdown_table(hypothesis), "",
        "## Authority", "", markdown_table(forecast["hii_forecast_authority"]), "",
        "DCF and reverse DCF were not run because terminal and production gates remain locked.", "",
    ])
    (OUTPUT / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT), "selected": "HII", "source_pass": source_pass,
        "parser_pass": parser_pass, "pit_pass": pit_pass, "fixed_oos_pass": coverage_pass,
        "aggregate_revenue_research_pass": aggregate_pass,
        "company_champion": forecast["hii_forecast_authority"].iloc[0].to_dict(),
        "three_company_hypothesis": hypothesis.iloc[0].to_dict(),
        "parents_unchanged": metadata["parents_unchanged"],
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
