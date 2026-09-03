from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import hash_files, sha256_file
from equity_platform.core.champion_gate import assess_against_naive
from equity_platform.core.pit import build_quarterly_forecast_origins
from equity_platform.experiments import ExperimentRunner, ExperimentSpec
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import markdown_table, write_csv_artifacts
from equity_platform.sectors.industrials.aerospace_defense.gd_v6 import (
    build_gd_conditional_financial_bridge,
    build_gd_conditional_valuation,
    build_gd_forecast_research,
    build_gd_industry_evidence,
    build_gd_ir_evidence,
    build_gd_margin_roic_reinvestment_research,
    build_gd_market_evidence,
    build_gd_prospective_segment_forecast,
    build_gd_sec_evidence,
)
from equity_platform.sectors.industrials.aerospace_defense.hii_v54 import (
    verify_hii_v54_margin_mechanism_research,
)
from equity_platform.sectors.industrials.v15.pit import (
    build_pit_forecast_features,
    parse_bls_ppi_vintages,
)


ROOT = PROJECT_ROOT
EXPERIMENT = ExperimentSpec(
    experiment_id="industrials.aerospace_defense.gd.v6",
    version="INDUSTRIALS_PLATFORM_V6_GD_FOURTH_COMPANY_RESEARCH",
    config_path=Path("configs/industrials_v6_gd.toml"),
    output_path=Path("output/industrials_v6_gd_fourth_company_research"),
)


