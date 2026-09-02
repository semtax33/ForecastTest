from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tomllib

import numpy as np
import pandas as pd

from energy_nowcast.data.consensus import (
    evaluate_model_vs_consensus,
    load_arcana_consensus,
    point_in_time_consensus,
)
from energy_nowcast.research.phase6.benchmark import (
    freeze_revenue_research_benchmark,
    verify_revenue_research_benchmark,
)
from energy_nowcast.research.phase6.bridge import (
    build_integrated_consolidated_earnings_bridge,
    build_midstream_ebitda_revenue_bridge,
    load_target_hierarchy,
    select_segment_predictions,
)
from energy_nowcast.research.phase6.financial_targets import (
    EP_TICKERS,
    INTEGRATED_TICKERS,
    REFINING_TICKERS,
    SERVICES_TICKERS,
    audit_integrated_segment_gold,
    build_capex_panel,
    build_integrated_segment_panel,
    build_operating_margin_panel,
    extract_ep_cash_capex,
    extract_integrated_net_income,
    extract_integrated_segment_earnings,
    extract_operating_income,
    target_source_metadata,
)
from energy_nowcast.research.phase6.validation import (
    TargetValidationResult,
    validate_target_panel,
)
from energy_nowcast.research.v351.revenue import load_companyfacts_quarterly_revenue


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "configs" / "phase6_value_driver_research.toml"
OUTPUT = ROOT / "output" / "phase6_value_driver_research"
COMPANYFACTS = ROOT.parent / "Arcana" / "data-lake" / "bronze" / "sec" / "companyfacts"
CONSENSUS = ROOT.parent / "Arcana" / "data-lake" / "bronze" / "consensus"
KPI_SNAPSHOT = ROOT / "data-lake" / "phase2_4_company_kpi_snapshot"
PHASE25 = ROOT / "output" / "phase2_5_target_aligned_research"
P21 = ROOT / "benchmarks" / "phase2_1_refining_kpi"
EP_PANEL = ROOT / "output" / "v3_5_2_clean_component" / "audited_revenue_panel.parquet"
SEGMENT_GOLD = ROOT / "configs" / "phase6_integrated_segment_gold.csv"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the post-revenue-freeze subindustry value-driver research"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _markdown(frame: pd.DataFrame) -> str:
    return "_No rows._" if frame.empty else frame.to_markdown(index=False)


def _write_result(
    artifacts: dict[str, pd.DataFrame],
    prefix: str,
    result: TargetValidationResult,
) -> None:
    artifacts[f"{prefix}_time_predictions.csv"] = result.time_predictions
    artifacts[f"{prefix}_loco_predictions.csv"] = result.loco_predictions
    artifacts[f"{prefix}_time_scorecard.csv"] = result.time_scorecard
    artifacts[f"{prefix}_loco_scorecard.csv"] = result.loco_scorecard
    artifacts[f"{prefix}_summary.csv"] = result.summary
    artifacts[f"{prefix}_gate.csv"] = result.gate


def _decision_row(
    *,
    subindustry: str,
    target: str,
    scope: str,
    result: TargetValidationResult,
    candidate_route: str,
    fallback_route: str,
) -> dict[str, object]:
    gate = bool(result.gate.iloc[0]["research_gate"])
    summary = result.summary.loc[
        result.summary["validation"].eq("TIME_HOLDOUT_8Q_PRIMARY")
    ].iloc[0]
    return {
        "subindustry": subindustry,
        "forecast_target": target,
        "scope": scope,
        "candidate_route": candidate_route,
        "selected_research_route": candidate_route if gate else fallback_route,
        "median_time_mase": summary["median_entity_mase"],
        "mean_time_mase": summary["mean_entity_mase"],
        "mean_target_level_mae": summary["mean_target_level_mae"],
        "entities": summary["entities"],
        "forecasts": summary["forecasts"],
        "research_gate": gate,
        "production_eligible": False,
    }


