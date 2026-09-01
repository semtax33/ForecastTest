from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from energy_nowcast.core.company_kpi import (
    load_company_kpis,
    select_company_kpis_for_targets,
)
from energy_nowcast.core.company_kpi_platform import (
    build_company_kpi_panel,
    validate_company_kpi_subindustry,
)
from energy_nowcast.core.kpi_parser_audit import (
    apply_manual_gold_to_pre_snapshot,
    build_gold_audit,
    load_gold_labels,
    parser_change_log,
    quality_error_diagnostics,
    summarize_gold_audit,
    verify_pre_audit_benchmark,
)
from energy_nowcast.core.proxy_benchmark import verify_proxy_benchmark
from energy_nowcast.core.taxonomy import SUBINDUSTRY_TICKERS
from energy_nowcast.operations.champion import verify_champion
from energy_nowcast.research.v36.benchmark import verify_research_champion


ROOT = Path(__file__).resolve().parent
PRE_AUDIT = ROOT / "benchmarks" / "phase2_4_kpi_parser_pre_audit"
POST_SNAPSHOT = ROOT / "data-lake" / "phase2_4_company_kpi_snapshot"
PROXY_OUTPUT = ROOT / "output" / "phase2_4_structural_research"
COMPANY_OUTPUT = ROOT / "output" / "phase2_4_company_kpi_research"
GOLD_LABELS = ROOT / "configs" / "phase2_4_kpi_parser_gold_labels.csv"
OUTPUT = ROOT / "output" / "kpi_parser_gold_audit"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Phase 2-4 company KPI parsing against manual gold labels."
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
    if frame.empty:
        return "_No rows._"
    return frame.to_markdown(index=False)


