from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib

import numpy as np
import pandas as pd

from energy_nowcast.core.calibration import interval_score
from energy_nowcast.core.company_kpi import (
    load_company_kpis,
    refresh_company_kpi_snapshot,
    requested_kpi_coverage,
    select_company_kpis_for_targets,
)
from energy_nowcast.core.company_kpi_platform import (
    build_company_kpi_panel,
    build_latest_company_kpi_nowcasts,
    build_latest_proxy_recalibrated_nowcasts,
    validate_company_kpi_subindustry,
)
from energy_nowcast.core.consensus_audit import latest_consensus_snapshot
from energy_nowcast.core.proxy_benchmark import verify_proxy_benchmark
from energy_nowcast.core.taxonomy import SUBINDUSTRY_TICKERS, all_phase_tickers
from energy_nowcast.data.consensus import (
    evaluate_model_vs_consensus,
    load_arcana_consensus,
    point_in_time_consensus,
)
from energy_nowcast.operations.champion import sha256_file, verify_champion
from energy_nowcast.research.v36.benchmark import verify_research_champion


ROOT = Path(__file__).resolve().parent
PROXY_OUTPUT = ROOT / "output" / "phase2_4_structural_research"
OUTPUT = ROOT / "output" / "phase2_4_company_kpi_research"
KPI_SNAPSHOT = ROOT / "data-lake" / "phase2_4_company_kpi_snapshot"
PARSER_AUDIT_OUTPUT = ROOT / "output" / "kpi_parser_gold_audit"
CONSENSUS = ROOT.parent / "Arcana" / "data-lake" / "bronze" / "consensus"
CONFIG = ROOT / "configs" / "phase2_4_company_kpi_research.toml"


def _load_parser_quality_gates() -> tuple[pd.DataFrame, str]:
    gate_path = PARSER_AUDIT_OUTPUT / "parser_quality_gate.csv"
    metadata_path = PARSER_AUDIT_OUTPUT / "metadata.json"
    fallback = pd.DataFrame(
        {
            "subindustry": list(SUBINDUSTRY_TICKERS),
            "gold_rows": 0,
            "parser_quality_gate": False,
            "post_numeric_accuracy": np.nan,
            "post_unit_accuracy": np.nan,
            "post_period_accuracy": np.nan,
            "post_semantic_accuracy": np.nan,
        }
    )
    if not gate_path.exists() or not metadata_path.exists():
        return fallback, "MISSING_FAIL_CLOSED"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_snapshot = metadata.get("post_snapshot_sha256")
    actual_snapshot = sha256_file(KPI_SNAPSHOT / "company_kpi_quarterly.csv")
    if expected_snapshot != actual_snapshot:
        return fallback, "STALE_SNAPSHOT_FAIL_CLOSED"
    gates = pd.read_csv(gate_path)
    if set(gates["subindustry"]) != set(SUBINDUSTRY_TICKERS):
        return fallback, "INCOMPLETE_FAIL_CLOSED"
    return gates, "CURRENT"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 2-4 company-KPI research")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--refresh-company-kpis", action="store_true")
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


def _add_labels(frame: pd.DataFrame, experiment: str, subindustry: str) -> pd.DataFrame:
    result = frame.copy()
    result.insert(0, "experiment", experiment)
    if "subindustry" in result:
        result["subindustry"] = subindustry
    else:
        result.insert(1, "subindustry", subindustry)
    return result


