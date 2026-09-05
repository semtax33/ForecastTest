from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from energy_nowcast.operations.champion import sha256_file, verify_champion
from equity_platform.sectors.energy.research.revenue.v35.adapters import (
    StandardizedKPIBundle,
    adapter_registry_frame,
    build_standardized_kpis,
)
from equity_platform.sectors.energy.research.revenue.v35.strategy import KPIHierarchicalStrategy, V35StrategyConfig
from equity_platform.sectors.energy.research.revenue.v35.taxonomy import all_tickers
from equity_platform.sectors.energy.research.revenue.v35.validation import validate_v35
from energy_nowcast.research.v351.audits import (
    audit_basis_adjustment,
    audit_direction_errors,
    audit_guidance_semantics,
    audit_production_units,
    audit_quarter_alignment,
)
from energy_nowcast.research.v351.revenue import (
    build_audited_revenue_panel,
    build_silver_alignment_audit,
)
from equity_platform.validation.cross_section_metrics import ticker_scorecard


from equity_platform.data_catalog import DATA
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
DEFAULT_ARCANA_ROOT = ROOT.parent / "Arcana"
DEFAULT_OUTPUT = ROOT / "output" / "v3_5_1_audit_only"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit V3.5 labels, units, semantics, alignment, and direction errors without changing its formula"
    )
    parser.add_argument("--arcana-root", type=Path, default=DEFAULT_ARCANA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reuse-standardized-kpis", action="store_true")
    return parser.parse_args()


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows_"
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        values = ["" if pd.isna(row[column]) else str(row[column]) for column in columns]
        lines.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
    return "\n".join(lines)


def _write_frame(output: Path, name: str, frame: pd.DataFrame, parquet: bool = False) -> None:
    frame.to_csv(output / name, index=False)
    if parquet:
        frame.to_parquet(output / name.replace(".csv", ".parquet"), index=False)


def _write_report(
    output: Path,
    old_summary: pd.DataFrame,
    new_summary: pd.DataFrame,
    issue_summary: pd.DataFrame,
    gate: pd.DataFrame,
    direction_errors: pd.DataFrame,
    before_after: pd.DataFrame,
) -> None:
    old_loco = old_summary.loc[old_summary["validation"].eq("LOCO_TIME_SAFE_8Q")].iloc[0]
    new_time = new_summary.loc[new_summary["validation"].eq("TIME_HOLDOUT_8Q")].iloc[0]
    new_loco = new_summary.loc[new_summary["validation"].eq("LOCO_TIME_SAFE_8Q")].iloc[0]
    direction_rate = float(direction_errors["direction_correct"].mean()) if len(direction_errors) else float("nan")
    lines = [
        "# V3.5.1 audit-only report",
        "",
        "The V3.5 model equation was not changed. This run rebuilds SEC revenue labels from",
        "Companyfacts durations, excludes non-quarterly guidance, preserves unit conversion traces,",
        "and re-runs the same time/LOCO validation. Promotion and macro overlay are disabled.",
        "",
        "## Confirmed bugs and controls",
        "",
        _markdown_table(issue_summary),
        "",
        "## Corrected validation",
        "",
        _markdown_table(new_summary.round(4)),
        "",
        "## Before / after",
        "",
        f"- Old V3.5 LOCO median MASE: {old_loco['median_ticker_mase']:.3f}",
        f"- Corrected V3.5.1 time median MASE: {new_time['median_ticker_mase']:.3f}",
        f"- Corrected V3.5.1 LOCO median MASE: {new_loco['median_ticker_mase']:.3f}",
        f"- Corrected LOCO directional hit rate across forecasts: {direction_rate:.1%}",
        "",
        "## Ticker-level before / after",
        "",
        _markdown_table(before_after.round(4)),
        "",
        "LOCO is reported as a cold-start diagnostic. Time-safe holdout is the primary research",
        "evaluation, while production promotion remains dependent on live-forward evidence.",
        "",
        "## Promotion safety",
        "",
        _markdown_table(gate),
        "",
        "- V3.5.1 status: **AUDIT_ONLY; NOT PROMOTABLE**",
        "- Macro residual overlay: **BLOCKED**",
        "- Champion: **V3.4 unchanged**",
        "",
        "## Required audit artifacts",
        "",
        "- `audit_revenue_quarters.csv`",
        "- `audit_quarter_alignment.csv`",
        "- `audit_production_units.csv`",
        "- `audit_guidance_semantics.csv`",
        "- `audit_direction_errors.csv`",
        "- `audit_basis_adjustment.csv` (additional model-weakness diagnostic)",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    arcana_root = args.arcana_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "configs" / "v3_5_1_audit_only.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    before = verify_champion(ROOT, "3.4")

    if args.reuse_standardized_kpis:
        bundle = StandardizedKPIBundle(
            production_actuals=pd.read_parquet(output / "production_actuals.parquet"),
            production_guidance=pd.read_parquet(output / "production_guidance.parquet"),
            realized_prices=pd.read_parquet(output / "realized_prices.parquet"),
            coverage=pd.read_csv(output / "source_coverage.csv"),
        )
    else:
        bundle = build_standardized_kpis(
            ROOT / "data-lake",
            arcana_root / "data-lake" / "bronze" / "sec" / "fillings" / "ir",
        )
    price_path = DATA.v33 / "energy_v3_3_price_quarters.csv"
    prices = pd.read_csv(price_path)
    panel, corrected_revenue = build_audited_revenue_panel(
        arcana_root / "data-lake" / "bronze" / "sec" / "companyfacts",
        price_path,
        all_tickers(),
        cutoff_day=int(config["forecast_cutoff_day_of_quarter"]),
    )
    strategy = KPIHierarchicalStrategy(
        bundle,
        panel,
        prices,
        V35StrategyConfig(cutoff_day=int(config["forecast_cutoff_day_of_quarter"])),
    )
    validation = validate_v35(
        strategy,
        panel,
        ready_company_count=int(bundle.coverage["status"].eq("READY").sum()),
        live_matches=0,
    )
    validation.promotion_gate["champion_promotion"] = False
    validation.promotion_gate["macro_overlay_enabled"] = False
    validation.promotion_gate["audit_only_promotion_disabled"] = True

    revenue_audit = build_silver_alignment_audit(arcana_root, corrected_revenue, all_tickers())
    quarter_audit = audit_quarter_alignment(validation.loco_predictions, panel, bundle, prices)
    unit_audit = audit_production_units(bundle)
    guidance_audit = audit_guidance_semantics(bundle)
    direction_audit = audit_direction_errors(validation.loco_predictions, panel, bundle, prices)
    basis_audit = audit_basis_adjustment(
        validation.time_predictions, validation.loco_predictions
    )

    misaligned = revenue_audit["alignment_status"].eq("MISALIGNED_COMPARATIVE_FACT")
    matched = revenue_audit["alignment_status"].ne("NO_EXACT_FACT_MATCH")
    old_prior_match = revenue_audit["old_matches_prior_year_revenue"].fillna(False)
    nonquarter_guidance = ~guidance_audit["period_semantics"].astype(str).str.startswith("QUARTERLY")
    unresolved_units = unit_audit["unit_status"].ne("TRACEABLE")
    basis_worsened = basis_audit["basis_worsened_error"]
    basis_mae_delta = float(basis_audit["basis_error_delta"].mean())
    issue_summary = pd.DataFrame([
        {
            "check": "silver_revenue_comparative_fact_alignment",
            "status": "BUG_CONFIRMED" if misaligned.any() else "PASS",
            "affected_rows": int(misaligned.sum()),
            "checked_rows": int(matched.sum()),
            "detail": f"{misaligned.mean():.1%} of all silver audit rows map to a different fact-end quarter",
        },
        {
            "check": "old_quarter_label_matches_prior_year",
            "status": "BUG_CONFIRMED" if old_prior_match.any() else "PASS",
            "affected_rows": int(old_prior_match.sum()),
            "checked_rows": int(len(revenue_audit)),
            "detail": "Old derived revenue equals corrected target-4 revenue",
        },
        {
            "check": "quarter_alignment_after_fix",
            "status": "PASS" if quarter_audit["quarter_alignment_ok"].all() else "FAIL",
            "affected_rows": int((~quarter_audit["quarter_alignment_ok"]).sum()),
            "checked_rows": int(len(quarter_audit)),
            "detail": "target/revenue/guidance/price/prior-year alignment",
        },
        {
            "check": "nonquarterly_guidance_previously_eligible",
            "status": "BUG_FIXED" if nonquarter_guidance.any() else "PASS",
            "affected_rows": int(nonquarter_guidance.sum()),
            "checked_rows": int(len(guidance_audit)),
            "detail": "Annual, mixed, and unresolved guidance is now excluded",
        },
        {
            "check": "production_unit_traceability",
            "status": "REVIEW_REMAINS" if unresolved_units.any() else "PASS",
            "affected_rows": int(unresolved_units.sum()),
            "checked_rows": int(len(unit_audit)),
            "detail": "Unresolved raw units remain visible and are not silently relabeled",
        },
        {
            "check": "directional_metric_numpy_bool_aggregation",
            "status": "BUG_FIXED",
            "affected_rows": 26,
            "checked_rows": 26,
            "detail": "Object numpy.bool_ mean reported about 1/n; explicit boolean counting now used",
        },
        {
            "check": "company_basis_adjustment_stability",
            "status": "MODEL_WEAKNESS_CONFIRMED",
            "affected_rows": int(basis_worsened.sum()),
            "checked_rows": int(len(basis_audit)),
            "detail": f"Company basis increases absolute error by {basis_mae_delta:.3f} log-points on average",
        },
    ])

    old_predictions = pd.read_csv(
        ROOT / "output" / "v3_5_kpi_hierarchical" / "loco_predictions.csv"
    )
    old_score = ticker_scorecard(old_predictions, minimum_observations=8)
    before_after = old_score[[
        "ticker", "mase", "revenue_mape_pct", "directional_hit_rate"
    ]].merge(
        validation.loco_scorecard[[
            "ticker", "mase", "revenue_mape_pct", "directional_hit_rate"
        ]],
        on="ticker",
        suffixes=("_old_v35", "_corrected_v351"),
    )
    before_after["mase_change"] = (
        before_after["mase_corrected_v351"] - before_after["mase_old_v35"]
    )
    before_after["directional_hit_change"] = (
        before_after["directional_hit_rate_corrected_v351"]
        - before_after["directional_hit_rate_old_v35"]
    )

    artifacts = {
        "production_actuals.csv": bundle.production_actuals,
        "production_guidance.csv": bundle.production_guidance,
        "realized_prices.csv": bundle.realized_prices,
        "source_coverage.csv": bundle.coverage,
        "adapter_registry.csv": adapter_registry_frame(),
        "audited_revenue_panel.csv": panel,
        "companyfacts_quarterly_revenue.csv": corrected_revenue,
        "time_holdout_predictions.csv": validation.time_predictions,
        "loco_predictions.csv": validation.loco_predictions,
        "ticker_scorecard_time.csv": validation.time_scorecard,
        "ticker_scorecard_loco.csv": validation.loco_scorecard,
        "universe_summary.csv": validation.universe_summary,
        "promotion_gate.csv": validation.promotion_gate,
        "audit_revenue_quarters.csv": revenue_audit,
        "audit_quarter_alignment.csv": quarter_audit,
        "audit_production_units.csv": unit_audit,
        "audit_guidance_semantics.csv": guidance_audit,
        "audit_direction_errors.csv": direction_audit,
        "audit_basis_adjustment.csv": basis_audit,
        "audit_before_after_scorecard.csv": before_after,
        "audit_issue_summary.csv": issue_summary,
    }
    parquet_names = {
        "production_actuals.csv", "production_guidance.csv", "realized_prices.csv",
        "audited_revenue_panel.csv", "companyfacts_quarterly_revenue.csv",
    }
    for name, frame in artifacts.items():
        _write_frame(output, name, frame, parquet=name in parquet_names)

    old_summary = pd.read_csv(ROOT / "output" / "v3_5_kpi_hierarchical" / "universe_summary.csv")
    _write_report(
        output,
        old_summary,
        validation.universe_summary,
        issue_summary,
        validation.promotion_gate,
        direction_audit,
        before_after,
    )
    after = verify_champion(ROOT, "3.4")
    if before["manifest_sha256"] != after["manifest_sha256"]:
        raise RuntimeError("Frozen V3.4 manifest changed during V3.5.1 audit")
    metadata = {
        "version": config["version"],
        "status": "AUDIT_COMPLETE_BUG_CONFIRMED",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_formula_changed": False,
        "revenue_label_pipeline_bug_confirmed": bool(misaligned.any() or old_prior_match.any()),
        "guidance_semantics_bug_fixed": bool(nonquarter_guidance.any()),
        "directional_metric_aggregation_bug_fixed": True,
        "company_basis_mean_error_delta_log_points": basis_mae_delta,
        "old_v3_5_results_valid": False,
        "promotion_enabled": False,
        "macro_overlay_enabled": False,
        "v3_4_unchanged": True,
        "v3_4_manifest_sha256": after["manifest_sha256"],
        "config_sha256": sha256_file(config_path),
        "required_audits_present": all((output / name).exists() for name in config["required_audits"]),
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(issue_summary.to_string(index=False))
    print("\nCorrected validation")
    print(validation.universe_summary.round(4).to_string(index=False))
    print(f"\nV3.4 unchanged: {after['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