def _gold_replacement_backtest(
    proxy_panel: pd.DataFrame,
    gold_metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    targets = proxy_panel[["ticker", "quarter"]].drop_duplicates()
    features = select_company_kpis_for_targets(gold_metrics, targets, cutoff_day=61)
    panel = build_company_kpi_panel(proxy_panel, features)
    predictions: list[pd.DataFrame] = []
    summaries: list[dict[str, object]] = []
    for subindustry in SUBINDUSTRY_TICKERS:
        result = validate_company_kpi_subindustry(panel, subindustry, quarters=8)
        time_summary = result.summary.iloc[0]
        predictions.append(result.time_predictions)
        summaries.append(
            {
                "subindustry": subindustry,
                "median_ticker_mase": time_summary["median_ticker_mase"],
                "mean_ticker_mase": time_summary["mean_ticker_mase"],
                "overall_revenue_wape_pct": time_summary[
                    "overall_revenue_wape_pct"
                ],
                "mean_directional_hit_rate": time_summary[
                    "mean_directional_hit_rate"
                ],
                "mean_pi_80_coverage": time_summary["mean_pi_80_coverage"],
                "mean_pi_95_coverage": time_summary["mean_pi_95_coverage"],
            }
        )
    return pd.concat(predictions, ignore_index=True), pd.DataFrame(summaries)


def _performance_comparison(gold_summary: pd.DataFrame) -> pd.DataFrame:
    pre = pd.read_csv(PRE_AUDIT / "benchmark_vs_company_kpi_summary.csv").set_index(
        "subindustry"
    )
    post = pd.read_csv(
        COMPANY_OUTPUT / "benchmark_vs_company_kpi_summary.csv"
    ).set_index("subindustry")
    gold = gold_summary.set_index("subindustry")
    rows: list[dict[str, object]] = []
    for subindustry in SUBINDUSTRY_TICKERS:
        rows.append(
            {
                "subindustry": subindustry,
                "pre_parser_median_mase": pre.loc[
                    subindustry, "company_kpi_median_mase"
                ],
                "gold_sample_replacement_median_mase": gold.loc[
                    subindustry, "median_ticker_mase"
                ],
                "post_parser_median_mase": post.loc[
                    subindustry, "company_kpi_median_mase"
                ],
                "pre_parser_mean_mase": pre.loc[
                    subindustry, "company_kpi_mean_mase"
                ],
                "gold_sample_replacement_mean_mase": gold.loc[
                    subindustry, "mean_ticker_mase"
                ],
                "post_parser_mean_mase": post.loc[
                    subindustry, "company_kpi_mean_mase"
                ],
                "pre_parser_wape_pct": pre.loc[
                    subindustry, "company_kpi_wape_pct"
                ],
                "gold_sample_replacement_wape_pct": gold.loc[
                    subindustry, "overall_revenue_wape_pct"
                ],
                "post_parser_wape_pct": post.loc[
                    subindustry, "company_kpi_wape_pct"
                ],
                "post_vs_pre_median_mase_change": post.loc[
                    subindustry, "company_kpi_median_mase"
                ]
                - pre.loc[subindustry, "company_kpi_median_mase"],
            }
        )
    return pd.DataFrame(rows)


def _write_report(
    output: Path,
    overall: pd.DataFrame,
    by_subindustry: pd.DataFrame,
    sampling_strata: pd.DataFrame,
    changes: pd.DataFrame,
    performance: pd.DataFrame,
    quality_error: pd.DataFrame,
) -> None:
    change_summary = (
        changes.groupby(["subindustry", "change_reason"], as_index=False)
        .agg(changed_rows=("ticker", "size"))
        .sort_values(["subindustry", "change_reason"])
    )
    lines = [
        "# KPI parser manual-gold audit",
        "",
        "A stratified 75-row sample was transcribed from official SEC earnings",
        "exhibits across early, middle, and recent periods. Numeric, unit,",
        "quarter/period, and semantic matches are evaluated independently.",
        "",
        "`HIGH` source quality means a directly transcribed, period-unambiguous",
        "disclosure row; `LOW` means period-context selection, component",
        "aggregation, or unit normalization was required.",
        "",
        "## Gold sampling strata",
        "",
        _markdown(sampling_strata),
        "",
        "## Overall parser accuracy",
        "",
        _markdown(overall.round(4)),
        "",
        "## Accuracy by subindustry",
        "",
        _markdown(by_subindustry.round(4)),
        "",
        "## Parser corrections",
        "",
        _markdown(change_summary),
        "",
        "## Parser value versus manual-gold replacement backtest",
        "",
        _markdown(performance.round(4)),
        "",
        "The gold-sample replacement column changes only the 75 manually",
        "reviewed rows in the frozen pre-audit snapshot. The post-parser column",
        "applies the corrected rule to every matching historical filing.",
        "",
        "## Rule confidence versus forecast error",
        "",
        _markdown(quality_error.round(4)),
        "",
        "Parser quality is a mandatory gate for company-KPI research selection.",
        "It does not replace the point-model, uncertainty, or live-forward gates.",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    pre_integrity = verify_pre_audit_benchmark(ROOT)
    proxy_integrity = verify_proxy_benchmark(ROOT)
    v34 = verify_champion(ROOT, "3.4")
    v353 = verify_research_champion(ROOT, "3.5.3")

    labels = load_gold_labels(GOLD_LABELS)
    pre_metrics = load_company_kpis(PRE_AUDIT)
    post_metrics = load_company_kpis(POST_SNAPSHOT)
    audit_rows = build_gold_audit(labels, pre_metrics, post_metrics)
    sampling_strata = (
        audit_rows.groupby(
            ["subindustry", "sample_era", "source_quality_stratum"],
            as_index=False,
        )
        .agg(gold_rows=("ticker", "size"))
        .sort_values(["subindustry", "sample_era", "source_quality_stratum"])
    )
    overall = summarize_gold_audit(audit_rows)
    by_subindustry = summarize_gold_audit(audit_rows, ["subindustry"])
    by_metric = summarize_gold_audit(audit_rows, ["ticker", "metric_id"])
    changes = parser_change_log(pre_metrics, post_metrics)
    change_summary = (
        changes.groupby(["subindustry", "change_reason"], as_index=False)
        .agg(changed_rows=("ticker", "size"))
    )

    proxy_panel = pd.read_parquet(PROXY_OUTPUT / "structural_panel.parquet")
    gold_metrics = apply_manual_gold_to_pre_snapshot(
        pre_metrics, labels, post_metrics
    )
    gold_predictions, gold_summary = _gold_replacement_backtest(
        proxy_panel, gold_metrics
    )
    performance = _performance_comparison(gold_summary)

    current_predictions = pd.read_csv(
        COMPANY_OUTPUT / "company_kpi_time_predictions.csv"
    )
    quality_error, quality_correlations = quality_error_diagnostics(
        current_predictions, by_subindustry
    )

    artifacts = {
        "parser_gold_audit_rows.csv": audit_rows,
        "gold_sampling_strata.csv": sampling_strata,
        "parser_gold_audit_summary.csv": overall,
        "parser_quality_gate.csv": by_subindustry,
        "parser_gold_audit_by_metric.csv": by_metric,
        "parser_change_log.csv": changes,
        "parser_change_summary.csv": change_summary,
        "gold_sample_replacement_time_predictions.csv": gold_predictions,
        "gold_sample_replacement_summary.csv": gold_summary,
        "pre_gold_post_model_performance.csv": performance,
        "kpi_quality_vs_forecast_error.csv": quality_error,
        "kpi_quality_error_correlations.csv": quality_correlations,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(output / filename, index=False)

    _write_report(
        output,
        overall,
        by_subindustry,
        sampling_strata,
        changes,
        performance,
        quality_error,
    )
    metadata = {
        "version": "KPI_PARSER_GOLD_AUDIT_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "manual_gold_rows": len(labels),
        "sampling": {
            "integrated": int(labels["subindustry"].eq("integrated").sum()),
            "refining": int(labels["subindustry"].eq("refining").sum()),
            "midstream": int(labels["subindustry"].eq("midstream").sum()),
            "services": int(labels["subindustry"].eq("services").sum()),
        },
        "sampling_eras": labels["sample_era"].value_counts().sort_index().to_dict(),
        "source_quality_strata": labels["source_quality_stratum"]
        .value_counts()
        .sort_index()
        .to_dict(),
        "thresholds": {
            "numeric_near_match_minimum": 0.95,
            "unit_match_minimum": 1.00,
            "period_match_minimum": 1.00,
            "semantic_match_minimum": 0.95,
        },
        "all_subindustry_parser_gates_pass": bool(
            by_subindustry["parser_quality_gate"].all()
        ),
        "pre_audit_benchmark": pre_integrity,
        "proxy_benchmark": proxy_integrity,
        "v3_4_manifest_sha256": v34["manifest_sha256"],
        "v3_5_3_manifest_sha256": v353["manifest_sha256"],
        "gold_labels_sha256": _sha256(GOLD_LABELS),
        "post_snapshot_sha256": _sha256(
            POST_SNAPSHOT / "company_kpi_quarterly.csv"
        ),
        "parser_source_sha256": _sha256(
            ROOT / "energy_nowcast" / "core" / "company_kpi.py"
        ),
        "paid_market_data_used": False,
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    verify_pre_audit_benchmark(ROOT)
    verify_proxy_benchmark(ROOT)
    verify_champion(ROOT, "3.4")
    verify_research_champion(ROOT, "3.5.3")

    print("\nGOLD ACCURACY")
    print(by_subindustry.round(4).to_string(index=False))
    print("\nPARSER CHANGES")
    print(change_summary.to_string(index=False))
    print("\nMODEL PERFORMANCE")
    print(performance.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