def _cross_company(gd_forecast: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    lmt_path = ROOT / "output/industrials_v3_lmt_aerospace_research/lmt_portability_summary.csv"
    if lmt_path.exists():
        lmt = pd.read_csv(lmt_path)[
            ["segment", "revenue_mase", "margin_mase", "joint_champion"]
        ]
        lmt.insert(0, "company", "LMT")
        rows.append(lmt)
    noc_path = ROOT / "output/industrials_v4_noc_cross_company_research/noc_portability_summary.csv"
    if noc_path.exists():
        noc = pd.read_csv(noc_path)[
            ["segment", "funded_backlog_revenue_mase", "margin_mase", "joint_champion"]
        ].rename(columns={"funded_backlog_revenue_mase": "revenue_mase"})
        noc.insert(0, "company", "NOC")
        rows.append(noc)
    gd = gd_forecast["gd_portability_summary"][
        ["segment", "funded_backlog_revenue_mase", "margin_mase", "joint_champion"]
    ].rename(columns={"funded_backlog_revenue_mase": "revenue_mase"})
    gd.insert(0, "company", "GD")
    rows.append(gd)
    detail = pd.concat(rows, ignore_index=True)
    detail["revenue_champion"] = detail["revenue_mase"].lt(1.0)
    detail["margin_champion"] = detail["margin_mase"].lt(1.0)
    summary = detail.groupby("company", as_index=False).agg(
        segments=("segment", "size"),
        median_revenue_mase=("revenue_mase", "median"),
        revenue_champion_segments=("revenue_champion", "sum"),
        median_margin_mase=("margin_mase", "median"),
        margin_champion_segments=("margin_champion", "sum"),
        joint_champion_segments=("joint_champion", "sum"),
    )
    company_rows: list[dict[str, object]] = []
    lmt_walk_path = ROOT / "output/industrials_v3_lmt_aerospace_research/lmt_portability_walk_forward.csv"
    if lmt_walk_path.exists():
        lmt_walk = pd.read_csv(lmt_walk_path).groupby("period", as_index=False).agg(
            actual_sales_usd=("actual_sales_usd", "sum"),
            predicted_sales_usd=("predicted_sales_usd", "sum"),
            naive_prior_year_sales_usd=("naive_prior_year_sales_usd", "sum"),
        )
        metric = assess_against_naive(
            actual=lmt_walk["actual_sales_usd"],
            prediction=lmt_walk["predicted_sales_usd"],
            naive=lmt_walk["naive_prior_year_sales_usd"],
        )
        company_rows.append(
            {"company": "LMT", "aggregate_revenue_mase": metric.mase, "aggregate_revenue_champion": metric.eligible}
        )
    noc_company_path = ROOT / "output/industrials_v4_noc_cross_company_research/noc_company_portability_summary.csv"
    if noc_company_path.exists():
        row = pd.read_csv(noc_company_path).iloc[0]
        company_rows.append(
            {
                "company": "NOC",
                "aggregate_revenue_mase": row["funded_backlog_revenue_mase"],
                "aggregate_revenue_champion": bool(row["funded_backlog_revenue_champion_eligible"]),
            }
        )
    hii_path = ROOT / "output/industrials_v5_hii_third_company_research/hii_forecast_authority.csv"
    if hii_path.exists():
        row = pd.read_csv(hii_path).iloc[0]
        company_rows.append(
            {
                "company": "HII",
                "aggregate_revenue_mase": row["aggregate_revenue_mase"],
                "aggregate_revenue_champion": bool(row["aggregate_revenue_point_authority"]),
            }
        )
    row = gd_forecast["gd_company_portability_summary"].iloc[0]
    company_rows.append(
        {
            "company": "GD",
            "aggregate_revenue_mase": row["funded_backlog_revenue_mase"],
            "aggregate_revenue_champion": bool(row["funded_backlog_revenue_champion_eligible"]),
        }
    )
    aggregate = pd.DataFrame(company_rows)
    aggregate["four_company_industry_law_claim_allowed"] = False
    return detail, summary.merge(aggregate, on="company", how="outer")


def main() -> int:
    runner = ExperimentRunner(root=ROOT, spec=EXPERIMENT)
    config = runner.config
    output = runner.output_path
    parent_before = runner.stage(
        "verify_frozen_parent",
        lambda: verify_hii_v54_margin_mechanism_research(ROOT),
        consumes=("hii_v54_manifest",),
    )
    ir = runner.stage(
        "ir_evidence",
        lambda: build_gd_ir_evidence(
            Path(config["ir_root"]), pd.Timestamp(config["as_of_date"])
        ),
        consumes=("arcana_ir",),
    )
    sec = runner.stage(
        "sec_evidence",
        lambda: build_gd_sec_evidence(
            project_root=ROOT,
            manifest_path=ROOT / config["sec_manifest"],
            company_history=ir["gd_company_as_reported_pit_history"],
        ),
        consumes=("sec_manifest", "gd_company_as_reported_pit_history"),
    )
    historical_origins = build_quarterly_forecast_origins(
        ir["gd_segment_as_reported_pit_history"]
    )
    prospective_origin = pd.DataFrame(
        [
            {
                "period": config["prospective_target_period"],
                "forecast_as_of": config["prospective_forecast_as_of"],
                "actual_available_at": config["prospective_actual_available_at"],
                "origin_period": config["prospective_origin_period"],
                "horizon_quarters": int(config["prospective_horizon_quarters"]),
                "actual_after_forecast": True,
            }
        ]
    )
    origins = pd.concat([historical_origins, prospective_origin], ignore_index=True)
    bls = runner.stage(
        "bls_pit_vintages",
        lambda: parse_bls_ppi_vintages(
            project_root=ROOT,
            archive_manifest_path=ROOT / config["bls_archive_manifest"],
            sensor_map_path=ROOT / config["bls_sensor_map"],
            cutoff=pd.Timestamp(config["as_of_date"]),
        ),
        consumes=("bls_archive_manifest", "bls_sensor_map"),
    )
    sensor_map = pd.read_csv(ROOT / config["bls_sensor_map"])
    pit = runner.stage(
        "pit_features",
        lambda: build_pit_forecast_features(
            vintages=bls["bls_ppi_vintage_canonical"],
            sensor_map=sensor_map,
            forecast_origins=origins,
        ),
        consumes=("bls_ppi_vintage_canonical", "forecast_origins"),
    )
    industry = runner.stage(
        "industry_evidence",
        lambda: build_gd_industry_evidence(
            arcana_pqci_root=Path(config["arcana_pqci_root"]),
            labor_snapshot_path=ROOT / config["bls_labor_snapshot"],
            labor_maximum_reference_period=config["bls_labor_maximum_reference_period"],
            sensor_map=sensor_map,
            bls_vintage_audit=bls["bls_ppi_vintage_audit"],
            pit_feature_summary=pit["pit_feature_summary"],
        ),
        consumes=("arcana_pqci", "bls_labor_snapshot", "pit_feature_summary"),
    )
    forecast = runner.stage(
        "forecast_research",
        lambda: build_gd_forecast_research(
            history=ir["gd_segment_as_reported_pit_history"],
            backlog=ir["gd_backlog_history"],
            delivery_history=ir["gd_aerospace_delivery_history"],
            scope_audit=ir["gd_cross_release_scope_audit"],
            industry_features=pit["pit_segment_features"],
            forecast_origins=origins,
            validation_start_period=config["validation_start_period"],
            minimum_training_quarters=int(config["minimum_training_quarters"]),
            ridge_penalty=float(config["ridge_penalty"]),
        ),
        consumes=("ir_evidence", "pit_segment_features", "forecast_origins"),
    )
    prospective = runner.stage(
        "prospective_forecast",
        lambda: build_gd_prospective_segment_forecast(
            feature_panel=forecast["gd_portability_feature_panel"],
            history=ir["gd_segment_as_reported_pit_history"],
            backlog=ir["gd_backlog_history"],
            industry_features=pit["pit_segment_features"],
            target_period=config["prospective_target_period"],
            ridge_penalty=float(config["ridge_penalty"]),
        ),
        consumes=("gd_portability_feature_panel", "ir_evidence", "pit_segment_features"),
        produces=("gd_2026q3_prospective_segment_forecast",),
    )
    research = runner.stage(
        "economics_research",
        lambda: build_gd_margin_roic_reinvestment_research(
            segment_history=ir["gd_segment_as_reported_pit_history"],
            company_history=ir["gd_company_as_reported_pit_history"],
            annual_bridge=sec["gd_annual_reinvestment_roic_bridge"],
            terminal_margin_hypotheses_pct=list(config["terminal_margin_hypotheses_pct"]),
        ),
        consumes=("ir_evidence", "gd_annual_reinvestment_roic_bridge"),
    )
    financial_bridge = runner.stage(
        "financial_bridge",
        lambda: build_gd_conditional_financial_bridge(
            prospective_segment_forecast=prospective, research=research
        ),
        consumes=("prospective_forecast", "economics_research"),
        produces=("gd_2026q3_conditional_financial_bridge",),
    )
    annual = sec["gd_annual_reinvestment_roic_bridge"].iloc[-1]
    market = runner.stage(
        "market_and_wacc",
        lambda: build_gd_market_evidence(
            root=ROOT,
            config=config,
            latest_balance=sec["gd_periodic_financial_history"].iloc[-1],
            tax_rate_pct=float(annual["effective_tax_rate_pct"]),
        ),
        consumes=("market_snapshots", "gd_periodic_financial_history"),
    )
    valuation = runner.stage(
        "conditional_valuation",
        lambda: build_gd_conditional_valuation(
            config=config,
            market=market["gd_market_capitalization_bridge"],
            wacc=market["gd_independent_wacc_range"],
            financial_bridge=financial_bridge,
            margin_distribution=research["gd_margin_distribution_summary"],
            roic_summary=research["gd_roic_reinvestment_research_summary"],
            company_ttm_history=research["gd_company_ttm_margin_history"],
            latest_tax_rate_pct=float(annual["effective_tax_rate_pct"]),
        ),
        consumes=("financial_bridge", "market_and_wacc", "economics_research"),
    )
    cross_detail, cross_summary = runner.stage(
        "cross_company_validation",
        lambda: _cross_company(forecast),
        consumes=("forecast_research", "frozen_peer_outputs"),
        produces=(
            "aerospace_defense_four_company_segment_comparison",
            "aerospace_defense_four_company_summary",
        ),
    )

    source = sec["gd_sec_source_summary"].iloc[0]
    reconciliation = sec["gd_sec_ir_reconciliation_summary"].iloc[0]
    company_performance = forecast["gd_company_portability_summary"].iloc[0]
    segment_summary = forecast["gd_portability_summary"]
    fixed_oos = bool(
        len(forecast["gd_portability_walk_forward"])
        == int(config["expected_segments"])
        * int(config["expected_oos_quarters_per_segment"])
        and forecast["gd_portability_walk_forward"]["actual_after_forecast"].all()
    )
    evidence_ready = bool(
        source["source_gate_pass"]
        and ir["gd_ir_parser_summary"].iloc[0]["parser_gate_pass"]
        and industry["gd_industry_data_summary"].iloc[0]["historical_pit_ready"]
    )
    forecast_ready = bool(
        evidence_ready
        and fixed_oos
        and company_performance["funded_backlog_revenue_champion_eligible"]
        and company_performance["margin_champion_eligible"]
    )
    gate = pd.DataFrame(
        [
            {
                "version": config["version"],
                "hii_v54_parent_unchanged": True,
                "sec_10k_filings": source["sec_10k_filings"],
                "sec_10q_filings": source["sec_10q_filings"],
                "ir_earnings_releases": ir["gd_ir_parser_summary"].iloc[0]["earnings_releases"],
                "source_gate_pass": bool(source["source_gate_pass"]),
                "ir_parser_gate_pass": bool(ir["gd_ir_parser_summary"].iloc[0]["parser_gate_pass"]),
                "sec_ir_revenue_reconciliation_pass": bool(reconciliation["revenue_reconciliation_gate_pass"]),
                "sec_ir_operating_income_reconciliation_complete": bool(reconciliation["operating_income_reconciliation_complete"]),
                "unidentified_operating_income_bridge_rows": int(reconciliation["unidentified_operating_income_bridge_rows"]),
                "historical_pit_industry_gate_pass": bool(industry["gd_industry_data_summary"].iloc[0]["historical_pit_ready"]),
                "fixed_oos_window_pass": fixed_oos,
                "segment_validation_rows": len(forecast["gd_portability_walk_forward"]),
                "company_revenue_mase": company_performance["funded_backlog_revenue_mase"],
                "company_margin_mase": company_performance["margin_mase"],
                "segment_revenue_champions": int(segment_summary["funded_backlog_revenue_champion_eligible"].sum()),
                "segment_margin_champions": int(segment_summary["margin_champion_eligible"].sum()),
                "segment_joint_champions": int(segment_summary["joint_champion"].sum()),
                "gulfstream_delivery_challenger_champion": bool(forecast["gd_aerospace_delivery_challenger_summary"].iloc[0]["revenue_champion_eligible"]),
                "evidence_freeze_eligible": evidence_ready,
                "forecast_research_freeze_eligible": forecast_ready,
                "conditional_dcf_run": True,
                "conditional_reverse_dcf_run": True,
                "terminal_gate_pass": False,
                "fair_value_claim_allowed": False,
                "production_gate_pass": False,
                "live_matched_observations": f"0/{int(config['production_minimum_live_observations'])}",
                "status": "RESEARCH_FREEZE_ELIGIBLE_CONDITIONAL_VALUATION_TERMINAL_LOCKED" if forecast_ready else "HOLD_RESEARCH_UNFROZEN",
            }
        ]
    )
    artifacts = {
        **ir,
        **sec,
        "gd_forecast_origins": origins,
        **{key.replace("bls_", "gd_bls_"): value for key, value in bls.items()},
        **{key.replace("pit_", "gd_pit_"): value for key, value in pit.items()},
        **industry,
        **forecast,
        "gd_2026q3_prospective_segment_forecast": prospective,
        **research,
        "gd_2026q3_conditional_financial_bridge": financial_bridge,
        **market,
        **valuation,
        "aerospace_defense_four_company_segment_comparison": cross_detail,
        "aerospace_defense_four_company_summary": cross_summary,
        "industrials_v6_gd_gate": gate,
        "experiment_run_ledger": runner.ledger(),
    }
    write_csv_artifacts(output, artifacts)
    parent_after = verify_hii_v54_margin_mechanism_research(ROOT)
    if parent_before["manifest_sha256"] != parent_after["manifest_sha256"]:
        raise RuntimeError("Frozen HII V5.4 parent changed")
    source_paths = [
        "configs/industrials_v6_gd.toml",
        "configs/industrials_v6_gd_bls_sensors.csv",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/__init__.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/ir.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/sec.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/industry.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/forecast.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/research.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/market.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/valuation.py",
        "scripts/industrials/fetch_gd_periodic_filings_v6.py",
        "scripts/industrials/fetch_gd_v6_market.py",
        "scripts/industrials/valuation_v6_gd.py",
        "equity_platform/experiments/runner.py",
        "equity_platform/sectors/industrials/aerospace_defense/gd_v6/experiment.py",
    ]
    metadata = {
        "version": config["version"],
        "experiment_id": config["experiment_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": "GD",
        "as_of_date": config["as_of_date"],
        "valuation_date": config["valuation_date"],
        "parent_hii_v54_manifest_sha256": parent_before["manifest_sha256"],
        "parent_unchanged": True,
        "sec_manifest_sha256": sha256_file(ROOT / config["sec_manifest"]),
        "source_hashes": hash_files(ROOT, source_paths),
        "uses_10k": True,
        "uses_10q": True,
        "uses_ir": True,
        "uses_historical_pit_industry_data": True,
        "uses_current_revised_industry_context_in_oos": False,
        "pdf_parsing_used": False,
        "terminal_input_allowed": False,
        "fair_value_claim_allowed": False,
        "production_promoted": False,
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = f"""# Industrials Platform V6 — General Dynamics fourth-company research

## Decision

{markdown_table(gate)}

HII V5.4 remains byte-for-byte unchanged and paused. GD is a separate fourth-company
branch. Its evidence and fixed OOS forecast may be frozen, while terminal economics,
fair-value authority and production stay locked.

## 10-K, 10-Q and IR coverage

{markdown_table(sec['gd_sec_source_summary'])}

{markdown_table(ir['gd_ir_parser_summary'])}

Revenue reconciles exactly for all comparable quarters. The $26m 2020Q4 difference
between IR segment operating earnings (including corporate) and SEC GAAP operating
income remains an explicit unidentified bridge; it is not silently normalized.

## Industry data and PIT authority

{markdown_table(industry['gd_industry_data_summary'])}

BLS PPI archived release vintages are model inputs. Census M3, BEA input-output and
current-revised BLS shipbuilding labor are context only and cannot enter OOS claims.

## Fixed six-quarter OOS performance

{markdown_table(forecast['gd_portability_summary'])}

{markdown_table(forecast['gd_company_portability_summary'])}

{markdown_table(forecast['gd_aerospace_delivery_challenger_summary'])}

Gulfstream deliveries were an economically predeclared challenger, but failed the
naive gate. It is retained as attribution evidence rather than promoted.

## 2026Q3 Anchor to Bridge research forecast

{markdown_table(prospective)}

{markdown_table(financial_bridge)}

## Margin, ROIC and reinvestment diagnostics

{markdown_table(research['gd_margin_distribution_summary'])}

{markdown_table(research['gd_roic_reinvestment_research_summary'])}

R&D is not identified in GD XBRL and is never treated as economically proven zero.
The innovation-adjusted reinvestment claim therefore remains disabled.

## Conditional DCF and Reverse DCF

{markdown_table(market['gd_independent_wacc_range'])}

{markdown_table(valuation['gd_conditional_valuation_summary'])}

{markdown_table(valuation['gd_reverse_dcf_diagnostics'])}

These values are an expectations surface, not a fair-value claim. Terminal margins
and ROIC are historical conditional diagnostics; terminal and production gates stay locked.

## Cross-company comparison

{markdown_table(cross_summary)}

Four companies improve portability evidence but do not establish a universal industry law.
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    for frame in (
        sec["gd_sec_source_summary"],
        ir["gd_ir_parser_summary"],
        forecast["gd_portability_summary"],
        forecast["gd_company_portability_summary"],
        financial_bridge,
        market["gd_independent_wacc_range"],
        valuation["gd_conditional_valuation_summary"],
        gate,
    ):
        print(frame.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
