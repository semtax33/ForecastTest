from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.core.activity import (
    load_rig_snapshot,
    refresh_rig_snapshot,
    rig_features_for_quarters,
)
from energy_nowcast.core.coverage import macro_overlay_status, operational_kpi_coverage
from energy_nowcast.core.consensus_audit import (
    consensus_cutoff_audit,
    latest_consensus_snapshot,
)
from energy_nowcast.core.platform import (
    build_latest_unobserved_nowcasts,
    build_structural_panel,
    validate_subindustry,
)
from energy_nowcast.core.steo import (
    load_steo_vintages,
    quarterly_vintage_features,
    refresh_steo_vintages,
    select_point_in_time_features,
)
from energy_nowcast.core.taxonomy import (
    SUBINDUSTRY_TICKERS,
    all_phase_tickers,
    phase_for_subindustry,
)
from energy_nowcast.data.consensus import (
    evaluate_model_vs_consensus,
    load_arcana_consensus,
    point_in_time_consensus,
)
from energy_nowcast.data.cutoff import quarter_cutoff_date
from energy_nowcast.operations.champion import sha256_file, verify_champion
from energy_nowcast.research.v36.benchmark import verify_research_champion
from energy_nowcast.validation.cross_section_metrics import ticker_scorecard, universe_summary


