from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.operations.champion import sha256_file, verify_champion
from energy_nowcast.research.v35.adapters import (
    StandardizedKPIBundle,
    adapter_registry_frame,
    build_standardized_kpis,
)
from energy_nowcast.research.v35.strategy import KPIHierarchicalStrategy, V35StrategyConfig
from energy_nowcast.research.v35.taxonomy import all_tickers
from energy_nowcast.research.v351.revenue import build_audited_revenue_panel
from energy_nowcast.research.v352.validation import validate_v352


from equity_platform.data_catalog import DATA
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
DEFAULT_ARCANA_ROOT = ROOT.parent / "Arcana"
DEFAULT_OUTPUT = ROOT / "output" / "v3_5_2_clean_component"
AUDIT_OUTPUT = ROOT / "output" / "v3_5_1_audit_only"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the V3.5.2 clean-component candidate with company basis disabled"
    )
    parser.add_argument("--arcana-root", type=Path, default=DEFAULT_ARCANA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--reuse-audit-kpis",
        action="store_true",
        help="Reuse V3.5.1 standardized KPI parquet files; revenue labels are always rebuilt",
    )
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


def _read_audit_bundle() -> StandardizedKPIBundle:
    return StandardizedKPIBundle(
        production_actuals=pd.read_parquet(AUDIT_OUTPUT / "production_actuals.parquet"),
        production_guidance=pd.read_parquet(AUDIT_OUTPUT / "production_guidance.parquet"),
        realized_prices=pd.read_parquet(AUDIT_OUTPUT / "realized_prices.parquet"),
        coverage=pd.read_csv(AUDIT_OUTPUT / "source_coverage.csv"),
    )


def _live_matches() -> int:
    path = ROOT / "output" / "operations" / "live_scorecard_summary.csv"
    if not path.exists():
        return 0
    frame = pd.read_csv(path)
    return int(pd.to_numeric(frame.get("matched_observations"), errors="coerce").fillna(0).iloc[0])