def _benchmark_comparison(
    candidate: pd.DataFrame,
    benchmark: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    left = candidate[[
        "ticker", "quarter", "subindustry", "actual_log_yoy", "candidate_prediction"
    ]].rename(columns={"candidate_prediction": "company_kpi_prediction"})
    right = benchmark[["ticker", "quarter", "candidate_prediction"]].rename(
        columns={"candidate_prediction": "proxy_prediction"}
    )
    rows = left.merge(right, on=["ticker", "quarter"], how="inner")
    rows["company_kpi_absolute_error"] = (
        rows["actual_log_yoy"] - rows["company_kpi_prediction"]
    ).abs()
    rows["proxy_absolute_error"] = (
        rows["actual_log_yoy"] - rows["proxy_prediction"]
    ).abs()
    rows["company_kpi_minus_proxy_absolute_error"] = (
        rows["company_kpi_absolute_error"] - rows["proxy_absolute_error"]
    )
    rows["company_kpi_wins"] = rows["company_kpi_absolute_error"].lt(
        rows["proxy_absolute_error"]
    )
    ticker = (
        rows.groupby(["subindustry", "ticker"], as_index=False)
        .agg(
            observations=("quarter", "count"),
            company_kpi_mae=("company_kpi_absolute_error", "mean"),
            proxy_mae=("proxy_absolute_error", "mean"),
            company_kpi_win_rate=("company_kpi_wins", "mean"),
        )
    )
    ticker["company_kpi_improvement_log_points"] = (
        ticker["proxy_mae"] - ticker["company_kpi_mae"]
    )
    summary = (
        ticker.groupby("subindustry", as_index=False)
        .agg(
            ticker_count=("ticker", "count"),
            benchmark_no_regression_share=(
                "company_kpi_improvement_log_points",
                lambda values: values.ge(0.0).mean(),
            ),
            benchmark_severe_regression_count=(
                "company_kpi_improvement_log_points",
                lambda values: values.lt(-2.0).sum(),
            ),
            median_company_kpi_improvement_log_points=(
                "company_kpi_improvement_log_points",
                "median",
            ),
            mean_company_kpi_win_rate=("company_kpi_win_rate", "mean"),
        )
    )
    return rows, ticker.merge(summary, on="subindustry", how="left")


def _original_interval_summary() -> pd.DataFrame:
    predictions = pd.read_csv(PROXY_OUTPUT / "time_predictions.csv")
    rows: list[dict[str, object]] = []
    for subindustry, group in predictions.groupby("subindustry"):
        output: dict[str, object] = {"subindustry": subindustry}
        for level in (0.80, 0.95):
            label = int(level * 100)
            lower = pd.to_numeric(group[f"lower_{label}_log_yoy"], errors="coerce")
            upper = pd.to_numeric(group[f"upper_{label}_log_yoy"], errors="coerce")
            actual = pd.to_numeric(group["actual_log_yoy"], errors="coerce")
            output[f"original_pi_{label}_coverage"] = float(
                group[f"covered_{label}"].astype(str).str.lower().eq("true").mean()
            )
            output[f"original_interval_{label}_width"] = float((upper - lower).mean())
            output[f"original_interval_{label}_score"] = float(
                np.nanmean(
                    [
                        interval_score(y, lo, hi, level)
                        for y, lo, hi in zip(actual, lower, upper)
                    ]
                )
            )
        rows.append(output)
    return pd.DataFrame(rows)


def _integrated_ablation_summary(panel: pd.DataFrame) -> pd.DataFrame:
    columns = {
        "UPSTREAM_ONLY": ["upstream_company_kpi_effect_log_points"],
        "DOWNSTREAM_ONLY": ["downstream_company_kpi_effect_log_points"],
        "CHEMICALS_ONLY": ["chemicals_company_kpi_effect_log_points"],
        "ALL_COMPANY_KPIS": [
            "upstream_company_kpi_effect_log_points",
            "downstream_company_kpi_effect_log_points",
            "chemicals_company_kpi_effect_log_points",
        ],
    }
    rows: list[dict[str, object]] = []
    for variant, effects in columns.items():
        candidate = panel.copy()
        candidate["raw_structural_prediction"] = (
            candidate["benchmark_raw_structural_prediction"]
            + candidate[effects].fillna(0.0).sum(axis=1)
        )
        result = validate_company_kpi_subindustry(candidate, "integrated", 8)
        summary = result.summary.loc[
            result.summary["validation"].str.startswith("TIME")
        ].iloc[0]
        rows.append({
            "subindustry": "integrated",
            "variant": variant,
            "median_ticker_mase": summary["median_ticker_mase"],
            "mean_ticker_mase": summary["mean_ticker_mase"],
            "overall_revenue_wape_pct": summary["overall_revenue_wape_pct"],
            "mean_directional_hit_rate": summary["mean_directional_hit_rate"],
            "point_model_gate": bool(result.gates.loc[0, "point_model_gate"]),
        })
    return pd.DataFrame(rows)


def _consensus_comparison(
    nowcasts: pd.DataFrame,
    consensus: pd.DataFrame,
    status_when_matched: str,
) -> pd.DataFrame:
    columns = [
        "ticker", "quarter", "snapshot_date", "consensus_revenue", "provider_count", "providers"
    ]
    source = consensus.copy()
    for column in columns:
        if column not in source:
            source[column] = np.nan
    result = nowcasts[[
        "phase", "subindustry", "ticker", "quarter", "forecast_cutoff_date",
        "candidate_revenue", "selected_revenue",
    ]].merge(source[columns], on=["ticker", "quarter"], how="left")
    result["snapshot_date"] = pd.to_datetime(result["snapshot_date"], errors="coerce")
    result["snapshot_after_cutoff"] = result["snapshot_date"].gt(
        pd.to_datetime(result["forecast_cutoff_date"])
    )
    result["candidate_minus_consensus_pct"] = (
        result["candidate_revenue"] / result["consensus_revenue"] - 1.0
    ) * 100.0
    result["comparison_status"] = np.where(
        result["consensus_revenue"].notna(),
        status_when_matched,
        "NO_ELIGIBLE_REVENUE_CONSENSUS",
    )
    return result


def _write_report(
    output: Path,
    comparison: pd.DataFrame,
    pi_comparison: pd.DataFrame,
    gates: pd.DataFrame,
    latest: pd.DataFrame,
    kpi_coverage: pd.DataFrame,
    integrated_ablation: pd.DataFrame,
    parser_quality: pd.DataFrame,
) -> None:
    performance = comparison[[
        "subindustry", "proxy_median_mase", "company_kpi_median_mase",
        "proxy_mean_mase", "company_kpi_mean_mase", "proxy_wape_pct",
        "company_kpi_wape_pct", "benchmark_no_regression_share",
        "median_company_kpi_improvement_log_points",
    ]].round(4)
    pi_view = pi_comparison[[
        "subindustry", "original_pi_80_coverage", "recalibrated_pi_80_coverage",
        "original_pi_95_coverage", "recalibrated_pi_95_coverage",
        "original_interval_80_score", "recalibrated_interval_80_score",
    ]].round(4)
    gate_view = gates[[
        "experiment", "subindustry", "point_model_gate", "uncertainty_gate",
        "combined_research_gate", "macro_research_unlocked",
        "production_promotion_eligible",
    ]]
    latest_view = latest[[
        "phase", "subindustry", "ticker", "quarter", "company_kpi_report_quarter",
        "company_kpi_feature_count", "research_selected_model", "candidate_prediction", "candidate_revenue",
        "lower_80_log_yoy", "upper_80_log_yoy", "selected_model",
        "selected_prediction", "selected_revenue",
    ]].copy()
    latest_view["candidate_revenue"] /= 1e9
    latest_view["selected_revenue"] /= 1e9
    latest_view = latest_view.rename(columns={
        "candidate_revenue": "candidate_revenue_usd_bn",
        "selected_revenue": "selected_revenue_usd_bn",
    }).round(4)
    lines = [
        "# Phase 2-4 company KPI and conformal refinement",
        "",
        "The original structural proxy benchmark is frozen and verified. Company KPI",
        "candidates use official SEC 8-K earnings exhibits released by the day-61",
        "cutoff. Missing or stale KPIs fall back to the original proxy.",
        "",
        "## Point forecast comparison",
        "",
        _markdown_table(performance),
        "",
        "## Manual-gold parser quality gate",
        "",
        _markdown_table(parser_quality[[
            "subindustry", "gold_rows", "post_numeric_accuracy",
            "post_unit_accuracy", "post_period_accuracy",
            "post_semantic_accuracy", "parser_quality_gate",
        ]].round(4)),
        "",
        "## Integrated component ablation",
        "",
        _markdown_table(integrated_ablation.round(4)),
        "",
        "## Prediction interval recalibration",
        "",
        _markdown_table(pi_view),
        "",
        "## Split gates",
        "",
        _markdown_table(gate_view),
        "",
        "## Latest local-snapshot predictions",
        "",
        _markdown_table(latest_view),
        "",
        "## Standardized KPI coverage",
        "",
        _markdown_table(kpi_coverage.round(4)),
        "",
        "Macro research unlock follows the point-model gate only. Production promotion",
        "still requires point, uncertainty, and 20 matched live-forward observations;",
        "therefore the lag-revenue baseline remains selected.",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    cutoff = int(config["forecast_cutoff_day_of_quarter"])
    holdout = int(config["time_holdout_quarters"])

    proxy_before = verify_proxy_benchmark(ROOT)
    v34_before = verify_champion(ROOT, "3.4")
    v353_before = verify_research_champion(ROOT, "3.5.3")
    if args.refresh_company_kpis:
        refresh_company_kpi_snapshot(
            KPI_SNAPSHOT, all_phase_tickers(), start_year=2019, end_year=datetime.now().year
        )

    proxy_panel = pd.read_parquet(PROXY_OUTPUT / "structural_panel.parquet")
    proxy_latest = pd.read_csv(PROXY_OUTPUT / "latest_unobserved_predictions.csv")
    for frame in (proxy_panel, proxy_latest):
        frame["forecast_cutoff_date"] = pd.to_datetime(
            frame["forecast_cutoff_date"], errors="coerce"
        )
    kpis = load_company_kpis(KPI_SNAPSHOT)
    targets = pd.concat(
        [proxy_panel[["ticker", "quarter"]], proxy_latest[["ticker", "quarter"]]],
        ignore_index=True,
    ).drop_duplicates()
    kpi_features = select_company_kpis_for_targets(kpis, targets, cutoff)
    panel_features = kpi_features.merge(
        proxy_panel[["ticker", "quarter"]].drop_duplicates(),
        on=["ticker", "quarter"],
        how="inner",
    )
    latest_features = kpi_features.merge(
        proxy_latest[["ticker", "quarter"]].drop_duplicates(),
        on=["ticker", "quarter"],
        how="inner",
    )
    candidate_panel = build_company_kpi_panel(proxy_panel, panel_features)
    integrated_ablation = _integrated_ablation_summary(candidate_panel)

    prediction_frames: dict[str, list[pd.DataFrame]] = {
        "proxy_time": [], "proxy_loco": [], "company_time": [], "company_loco": []
    }
    score_frames: list[pd.DataFrame] = []
    summary_frames: list[pd.DataFrame] = []
    gate_frames: list[pd.DataFrame] = []
    for subindustry in SUBINDUSTRY_TICKERS:
        proxy = validate_company_kpi_subindustry(proxy_panel, subindustry, holdout)
        company = validate_company_kpi_subindustry(candidate_panel, subindustry, holdout)
        prediction_frames["proxy_time"].append(proxy.time_predictions)
        prediction_frames["proxy_loco"].append(proxy.loco_predictions)
        prediction_frames["company_time"].append(company.time_predictions)
        prediction_frames["company_loco"].append(company.loco_predictions)
        for experiment, result in (
            ("PROXY_RECALIBRATED", proxy),
            ("COMPANY_KPI", company),
        ):
            score_frames.extend([
                _add_labels(result.time_scorecard, experiment, subindustry),
                _add_labels(result.loco_scorecard, experiment, subindustry),
            ])
            summary_frames.append(_add_labels(result.summary, experiment, subindustry))
            gate_frames.append(_add_labels(result.gates, experiment, subindustry))

    proxy_time = _concat(prediction_frames["proxy_time"])
    proxy_loco = _concat(prediction_frames["proxy_loco"])
    company_time = _concat(prediction_frames["company_time"])
    company_loco = _concat(prediction_frames["company_loco"])
    scores = _concat(score_frames)
    summaries = _concat(summary_frames)
    gates = _concat(gate_frames)

    frozen_time = pd.read_csv(PROXY_OUTPUT / "time_predictions.csv")
    equality = proxy_time[["ticker", "quarter", "candidate_prediction"]].merge(
        frozen_time[["ticker", "quarter", "candidate_prediction"]],
        on=["ticker", "quarter"], suffixes=("_recalibrated", "_frozen"), how="inner"
    )
    if len(equality) != len(frozen_time) or not np.allclose(
        equality["candidate_prediction_recalibrated"],
        equality["candidate_prediction_frozen"],
        equal_nan=True,
    ):
        raise RuntimeError("PI recalibration changed frozen proxy point predictions")

    comparison_rows, comparison_ticker = _benchmark_comparison(company_time, proxy_time)
    proxy_time_summary = summaries.loc[
        summaries["experiment"].eq("PROXY_RECALIBRATED")
        & summaries["validation"].str.startswith("TIME")
    ].set_index("subindustry")
    company_time_summary = summaries.loc[
        summaries["experiment"].eq("COMPANY_KPI")
        & summaries["validation"].str.startswith("TIME")
    ].set_index("subindustry")
    comparison_summary = comparison_ticker.drop_duplicates("subindustry")[[
        "subindustry", "benchmark_no_regression_share", "benchmark_severe_regression_count",
        "median_company_kpi_improvement_log_points", "mean_company_kpi_win_rate",
    ]].copy()
    for name, source in (("proxy", proxy_time_summary), ("company_kpi", company_time_summary)):
        comparison_summary[f"{name}_median_mase"] = comparison_summary["subindustry"].map(
            source["median_ticker_mase"]
        )
        comparison_summary[f"{name}_mean_mase"] = comparison_summary["subindustry"].map(
            source["mean_ticker_mase"]
        )
        comparison_summary[f"{name}_wape_pct"] = comparison_summary["subindustry"].map(
            source["overall_revenue_wape_pct"]
        )

    original_pi = _original_interval_summary()
    recal_pi = proxy_time_summary.reset_index()[[
        "subindustry", "mean_pi_80_coverage", "mean_pi_95_coverage",
        "mean_interval_80_score", "mean_interval_95_score",
        "mean_interval_80_width", "mean_interval_95_width",
    ]].rename(columns={
        "mean_pi_80_coverage": "recalibrated_pi_80_coverage",
        "mean_pi_95_coverage": "recalibrated_pi_95_coverage",
        "mean_interval_80_score": "recalibrated_interval_80_score",
        "mean_interval_95_score": "recalibrated_interval_95_score",
        "mean_interval_80_width": "recalibrated_interval_80_width",
        "mean_interval_95_width": "recalibrated_interval_95_width",
    })
    pi_comparison = original_pi.merge(recal_pi, on="subindustry", how="outer")

    parser_quality_gates, parser_audit_status = _load_parser_quality_gates()
    parser_gate_lookup = parser_quality_gates.set_index("subindustry")
    company_gate_lookup = gates.loc[
        gates["experiment"].eq("COMPANY_KPI")
    ].set_index("subindustry")
    selection_rows: list[dict[str, object]] = []
    for row in comparison_summary.itertuples(index=False):
        company_point_gate = bool(
            company_gate_lookup.loc[row.subindustry, "point_model_gate"]
        )
        company_uncertainty_gate = bool(
            company_gate_lookup.loc[row.subindustry, "uncertainty_gate"]
        )
        parser_quality_gate = bool(
            parser_gate_lookup.loc[row.subindustry, "parser_quality_gate"]
        )
        accepted = bool(
            row.company_kpi_median_mase < row.proxy_median_mase
            and row.company_kpi_mean_mase <= row.proxy_mean_mase
            and row.benchmark_no_regression_share >= 0.80
            and row.benchmark_severe_regression_count == 0
            and company_point_gate
            and company_uncertainty_gate
            and parser_quality_gate
        )
        selected_experiment = "COMPANY_KPI" if accepted else "PROXY_RECALIBRATED"
        selected_gate = gates.loc[
            gates["experiment"].eq(selected_experiment)
            & gates["subindustry"].eq(row.subindustry)
        ].iloc[0]
        selection_rows.append({
            "subindustry": row.subindustry,
            "company_kpi_candidate_accepted": accepted,
            "parser_quality_gate": parser_quality_gate,
            "parser_numeric_accuracy": parser_gate_lookup.loc[
                row.subindustry, "post_numeric_accuracy"
            ],
            "parser_unit_accuracy": parser_gate_lookup.loc[
                row.subindustry, "post_unit_accuracy"
            ],
            "parser_period_accuracy": parser_gate_lookup.loc[
                row.subindustry, "post_period_accuracy"
            ],
            "parser_semantic_accuracy": parser_gate_lookup.loc[
                row.subindustry, "post_semantic_accuracy"
            ],
            "research_selected_experiment": selected_experiment,
            "research_selected_model": (
                f"P{2 if row.subindustry in {'integrated', 'refining'} else 3 if row.subindustry == 'midstream' else 4}.1_"
                f"{row.subindustry.upper()}_COMPANY_KPI"
                if accepted
                else "STRUCTURAL_PROXY_RECALIBRATED"
            ),
            "selection_reason": (
                "KPI_IMPROVES_AND_PASSES_PARSER_POINT_UNCERTAINTY_GATES"
                if accepted
                else (
                    "KPI_REJECTED_PARSER_GATE_FAIL_CLOSED"
                    if not parser_quality_gate
                    else "KPI_REJECTED_RETAIN_PROXY_BENCHMARK"
                )
            ),
            "point_model_gate": bool(selected_gate["point_model_gate"]),
            "uncertainty_gate": bool(selected_gate["uncertainty_gate"]),
            "macro_research_unlocked": bool(selected_gate["point_model_gate"]),
            "production_promotion_eligible": False,
        })
    research_selection = pd.DataFrame(selection_rows)
    accepted_map = research_selection.set_index("subindustry")[
        "company_kpi_candidate_accepted"
    ].to_dict()
    model_map = research_selection.set_index("subindustry")[
        "research_selected_model"
    ].to_dict()
    reason_map = research_selection.set_index("subindustry")["selection_reason"].to_dict()
    research_time = pd.concat([
        company_time.loc[company_time["subindustry"].eq(subindustry)]
        if accepted_map[subindustry]
        else proxy_time.loc[proxy_time["subindustry"].eq(subindustry)]
        for subindustry in SUBINDUSTRY_TICKERS
    ], ignore_index=True)
    research_loco = pd.concat([
        company_loco.loc[company_loco["subindustry"].eq(subindustry)]
        if accepted_map[subindustry]
        else proxy_loco.loc[proxy_loco["subindustry"].eq(subindustry)]
        for subindustry in SUBINDUSTRY_TICKERS
    ], ignore_index=True)
    research_time["research_selected_model"] = research_time["subindustry"].map(model_map)
    research_loco["research_selected_model"] = research_loco["subindustry"].map(model_map)

    latest_company = build_latest_company_kpi_nowcasts(
        proxy_latest, latest_features, candidate_panel
    )
    latest_proxy = build_latest_proxy_recalibrated_nowcasts(proxy_latest, proxy_panel)
    proxy_latest_columns = [
        "ticker", "quarter", "candidate_prediction", "candidate_revenue",
        "lower_80_log_yoy", "upper_80_log_yoy", "lower_95_log_yoy", "upper_95_log_yoy",
    ]
    latest = latest_company.rename(columns={
        "candidate_prediction": "company_kpi_candidate_prediction",
        "candidate_revenue": "company_kpi_candidate_revenue",
        "lower_80_log_yoy": "company_kpi_lower_80_log_yoy",
        "upper_80_log_yoy": "company_kpi_upper_80_log_yoy",
        "lower_95_log_yoy": "company_kpi_lower_95_log_yoy",
        "upper_95_log_yoy": "company_kpi_upper_95_log_yoy",
    }).merge(
        latest_proxy[proxy_latest_columns].rename(columns={
            "candidate_prediction": "proxy_candidate_prediction",
            "candidate_revenue": "proxy_candidate_revenue",
            "lower_80_log_yoy": "proxy_lower_80_log_yoy",
            "upper_80_log_yoy": "proxy_upper_80_log_yoy",
            "lower_95_log_yoy": "proxy_lower_95_log_yoy",
            "upper_95_log_yoy": "proxy_upper_95_log_yoy",
        }),
        on=["ticker", "quarter"],
        how="left",
    )
    latest["company_kpi_candidate_accepted"] = latest["subindustry"].map(accepted_map)
    latest["research_selected_model"] = latest["subindustry"].map(model_map)
    latest["research_selection_reason"] = latest["subindustry"].map(reason_map)
    for output_column, company_column, proxy_column in (
        ("candidate_prediction", "company_kpi_candidate_prediction", "proxy_candidate_prediction"),
        ("candidate_revenue", "company_kpi_candidate_revenue", "proxy_candidate_revenue"),
        ("lower_80_log_yoy", "company_kpi_lower_80_log_yoy", "proxy_lower_80_log_yoy"),
        ("upper_80_log_yoy", "company_kpi_upper_80_log_yoy", "proxy_upper_80_log_yoy"),
        ("lower_95_log_yoy", "company_kpi_lower_95_log_yoy", "proxy_lower_95_log_yoy"),
        ("upper_95_log_yoy", "company_kpi_upper_95_log_yoy", "proxy_upper_95_log_yoy"),
    ):
        latest[output_column] = np.where(
            latest["company_kpi_candidate_accepted"],
            latest[company_column],
            latest[proxy_column],
        )
    consensus_rows, finnworlds = load_arcana_consensus(CONSENSUS, all_phase_tickers())
    consensus_pit = point_in_time_consensus(consensus_rows, cutoff)
    consensus_latest = latest_consensus_snapshot(consensus_rows)
    consensus_formal = _consensus_comparison(
        latest, consensus_pit, "POINT_IN_TIME_ELIGIBLE"
    )
    consensus_diagnostic = _consensus_comparison(
        latest,
        consensus_latest,
        "POST_CUTOFF_DIAGNOSTIC_ONLY_NOT_FOR_BACKTEST_OR_PROMOTION",
    )
    consensus_backtest_rows, consensus_performance = evaluate_model_vs_consensus(
        research_time.rename(columns={
            "candidate_revenue": "predicted_revenue", "revenue": "actual_revenue"
        }),
        consensus_pit,
    )

    kpi_coverage = pd.read_csv(KPI_SNAPSHOT / "metric_coverage.csv")
    requested_coverage = requested_kpi_coverage(kpis)
    source_manifest = pd.read_csv(KPI_SNAPSHOT / "source_manifest.csv")
    if not source_manifest["source_url"].str.contains("sec.gov", case=False).all():
        raise AssertionError("Company KPI source manifest contains a non-SEC URL")
    if pd.to_datetime(
        kpi_features["company_kpi_available_at"], errors="coerce"
    ).dt.normalize().gt(
        pd.to_datetime(
            kpi_features["forecast_cutoff_date"], errors="coerce"
        ).dt.normalize()
    ).any():
        raise AssertionError("Company KPI point-in-time cutoff violation")

    artifacts = {
        "company_kpi_point_in_time_features.csv": kpi_features,
        "proxy_recalibrated_time_predictions.csv": proxy_time,
        "proxy_recalibrated_loco_predictions.csv": proxy_loco,
        "company_kpi_time_predictions.csv": company_time,
        "company_kpi_loco_predictions.csv": company_loco,
        "scorecards.csv": scores,
        "summaries.csv": summaries,
        "split_gates.csv": gates,
        "research_model_selection.csv": research_selection,
        "parser_quality_gate.csv": parser_quality_gates,
        "research_selected_time_predictions.csv": research_time,
        "research_selected_loco_predictions.csv": research_loco,
        "benchmark_vs_company_kpi_rows.csv": comparison_rows,
        "benchmark_vs_company_kpi_ticker.csv": comparison_ticker,
        "benchmark_vs_company_kpi_summary.csv": comparison_summary,
        "integrated_component_ablation.csv": integrated_ablation,
        "pi_calibration_comparison.csv": pi_comparison,
        "latest_company_kpi_predictions.csv": latest,
        "latest_research_predictions.csv": latest,
        "latest_proxy_recalibrated_predictions.csv": latest_proxy,
        "company_kpi_metric_coverage.csv": kpi_coverage,
        "requested_kpi_coverage.csv": requested_coverage,
        "company_kpi_source_manifest.csv": source_manifest,
        "model_vs_consensus_point_in_time.csv": consensus_formal,
        "model_vs_consensus_post_cutoff_diagnostic.csv": consensus_diagnostic,
        "model_vs_consensus_backtest_rows.csv": consensus_backtest_rows,
        "model_vs_consensus_performance.csv": consensus_performance,
        "finnworlds_consensus_coverage.csv": finnworlds,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(output / filename, index=False)
    candidate_panel.to_parquet(output / "company_kpi_panel.parquet", index=False)
    _write_report(
        output,
        comparison_summary,
        pi_comparison,
        gates,
        latest,
        kpi_coverage,
        integrated_ablation,
        parser_quality_gates,
    )

    proxy_after = verify_proxy_benchmark(ROOT)
    v34_after = verify_champion(ROOT, "3.4")
    v353_after = verify_research_champion(ROOT, "3.5.3")
    for before, after, name in (
        (proxy_before, proxy_after, "Phase 2-4 proxy benchmark"),
        (v34_before, v34_after, "V3.4"),
        (v353_before, v353_after, "V3.5.3"),
    ):
        if before["manifest_sha256"] != after["manifest_sha256"]:
            raise RuntimeError(f"{name} changed during company-KPI research")

    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "paid_market_data_used": False,
        "cme_used": False,
        "cma_used": False,
        "company_kpi_source": "OFFICIAL_SEC_EDGAR_8K_EARNINGS_EXHIBITS",
        "company_kpi_availability": (
            "SEC_ACCEPTANCE_DATETIME_WITH_FILING_PLUS_ONE_FALLBACK"
        ),
        "parser_rule_version": "KPI_PARSER_CONTEXT_V2",
        "parser_audit_status": parser_audit_status,
        "parser_quality_gate_required_for_company_kpi_selection": True,
        "parser_quality_gates": parser_quality_gates.set_index("subindustry")[
            "parser_quality_gate"
        ].astype(bool).to_dict(),
        "parser_gold_audit_sha256": (
            sha256_file(PARSER_AUDIT_OUTPUT / "parser_quality_gate.csv")
            if parser_audit_status == "CURRENT"
            else None
        ),
        "prediction_interval_method": "ROLLING_TIME_SAFE_CONFORMAL_PARTIAL_POOLING",
        "point_and_uncertainty_gates_separated": True,
        "macro_unlock_uses_point_gate_only": True,
        "production_requires_live_forward": True,
        "live_matched_observations": "0/20",
        "selected_production_model": "LAG_REVENUE_BASELINE",
        "research_selected_models": research_selection.set_index("subindustry")[
            "research_selected_model"
        ].to_dict(),
        "company_kpi_accepted_subindustries": research_selection.loc[
            research_selection["company_kpi_candidate_accepted"], "subindustry"
        ].tolist(),
        "macro_research_unlocked_subindustries": research_selection.loc[
            research_selection["macro_research_unlocked"], "subindustry"
        ].tolist(),
        "requested_kpis_parsed": int(
            requested_coverage["status"].eq("PARSED_SEC_8K_EARNINGS_EXHIBIT").sum()
        ),
        "requested_kpis_total": int(len(requested_coverage)),
        "post_cutoff_consensus_used_for_backtest_or_promotion": False,
        "proxy_benchmark": proxy_after,
        "v3_4_manifest_sha256": v34_after["manifest_sha256"],
        "v3_5_3_manifest_sha256": v353_after["manifest_sha256"],
        "config_sha256": sha256_file(CONFIG),
        "company_kpi_snapshot_sha256": sha256_file(
            KPI_SNAPSHOT / "company_kpi_quarterly.csv"
        ),
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nPOINT COMPARISON\n", comparison_summary.round(4).to_string(index=False))
    print("\nPI RECALIBRATION\n", pi_comparison.round(4).to_string(index=False))
    print("\nGATES\n", gates[[
        "experiment", "subindustry", "point_model_gate", "uncertainty_gate",
        "macro_research_unlocked", "production_promotion_eligible",
    ]].to_string(index=False))
    print("\nLATEST\n", latest[[
        "subindustry", "ticker", "quarter", "company_kpi_feature_count",
        "candidate_prediction", "candidate_revenue", "lower_80_log_yoy",
        "upper_80_log_yoy", "selected_model", "selected_prediction",
    ]].round(4).to_string(index=False))
    print(f"\nProxy benchmark unchanged: {proxy_after['manifest_sha256']}")
    print(f"V3.4 unchanged: {v34_after['manifest_sha256']}")
    print(f"V3.5.3 unchanged: {v353_after['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