from equity_platform.data_catalog import DATA
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
OUTPUT = ROOT / "output" / "phase2_4_structural_research"
STEO_SNAPSHOT = DATA.steo_snapshot
RIG_SNAPSHOT = DATA.rig_snapshot
COMPANYFACTS = (
    ROOT.parent / "Arcana" / "data-lake" / "bronze" / "sec" / "companyfacts"
)
CONSENSUS = ROOT.parent / "Arcana" / "data-lake" / "bronze" / "consensus"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 2-4 structural research")
    parser.add_argument(
        "--refresh-free-data",
        action="store_true",
        help="Refresh free EIA STEO vintages and EIA/Baker Hughes rig history",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        values = ["" if pd.isna(row[column]) else str(row[column]) for column in columns]
        lines.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
    return "\n".join(lines)


def _phase_summaries(
    time_predictions: pd.DataFrame,
    loco_predictions: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for phase in (2, 3, 4):
        for validation, predictions in (
            ("TIME", time_predictions), ("LOCO", loco_predictions)
        ):
            selected = predictions.loc[predictions["phase"].eq(phase)].copy()
            score = ticker_scorecard(selected, minimum_observations=8)
            summary = universe_summary(
                score, selected, f"PHASE_{phase}_{validation}_8Q"
            )
            summary.insert(0, "phase", phase)
            rows.append(summary)
    return pd.concat(rows, ignore_index=True)


def _model_vs_consensus(
    nowcasts: pd.DataFrame,
    consensus: pd.DataFrame,
    day_of_quarter: int,
    eligible: bool,
) -> pd.DataFrame:
    model_columns = [
        "phase", "subindustry", "ticker", "quarter", "candidate_revenue",
        "selected_revenue", "selected_model",
    ]
    model = nowcasts[model_columns].copy()
    model["forecast_cutoff_date"] = model["quarter"].map(
        lambda quarter: quarter_cutoff_date(quarter, day_of_quarter)
    )
    consensus_columns = [
        "ticker", "quarter", "snapshot_date", "consensus_revenue",
        "consensus_revenue_low", "consensus_revenue_high", "analyst_count",
        "provider_count", "providers",
    ]
    normalized = consensus.copy()
    for column in consensus_columns:
        if column not in normalized:
            normalized[column] = np.nan
    comparison = model.merge(
        normalized[consensus_columns], on=["ticker", "quarter"], how="left"
    )
    comparison["snapshot_date"] = pd.to_datetime(
        comparison["snapshot_date"], errors="coerce"
    )
    comparison["snapshot_after_cutoff"] = (
        comparison["snapshot_date"].notna()
        & comparison["snapshot_date"].gt(comparison["forecast_cutoff_date"])
    )
    comparison["candidate_minus_consensus"] = (
        comparison["candidate_revenue"] - comparison["consensus_revenue"]
    )
    comparison["candidate_minus_consensus_pct"] = (
        comparison["candidate_minus_consensus"]
        / comparison["consensus_revenue"]
        * 100.0
    )
    if eligible:
        comparison["comparison_status"] = np.where(
            comparison["consensus_revenue"].notna(),
            "POINT_IN_TIME_ELIGIBLE",
            "NO_PRE_CUTOFF_REVENUE_CONSENSUS",
        )
    else:
        comparison["comparison_status"] = np.where(
            comparison["consensus_revenue"].notna(),
            "POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION",
            "NO_REVENUE_CONSENSUS_SNAPSHOT",
        )
    return comparison.sort_values(["phase", "subindustry", "ticker"]).reset_index(
        drop=True
    )


def _write_report(
    output: Path,
    summaries: pd.DataFrame,
    gates: pd.DataFrame,
    nowcasts: pd.DataFrame,
    consensus_performance: pd.DataFrame,
    consensus_diagnostic: pd.DataFrame,
    kpi_coverage: pd.DataFrame,
) -> None:
    time = summaries.loc[summaries["validation"].str.startswith("TIME")]
    metrics = time[[
        "subindustry", "median_ticker_mase", "mean_ticker_mase",
        "legacy_no_regression_share", "mean_pi_80_coverage",
        "mean_directional_hit_rate", "overall_revenue_wape_pct",
        "overall_revenue_median_ape_pct",
    ]].round(4)
    gate_view = gates[[
        "phase", "subindustry", "minimum_8_forecasts_per_ticker",
        "median_time_mase_below_0_80", "mean_time_mase_below_0_90",
        "baseline_no_regression_at_least_80pct", "severe_regression_count_zero",
        "pi80_between_75_85pct", "directional_hit_at_least_65pct", "research_gate",
    ]]
    prediction_view = nowcasts[[
        "phase", "subindustry", "ticker", "quarter", "issue", "available_at",
        "raw_structural_prediction", "structural_shrinkage_weight",
        "candidate_prediction", "candidate_revenue", "legacy_prediction",
        "selected_model", "selected_prediction", "selected_revenue",
    ]].copy()
    for column in (
        "candidate_revenue", "selected_revenue"
    ):
        prediction_view[column] = prediction_view[column] / 1_000_000_000.0
    prediction_view = prediction_view.rename(columns={
        "candidate_revenue": "candidate_revenue_usd_bn",
        "selected_revenue": "selected_revenue_usd_bn",
    }).round(4)
    consensus_view = consensus_diagnostic[[
        "ticker", "quarter", "candidate_revenue", "consensus_revenue",
        "candidate_minus_consensus_pct", "providers", "snapshot_date",
        "comparison_status",
    ]].copy()
    for column in ("candidate_revenue", "consensus_revenue"):
        consensus_view[column] = consensus_view[column] / 1_000_000_000.0
    consensus_view = consensus_view.rename(columns={
        "candidate_revenue": "candidate_revenue_usd_bn",
        "consensus_revenue": "consensus_revenue_usd_bn",
    }).round(4)
    coverage_view = kpi_coverage[[
        "subindustry", "ticker", "primary_operating_driver", "active_proxy",
        "proxy_scope", "configuration_status",
    ]]
    lines = [
        "# Energy platform Phase 2-4 structural research",
        "",
        "Phase 2 keeps Integrated and Refining as separate economic models. Phase 3",
        "uses contract-aware midstream volume/fee drivers. Phase 4 uses OFS activity",
        "and CapEx/pricing signals. TIME is primary; LOCO is a cold-start diagnostic.",
        "",
        "No paid CME, CMA, or CME DataMine data is used. Product-price and throughput",
        "forecasts come from point-in-time EIA STEO archives; rig history is the free",
        "EIA republication of Baker Hughes data.",
        "",
        "## TIME performance",
        "",
        _markdown_table(metrics),
        "",
        "## Strict research gates",
        "",
        _markdown_table(gate_view),
        "",
        "## Latest unobserved local-SEC-snapshot predictions",
        "",
        _markdown_table(prediction_view),
        "",
        "## Analyst consensus audit",
        "",
        "Arcana Alpha Vantage and FMP revenue estimates are included only when their",
        "snapshot date passes the same release-date cutoff. Finnworlds is recorded as",
        "ratings-only coverage and is never treated as revenue consensus.",
        "",
        _markdown_table(consensus_performance.round(4)),
        "",
        "The current Arcana snapshots are after the 2026Q2 cutoff, so this next table",
        "is diagnostic only and cannot enter backtests, gates, or promotion decisions.",
        "",
        _markdown_table(consensus_view),
        "",
        "## Operating KPI and proxy coverage",
        "",
        _markdown_table(coverage_view),
        "",
        "A failed research gate retains the lag-revenue baseline as the selected model.",
        "V3.4 remains the frozen production champion and live promotion remains 0/20.",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "configs" / "phase2_4_structural_research.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    v34_before = verify_champion(ROOT, "3.4")
    v353_before = verify_research_champion(ROOT, "3.5.3")
    if args.refresh_free_data:
        refresh_steo_vintages(STEO_SNAPSHOT, 2019, datetime.now().year)
        refresh_rig_snapshot(RIG_SNAPSHOT)

    monthly = load_steo_vintages(STEO_SNAPSHOT)
    quarterly = quarterly_vintage_features(monthly)
    target_quarters = [
        str(period)
        for period in pd.period_range("2019Q1", "2026Q3", freq="Q")
    ]
    steo_pit = select_point_in_time_features(
        quarterly, target_quarters, int(config["forecast_cutoff_day_of_quarter"])
    )
    rig_pit = rig_features_for_quarters(
        load_rig_snapshot(RIG_SNAPSHOT),
        target_quarters,
        int(config["forecast_cutoff_day_of_quarter"]),
    )
    panel, audit = build_structural_panel(
        COMPANYFACTS,
        steo_pit,
        rig_pit,
        all_phase_tickers(),
        int(config["forecast_cutoff_day_of_quarter"]),
    )

    time_predictions: list[pd.DataFrame] = []
    loco_predictions: list[pd.DataFrame] = []
    time_scores: list[pd.DataFrame] = []
    loco_scores: list[pd.DataFrame] = []
    summaries: list[pd.DataFrame] = []
    gates: list[pd.DataFrame] = []
    for subindustry in SUBINDUSTRY_TICKERS:
        result = validate_subindustry(
            panel, subindustry, int(config["time_holdout_quarters"])
        )
        for frame in (result.time_scorecard, result.loco_scorecard, result.summary):
            frame.insert(0, "subindustry", subindustry)
            frame.insert(0, "phase", phase_for_subindustry(subindustry))
        time_predictions.append(result.time_predictions)
        loco_predictions.append(result.loco_predictions)
        time_scores.append(result.time_scorecard)
        loco_scores.append(result.loco_scorecard)
        summaries.append(result.summary)
        gates.append(result.gate)
    time_frame = _concat(time_predictions)
    loco_frame = _concat(loco_predictions)
    summary_frame = _concat(summaries)
    gate_frame = _concat(gates)

    nowcasts = build_latest_unobserved_nowcasts(
        audit,
        steo_pit,
        rig_pit,
        panel,
        int(config["forecast_cutoff_day_of_quarter"]),
    )
    gate_lookup = gate_frame.set_index("subindustry")["research_gate"].to_dict()
    nowcasts["research_gate"] = nowcasts["subindustry"].map(gate_lookup).fillna(False)
    nowcasts["selected_model"] = np.where(
        nowcasts["research_gate"],
        nowcasts["structural_model"],
        "LAG_REVENUE_BASELINE",
    )
    nowcasts["selected_prediction"] = np.where(
        nowcasts["research_gate"],
        nowcasts["candidate_prediction"],
        nowcasts["legacy_prediction"],
    )
    nowcasts["selected_revenue"] = np.where(
        nowcasts["research_gate"],
        nowcasts["candidate_revenue"],
        nowcasts["baseline_revenue"],
    )

    consensus_rows, finnworlds_coverage = load_arcana_consensus(
        CONSENSUS, all_phase_tickers()
    )
    consensus_pit = point_in_time_consensus(
        consensus_rows, int(config["forecast_cutoff_day_of_quarter"])
    )
    consensus_latest = latest_consensus_snapshot(consensus_rows)
    consensus_audit = consensus_cutoff_audit(
        consensus_rows,
        nowcasts[["ticker", "quarter"]],
        int(config["forecast_cutoff_day_of_quarter"]),
    )
    pit_comparison = _model_vs_consensus(
        nowcasts,
        consensus_pit,
        int(config["forecast_cutoff_day_of_quarter"]),
        eligible=True,
    )
    diagnostic_comparison = _model_vs_consensus(
        nowcasts,
        consensus_latest,
        int(config["forecast_cutoff_day_of_quarter"]),
        eligible=False,
    )
    consensus_backtest = time_frame.rename(columns={
        "candidate_revenue": "predicted_revenue",
        "revenue": "actual_revenue",
    })
    consensus_performance_rows, consensus_performance_summary = (
        evaluate_model_vs_consensus(consensus_backtest, consensus_pit)
    )
    kpi_coverage = operational_kpi_coverage()
    overlay_status = macro_overlay_status(gate_frame)

    source_manifest = pd.read_csv(STEO_SNAPSHOT / "source_manifest.csv")
    forbidden = tuple(value.lower() for value in config["free_data_policy"]["forbidden_sources"])
    urls = " ".join(source_manifest["source_url"].astype(str)).lower()
    if any(source.lower() in urls for source in forbidden):
        raise AssertionError("Forbidden paid source found in source manifest")
    if bool(config["free_data_policy"]["paid_market_data_used"]):
        raise AssertionError("Paid market data must remain disabled")

    phase_summary = _phase_summaries(time_frame, loco_frame)
    artifacts = {
        "revenue_label_audit.csv": audit,
        "steo_point_in_time_quarterly.csv": steo_pit,
        "rig_point_in_time_quarterly.csv": rig_pit,
        "structural_panel.csv": panel,
        "time_predictions.csv": time_frame,
        "loco_predictions.csv": loco_frame,
        "time_scorecards.csv": _concat(time_scores),
        "loco_scorecards.csv": _concat(loco_scores),
        "subindustry_summary.csv": summary_frame,
        "phase_summary.csv": phase_summary,
        "research_gates.csv": gate_frame,
        "latest_unobserved_predictions.csv": nowcasts,
        "free_source_manifest.csv": source_manifest,
        "consensus_normalized_rows.csv": consensus_rows,
        "consensus_cutoff_audit.csv": consensus_audit,
        "finnworlds_consensus_coverage.csv": finnworlds_coverage,
        "model_vs_consensus_point_in_time.csv": pit_comparison,
        "model_vs_consensus_post_cutoff_diagnostic.csv": diagnostic_comparison,
        "model_vs_consensus_backtest_rows.csv": consensus_performance_rows,
        "model_vs_consensus_performance.csv": consensus_performance_summary,
        "operational_kpi_coverage.csv": kpi_coverage,
        "macro_overlay_status.csv": overlay_status,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(output / filename, index=False)
    panel.to_parquet(output / "structural_panel.parquet", index=False)
    _write_report(
        output,
        summary_frame,
        gate_frame,
        nowcasts,
        consensus_performance_summary,
        diagnostic_comparison,
        kpi_coverage,
    )

    v34_after = verify_champion(ROOT, "3.4")
    v353_after = verify_research_champion(ROOT, "3.5.3")
    if v34_before["manifest_sha256"] != v34_after["manifest_sha256"]:
        raise RuntimeError("V3.4 changed during Phase 2-4 research")
    if v353_before["manifest_sha256"] != v353_after["manifest_sha256"]:
        raise RuntimeError("V3.5.3 changed during Phase 2-4 research")
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "paid_market_data_used": False,
        "cme_used": False,
        "cma_used": False,
        "source_policy": (
            "FREE_EIA_STEO_SEC_COMPANYFACTS_EIA_RIGS_PLUS_"
            "ARCANA_ALPHA_VANTAGE_FMP_FINNWORLDS_CONSENSUS"
        ),
        "consensus_revenue_providers": ["ALPHA_VANTAGE", "FMP"],
        "finnworlds_consensus_role": "RATINGS_ONLY_NOT_REVENUE_CONSENSUS",
        "consensus_point_in_time_matched_observations": int(
            consensus_performance_summary.loc[0, "observations"]
        ),
        "consensus_performance_status": consensus_performance_summary.loc[0, "status"],
        "post_cutoff_consensus_used_for_backtest_or_promotion": False,
        "company_operating_kpis_parsed": False,
        "operating_proxy_disclosure_artifact": "operational_kpi_coverage.csv",
        "macro_residual_overlay_enabled": False,
        "latest_prediction_quarter": sorted(nowcasts["quarter"].unique().tolist()),
        "subindustry_research_gate": {
            row["subindustry"]: bool(row["research_gate"])
            for _, row in gate_frame.iterrows()
        },
        "production_champion": "V3.4_FROZEN",
        "production_champion_changed": False,
        "v3_4_manifest_sha256": v34_after["manifest_sha256"],
        "ep_research_champion": "V3.5.3_FROZEN",
        "v3_5_3_manifest_sha256": v353_after["manifest_sha256"],
        "live_matched_observations": "0/20",
        "config_sha256": sha256_file(config_path),
        "steo_snapshot_sha256": sha256_file(
            STEO_SNAPSHOT / "steo_monthly_vintages.csv"
        ),
        "rig_snapshot_sha256": sha256_file(RIG_SNAPSHOT / "rig_monthly.csv"),
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(summary_frame.loc[
        summary_frame["validation"].str.startswith("TIME"), [
            "phase", "subindustry", "median_ticker_mase", "mean_ticker_mase",
            "legacy_no_regression_share", "mean_pi_80_coverage",
            "mean_directional_hit_rate", "overall_revenue_wape_pct",
        ]
    ].round(4).to_string(index=False))
    print("\nGates\n", gate_frame[[
        "phase", "subindustry", "research_gate"
    ]].to_string(index=False))
    print("\nLatest predictions\n", nowcasts[[
        "subindustry", "ticker", "quarter", "candidate_prediction",
        "candidate_revenue", "selected_model", "selected_prediction",
    ]].round(4).to_string(index=False))
    print(f"\nV3.4 unchanged: {v34_after['manifest_sha256']}")
    print(f"V3.5.3 unchanged: {v353_after['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