def _write_report(
    output: Path,
    summaries: pd.DataFrame,
    gate: pd.DataFrame,
    time_comparison: pd.DataFrame,
    small_denominators: pd.DataFrame,
    macro_status: str,
) -> None:
    time = summaries.loc[summaries["validation"].eq("TIME_HOLDOUT_8Q_PRIMARY")].iloc[0]
    loco = summaries.loc[summaries["validation"].eq("LOCO_TIME_SAFE_8Q_COLD_START")].iloc[0]
    lines = [
        "# V3.5.2 clean-component report",
        "",
        "V3.5.2 preserves the corrected V3.5.1 labels, quarterly-guidance policy, unit traces,",
        "and directional metric fix. Its only model change is disabling company basis adjustment.",
        "No new feature or macro overlay is added.",
        "",
        "## Corrected evaluation roles",
        "",
        "- TIME holdout: primary research gate",
        "- LOCO: cold-start diagnostic",
        "- Live-forward: production promotion gate after 20 matched actuals",
        "",
        "## Results",
        "",
        _markdown_table(summaries.round(4)),
        "",
        f"- TIME median / mean MASE: {time['median_ticker_mase']:.3f} / {time['mean_ticker_mase']:.3f}",
        f"- TIME MASE<1: {int(time['mase_below_1_count'])}/{int(time['evaluable_company_count'])} evaluable ({time['mase_below_1_share']:.1%})",
        f"- TIME legacy no-regression: {int(time['legacy_no_regression_count'])}/{int(time['evaluable_company_count'])} evaluable ({time['legacy_no_regression_share']:.1%})",
        f"- LOCO median / mean MASE: {loco['median_ticker_mase']:.3f} / {loco['mean_ticker_mase']:.3f}",
        f"- LOCO MASE<1: {int(loco['mase_below_1_count'])}/{int(loco['evaluable_company_count'])} evaluable ({loco['mase_below_1_share']:.1%})",
        "",
        "## Basis-removal effect on primary TIME holdout",
        "",
        _markdown_table(time_comparison.round(4)),
        "",
        "## Revenue-level diagnostics",
        "",
        "MAPE remains available only as a diagnostic. WAPE and median APE are the reported",
        "revenue-level metrics. Small denominators are flagged, not removed.",
        "",
        _markdown_table(small_denominators),
        "",
        "## Promotion gate",
        "",
        _markdown_table(gate),
        "",
        "## Decision",
        "",
        "- Company basis overlay: **OFF**",
        f"- Macro residual overlay: **{macro_status}**",
        f"- Research component gate: **{'PASS' if bool(gate['research_component_gate'].iloc[0]) else 'FAIL'}**",
        f"- Champion promotion: **{'PASS' if bool(gate['champion_promotion'].iloc[0]) else 'LOCKED'}**",
        "- Champion: **V3.4 unchanged**",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    arcana_root = args.arcana_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "configs" / "v3_5_2_clean_component.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    before = verify_champion(ROOT, "3.4")

    if args.reuse_audit_kpis:
        bundle = _read_audit_bundle()
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
        V35StrategyConfig(
            cutoff_day=int(config["forecast_cutoff_day_of_quarter"]),
            volume_history_quarters=int(config["volume_history_quarters"]),
            partial_pooling_k=float(config["partial_pooling_k"]),
            use_company_basis=False,
        ),
    )
    validation = validate_v352(
        strategy,
        panel,
        ready_company_count=int(bundle.coverage["status"].eq("READY").sum()),
        registered_company_count=len(all_tickers()),
        live_matches=_live_matches(),
    )

    available_time = validation.time_predictions.loc[
        validation.time_predictions["candidate_status"].eq("AVAILABLE")
    ]
    available_loco = validation.loco_predictions.loc[
        validation.loco_predictions["candidate_status"].eq("AVAILABLE")
    ]
    paired = available_time[["ticker", "quarter", "candidate_prediction"]].merge(
        available_loco[["ticker", "quarter", "candidate_prediction"]],
        on=["ticker", "quarter"],
        suffixes=("_time", "_loco"),
    )
    if not np.allclose(
        paired["candidate_prediction_time"], paired["candidate_prediction_loco"], atol=1e-12
    ):
        raise AssertionError("Clean-component TIME and LOCO structural predictions differ")
    if not validation.time_predictions.loc[
        validation.time_predictions["candidate_status"].eq("AVAILABLE"), "basis_adjustment_log_points"
    ].eq(0.0).all():
        raise AssertionError("Company basis adjustment is not fully disabled")

    old_time = pd.read_csv(AUDIT_OUTPUT / "ticker_scorecard_time.csv")
    time_comparison = old_time[[
        "ticker", "mase", "candidate_mae_log_points", "improvement_log_points"
    ]].merge(
        validation.time_scorecard[[
            "ticker", "mase", "candidate_mae_log_points", "improvement_log_points"
        ]],
        on="ticker",
        suffixes=("_v351_basis_on", "_v352_basis_off"),
    )
    time_comparison["candidate_mae_change"] = (
        time_comparison["candidate_mae_log_points_v352_basis_off"]
        - time_comparison["candidate_mae_log_points_v351_basis_on"]
    )
    small_denominators = validation.time_predictions.loc[
        validation.time_predictions["small_denominator_flag"].eq(True),  # noqa: E712
        [
            "ticker", "quarter", "revenue", "rolling_median_revenue_8q",
            "candidate_revenue", "candidate_revenue_ape_pct",
        ],
    ].copy()

    artifacts = {
        "production_actuals.csv": bundle.production_actuals,
        "production_guidance.csv": bundle.production_guidance,
        "realized_prices.csv": bundle.realized_prices,
        "source_coverage.csv": bundle.coverage,
        "adapter_registry.csv": adapter_registry_frame(),
        "companyfacts_quarterly_revenue.csv": corrected_revenue,
        "audited_revenue_panel.csv": panel,
        "time_holdout_predictions.csv": validation.time_predictions,
        "loco_predictions.csv": validation.loco_predictions,
        "ticker_scorecard_time.csv": validation.time_scorecard,
        "ticker_scorecard_loco.csv": validation.loco_scorecard,
        "universe_summary.csv": validation.universe_summary,
        "promotion_gate.csv": validation.promotion_gate,
        "time_basis_removal_comparison.csv": time_comparison,
        "small_denominator_observations.csv": small_denominators,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(output / filename, index=False)
    for stem in (
        "production_actuals", "production_guidance", "realized_prices",
        "companyfacts_quarterly_revenue", "audited_revenue_panel",
    ):
        artifacts[f"{stem}.csv"].to_parquet(output / f"{stem}.parquet", index=False)

    research_pass = bool(validation.promotion_gate["research_component_gate"].iloc[0])
    macro_status = "UNLOCKED_FOR_SEPARATE_RESIDUAL_RESEARCH" if research_pass else "BLOCKED_CLEAN_COMPONENT_GATE"
    pd.DataFrame([{
        "company_basis_overlay": "OFF",
        "macro_overlay_status": macro_status,
        "macro_applied_to_results": False,
    }]).to_csv(output / "overlay_status.csv", index=False)
    _write_report(
        output,
        validation.universe_summary,
        validation.promotion_gate,
        time_comparison,
        small_denominators,
        macro_status,
    )

    after = verify_champion(ROOT, "3.4")
    if before["manifest_sha256"] != after["manifest_sha256"]:
        raise RuntimeError("V3.4 changed during V3.5.2 research")
    metadata = {
        "version": config["version"],
        "status": "RESEARCH_GATE_PASS" if research_pass else "RESEARCH_GATE_FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "company_basis_enabled": False,
        "company_basis_overlay_policy": "OPTIONAL_SEPARATE_OVERLAY_NOT_PROMOTED",
        "mape_role": "DIAGNOSTIC_ONLY",
        "denominator_policy": config["denominator_policy"],
        "macro_overlay_status": macro_status,
        "v3_4_unchanged": True,
        "v3_4_manifest_sha256": after["manifest_sha256"],
        "config_sha256": sha256_file(config_path),
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(validation.universe_summary.round(4).to_string(index=False))
    print("\nPromotion gate")
    print(validation.promotion_gate.to_string(index=False))
    print(f"\nCompany basis: OFF; macro: {macro_status}")
    print(f"V3.4 unchanged: {after['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