def _common_target_rows(
    frame: pd.DataFrame,
    *,
    subindustry: str,
    target: str,
    route_column: str,
    predicted_column: str,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    output = pd.DataFrame({
        "ticker": frame["ticker"],
        "quarter": frame["quarter"],
        "subindustry": subindustry,
        "forecast_target": target,
        "target_component": (
            frame["segment"] if "segment" in frame else "CONSOLIDATED"
        ),
        "actual_value": frame["target_value"],
        "predicted_value": frame[predicted_column],
        "actual_change": frame["actual_change"],
        "prediction_change": frame.get("selected_change", frame["candidate_prediction"]),
        "research_route_model": frame[route_column],
        "validation": frame["validation"],
        "production_model": "RESEARCH_ONLY_NO_PRODUCTION_ROUTE",
        "production_eligible": False,
    })
    output["absolute_error_change_units"] = (
        output["actual_change"] - output["prediction_change"]
    ).abs()
    output["absolute_target_error"] = (
        output["actual_value"] - output["predicted_value"]
    ).abs()
    return output


def _performance_table(
    revenue_scorecard: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    revenue = revenue_scorecard.loc[
        revenue_scorecard["validation"].eq("TIME_HOLDOUT_PHASE5_ROUTER")
    ]
    for item in revenue.itertuples(index=False):
        rows.append({
            "subindustry": item.subindustry,
            "forecast_target": item.forecast_target,
            "scope": "FROZEN_REVENUE_OR_EBITDA_BENCHMARK",
            "selected_research_route": item.research_route_model,
            "entities": item.tickers,
            "forecasts": item.forecasts,
            "median_time_mase": item.median_ticker_mase,
            "mean_time_mase": item.mean_ticker_mase,
            "level_error_metric": "WAPE_PCT",
            "level_error_value": item.aggregate_wape_pct,
            "gate_status": "FROZEN_NOT_RETESTED",
            "production_eligible": item.forecast_target == "GAAP_REVENUE",
        })
    for item in decisions.itertuples(index=False):
        rows.append({
            "subindustry": item.subindustry,
            "forecast_target": item.forecast_target,
            "scope": item.scope,
            "selected_research_route": item.selected_research_route,
            "entities": item.entities,
            "forecasts": item.forecasts,
            "median_time_mase": item.median_time_mase,
            "mean_time_mase": item.mean_time_mase,
            "level_error_metric": "MAE_TARGET_UNITS",
            "level_error_value": item.mean_target_level_mae,
            "gate_status": "PASS" if item.research_gate else "FAIL",
            "production_eligible": False,
        })
    return pd.DataFrame(rows)


def main() -> None:
    args = _arguments()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    validation_config = config["validation"]
    bridge_config = config["bridge"]

    revenue_freeze_before = freeze_revenue_research_benchmark(ROOT)
    source_manifest = pd.read_csv(KPI_SNAPSHOT / "source_manifest.csv")
    company_panel = pd.read_parquet(P21 / "company_kpi_panel.parquet")
    ep_panel = pd.read_parquet(EP_PANEL)
    artifacts: dict[str, pd.DataFrame] = {}

    hierarchy = load_target_hierarchy(CONFIG)
    artifacts["target_hierarchy.csv"] = hierarchy

    raw_segments, segment_earnings = extract_integrated_segment_earnings(
        source_manifest
    )
    gold_rows, gold_summary = audit_integrated_segment_gold(
        segment_earnings, pd.read_csv(SEGMENT_GOLD)
    )
    parser_gate = bool(gold_summary.iloc[0]["parser_quality_gate"])
    integrated_revenue = load_companyfacts_quarterly_revenue(
        COMPANYFACTS, INTEGRATED_TICKERS
    )
    segment_panel = build_integrated_segment_panel(
        segment_earnings, integrated_revenue, company_panel
    )
    artifacts["integrated_segment_parser_candidates.csv"] = raw_segments
    artifacts["integrated_segment_earnings_quarterly.csv"] = segment_earnings
    artifacts["integrated_segment_gold_audit_rows.csv"] = gold_rows
    artifacts["integrated_segment_gold_audit_summary.csv"] = gold_summary
    artifacts["integrated_segment_target_panel.parquet"] = segment_panel

    integrated_features = {
        segment: tuple(config["integrated"][f"{segment}_features"].split(";"))
        for segment in ("upstream", "downstream", "chemicals")
    }
    expected_integrated = {"upstream": 2, "downstream": 2, "chemicals": 1}
    segment_results: dict[str, TargetValidationResult] = {}
    decisions: list[dict[str, object]] = []
    for segment, features in integrated_features.items():
        result = validate_target_panel(
            segment_panel.loc[segment_panel["segment"].eq(segment)].copy(),
            features,
            parser_quality_gate=parser_gate,
            expected_entities=expected_integrated[segment],
            quarters=int(validation_config["minimum_forecasts_per_entity"]),
            alpha=float(validation_config["ridge_alpha"]),
            minimum_training_observations=int(
                config["integrated"]["minimum_training_observations"]
            ),
            clip_change=float(
                validation_config["margin_change_clip_percentage_points"]
            ),
        )
        segment_results[segment] = result
        _write_result(artifacts, f"integrated_{segment}", result)
        decisions.append(_decision_row(
            subindustry="Integrated",
            target="SEGMENT_EARNINGS_CONTRIBUTION_MARGIN_PCT",
            scope=segment.upper(),
            result=result,
            candidate_route="RIDGE_ECONOMIC_DRIVER_CANDIDATE",
            fallback_route="PRIOR_YEAR_ZERO_CHANGE_BASELINE",
        ))
    passed_segments = [
        segment for segment, result in segment_results.items()
        if bool(result.gate.iloc[0]["research_gate"])
    ]
    selected_segment_time = select_segment_predictions(
        pd.concat(
            [result.time_predictions for result in segment_results.values()],
            ignore_index=True,
            sort=False,
        ),
        passed_segments,
    )
    artifacts["integrated_selected_segment_time_predictions.csv"] = selected_segment_time

    integrated_net_income = extract_integrated_net_income(COMPANYFACTS)
    integrated_bridge, integrated_bridge_summary = (
        build_integrated_consolidated_earnings_bridge(
            selected_segment_time,
            segment_earnings,
            integrated_revenue,
            integrated_net_income,
            trailing_quarters=int(bridge_config["trailing_quarters"]),
            minimum_history=int(bridge_config["minimum_history"]),
            lower_quantile=float(bridge_config["lower_quantile"]),
            base_quantile=float(bridge_config["base_quantile"]),
            upper_quantile=float(bridge_config["upper_quantile"]),
            cutoff_day=int(config["forecast_cutoff_day_of_quarter"]),
        )
    )
    artifacts["integrated_consolidated_earnings_bridge.csv"] = integrated_bridge
    artifacts["integrated_consolidated_earnings_bridge_summary.csv"] = integrated_bridge_summary

    all_operating_tickers = (*EP_TICKERS, *REFINING_TICKERS, *SERVICES_TICKERS)
    operating_income = extract_operating_income(COMPANYFACTS, all_operating_tickers)
    artifacts["operating_income_quarterly.csv"] = operating_income
    target_groups = (
        (
            "ep", "E&P", EP_TICKERS, ep_panel,
            ("wti_log_yoy", "henry_log_yoy", "basket_price_log_yoy"), False,
        ),
        (
            "refining", "Refining", REFINING_TICKERS, company_panel,
            ("product_price_basket_log_yoy", "crack_321_per_bbl_log_yoy", "refinery_crude_input_log_yoy"), False,
        ),
        (
            "services", "Services", SERVICES_TICKERS, company_panel,
            ("wti_log_yoy", "henry_log_yoy", "total_rigs_log_yoy"), True,
        ),
    )
    operating_results: dict[str, TargetValidationResult] = {}
    for prefix, display, tickers, feature_panel, features, direct_gaap_gate in target_groups:
        panel = build_operating_margin_panel(
            operating_income.loc[operating_income["ticker"].isin(tickers)],
            COMPANYFACTS,
            feature_panel,
        )
        artifacts[f"{prefix}_operating_margin_panel.parquet"] = panel
        result = validate_target_panel(
            panel,
            features,
            parser_quality_gate=direct_gaap_gate,
            expected_entities=len(tickers),
            quarters=int(validation_config["minimum_forecasts_per_entity"]),
            alpha=float(validation_config["ridge_alpha"]),
            minimum_training_observations=int(
                validation_config["minimum_training_observations"]
            ),
            clip_change=float(
                validation_config["margin_change_clip_percentage_points"]
            ),
        )
        operating_results[prefix] = result
        _write_result(artifacts, f"{prefix}_operating_margin", result)
        decisions.append(_decision_row(
            subindustry=display,
            target="CONSOLIDATED_OPERATING_MARGIN_PCT",
            scope=(
                f"{int(result.gate.iloc[0]['evaluable_entities'])}_OF_"
                f"{len(tickers)}_STANDARDIZED_GAAP_TAG_COVERAGE"
            ),
            result=result,
            candidate_route="RIDGE_ECONOMIC_DRIVER_CANDIDATE",
            fallback_route="PRIOR_YEAR_ZERO_CHANGE_BASELINE",
        ))

    capex, capex_coverage = extract_ep_cash_capex(COMPANYFACTS)
    capex_panel = build_capex_panel(capex, ep_panel)
    capex_result = validate_target_panel(
        capex_panel,
        ("wti_log_yoy", "henry_log_yoy", "basket_price_log_yoy"),
        parser_quality_gate=False,
        expected_entities=len(EP_TICKERS),
        quarters=int(validation_config["minimum_forecasts_per_entity"]),
        alpha=float(validation_config["ridge_alpha"]),
        minimum_training_observations=int(
            validation_config["minimum_training_observations"]
        ),
        clip_change=float(validation_config["log_change_clip_points"]),
    )
    artifacts["ep_cash_capex_quarterly.csv"] = capex
    artifacts["ep_cash_capex_coverage.csv"] = capex_coverage
    artifacts["ep_cash_capex_panel.parquet"] = capex_panel
    _write_result(artifacts, "ep_cash_capex", capex_result)
    decisions.append(_decision_row(
        subindustry="E&P",
        target="CASH_CAPEX",
        scope="13_OF_14_TICKERS_HETEROGENEOUS_GAAP_TAGS",
        result=capex_result,
        candidate_route="RIDGE_ECONOMIC_DRIVER_CANDIDATE",
        fallback_route="PRIOR_YEAR_ZERO_CHANGE_BASELINE",
    ))

    phase5_common_time = pd.read_csv(
        PHASE25 / "phase5_common_forecast_schema_time.csv"
    )
    ebitda_quarterly = pd.read_csv(
        PHASE25 / "midstream_adjusted_ebitda_quarterly.csv"
    )
    midstream_bridge, midstream_bridge_summary = build_midstream_ebitda_revenue_bridge(
        phase5_common_time,
        ebitda_quarterly,
        COMPANYFACTS,
        trailing_quarters=int(bridge_config["trailing_quarters"]),
        minimum_history=int(bridge_config["minimum_history"]),
        lower_quantile=float(bridge_config["lower_quantile"]),
        base_quantile=float(bridge_config["base_quantile"]),
        upper_quantile=float(bridge_config["upper_quantile"]),
        cutoff_day=int(config["forecast_cutoff_day_of_quarter"]),
    )
    artifacts["midstream_ebitda_to_revenue_bridge.csv"] = midstream_bridge
    artifacts["midstream_ebitda_to_revenue_bridge_summary.csv"] = midstream_bridge_summary

    decisions_frame = pd.DataFrame(decisions)
    artifacts["target_research_decisions.csv"] = decisions_frame
    target_router = decisions_frame[[
        "subindustry", "forecast_target", "scope", "selected_research_route",
        "research_gate", "production_eligible",
    ]].copy()
    target_router["router_role"] = "STATIC_TARGET_DISPATCH_NO_META_MODEL"
    artifacts["phase6_target_router.csv"] = target_router

    common_targets = [
        phase5_common_time.assign(
            target_component="CONSOLIDATED",
            actual_change=phase5_common_time["actual_log_yoy"],
            prediction_change=phase5_common_time["prediction_log_yoy"],
            absolute_error_change_units=phase5_common_time["absolute_error_log_points"],
            absolute_target_error=(phase5_common_time["actual_value"] - phase5_common_time["predicted_value"]).abs(),
            production_eligible=phase5_common_time["forecast_target"].eq("GAAP_REVENUE"),
        )[[
            "ticker", "quarter", "subindustry", "forecast_target", "target_component", "actual_value",
            "predicted_value", "actual_change", "prediction_change", "research_route_model",
            "validation", "production_model", "production_eligible",
            "absolute_error_change_units", "absolute_target_error",
        ]],
        _common_target_rows(
            selected_segment_time,
            subindustry="Integrated",
            target="SEGMENT_EARNINGS_CONTRIBUTION_MARGIN_PCT",
            route_column="selected_route",
            predicted_column="selected_target_value",
        ),
    ]
    for prefix, display, *_ in target_groups:
        common_targets.append(_common_target_rows(
            operating_results[prefix].time_predictions.assign(
                selected_route="RIDGE_ECONOMIC_DRIVER_CANDIDATE"
                if bool(operating_results[prefix].gate.iloc[0]["research_gate"])
                else "PRIOR_YEAR_ZERO_CHANGE_BASELINE",
                selected_target_value=np.where(
                    bool(operating_results[prefix].gate.iloc[0]["research_gate"]),
                    operating_results[prefix].time_predictions["candidate_target_value"],
                    operating_results[prefix].time_predictions["prior_year_target_value"],
                ),
                selected_change=np.where(
                    bool(operating_results[prefix].gate.iloc[0]["research_gate"]),
                    operating_results[prefix].time_predictions["candidate_prediction"], 0.0,
                ),
            ),
            subindustry=display,
            target="CONSOLIDATED_OPERATING_MARGIN_PCT",
            route_column="selected_route",
            predicted_column="selected_target_value",
        ))
    common_targets.append(_common_target_rows(
        capex_result.time_predictions.assign(
            selected_route="PRIOR_YEAR_ZERO_CHANGE_BASELINE",
            selected_target_value=capex_result.time_predictions["prior_year_target_value"],
            selected_change=0.0,
        ),
        subindustry="E&P",
        target="CASH_CAPEX",
        route_column="selected_route",
        predicted_column="selected_target_value",
    ))
    artifacts["phase6_common_target_forecasts.csv"] = pd.concat(
        common_targets, ignore_index=True, sort=False
    )

    revenue_scorecard = pd.read_csv(PHASE25 / "phase5_sector_scorecard.csv")
    performance = _performance_table(revenue_scorecard, decisions_frame)
    artifacts["forecast_performance_summary.csv"] = performance

    all_tickers = tuple(sorted(set(
        (*EP_TICKERS, *INTEGRATED_TICKERS, *REFINING_TICKERS, *SERVICES_TICKERS)
    )))
    consensus_raw, finnworlds = load_arcana_consensus(CONSENSUS, all_tickers)
    consensus_pit = point_in_time_consensus(
        consensus_raw, int(config["forecast_cutoff_day_of_quarter"])
    )
    revenue_model = phase5_common_time.loc[
        phase5_common_time["forecast_target"].eq("GAAP_REVENUE")
    ].rename(columns={
        "predicted_value": "predicted_revenue",
        "actual_value": "actual_revenue",
    })
    consensus_backtest, consensus_summary = evaluate_model_vs_consensus(
        revenue_model, consensus_pit, minimum_observations=20
    )
    artifacts["analyst_consensus_normalized.csv"] = consensus_raw
    artifacts["analyst_consensus_pit.csv"] = consensus_pit
    artifacts["analyst_consensus_finnworlds_coverage.csv"] = finnworlds
    artifacts["model_vs_consensus_backtest.csv"] = consensus_backtest
    artifacts["model_vs_consensus_summary.csv"] = consensus_summary
    artifacts["current_model_vs_consensus.csv"] = pd.read_csv(
        ROOT / "output" / "v3_4" / "current_model_vs_consensus.csv"
    )

    for name, frame in artifacts.items():
        path = output / name
        if path.suffix == ".parquet":
            frame.to_parquet(path, index=False)
        else:
            frame.to_csv(path, index=False)

    revenue_freeze_after = verify_revenue_research_benchmark(ROOT)
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform_name": config["platform_name"],
        "research_only": True,
        "revenue_models_frozen": True,
        "revenue_benchmark_manifest": revenue_freeze_after["manifest_path"],
        "revenue_benchmark_manifest_sha256": revenue_freeze_after["manifest_sha256"],
        "revenue_benchmark_files_verified_before": revenue_freeze_before["verified_files"],
        "revenue_benchmark_files_verified_after": revenue_freeze_after["verified_files"],
        "production_champion_changed": False,
        "live_matched_observations": "0/20",
        "integrated_parser_gate": parser_gate,
        "integrated_segment_rows": len(segment_earnings),
        "integrated_passed_segments": passed_segments,
        "integrated_consolidated_revenue_improvement_allowed": False,
        "fixed_ratio_reverse_calculation_used": False,
        "scenario_bridges_required": True,
        "consensus_providers": ["ALPHA_VANTAGE", "FMP", "FINNWORLDS"],
        "finnworlds_revenue_consensus_status": "RATINGS_ONLY_NOT_USED",
        "consensus_backtest_status": str(consensus_summary.iloc[0]["status"]),
        "config_sha256": _sha256(CONFIG),
        "integrated_gold_sha256": _sha256(SEGMENT_GOLD),
        "target_sources": {
            "operating_income": target_source_metadata(operating_income),
            "cash_capex": target_source_metadata(capex),
            "integrated_net_income": target_source_metadata(integrated_net_income),
        },
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    report = f"""# Phase 6 — Subindustry Driver Forecast → Financial Bridge → Valuation

## Decision

- Revenue routes are frozen by `{revenue_freeze_after['manifest_path']}` and verified before and after this run.
- Production remains V3.4; live changes remain 0/20.
- Integrated consolidated-revenue improvement is stopped. Segment earnings are the primary anchor.
- No bridge uses a fixed margin or fixed ratio. Every available bridge uses PIT trailing distributions and reports scenarios plus anchor/bridge error attribution.

## Target hierarchy

{_markdown(hierarchy)}

## Forecast performance

Margin targets use percentage-point MAE as the interpretable level metric. WAPE on signed margins is retained in detailed diagnostics only.

{_markdown(performance)}

## Integrated segment decisions

{_markdown(decisions_frame.loc[decisions_frame['subindustry'].eq('Integrated')])}

The parser gold audit covers {int(gold_summary.iloc[0]['gold_rows'])} rows with {gold_summary.iloc[0]['all_dimension_accuracy']:.1%} all-dimension accuracy. Only `{';'.join(passed_segments) or 'NONE'}` passes the strict TIME gate. Failed segments use the prior-year zero-change baseline and are not promoted to production.

## Conditional bridge performance

{_markdown(pd.concat([integrated_bridge_summary, midstream_bridge_summary], ignore_index=True, sort=False))}

Integrated segment disclosures are GAAP segment earnings, not EBIT. The current bridge therefore targets consolidated net-income margin. EBIT/FCFF remains locked until corporate/unmodeled, tax, D&A, working-capital, and CapEx semantics are standardized.

## Analyst consensus

Arcana Alpha Vantage and FMP revenue estimates are normalized with release-date cutoffs. Finnworlds is inventoried but excluded from revenue consensus because the available local dataset contains ratings only.

{_markdown(consensus_summary)}

Current forward model-versus-consensus spreads remain in `current_model_vs_consensus.csv`; a historical performance claim stays locked until at least 20 matched PIT observations exist.
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
