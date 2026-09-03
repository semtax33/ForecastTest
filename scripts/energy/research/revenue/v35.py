from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from energy_nowcast.operations.champion import sha256_file, verify_champion
from energy_nowcast.research.v35.adapters import (
    StandardizedKPIBundle,
    adapter_registry_frame,
    build_standardized_kpis,
)
from energy_nowcast.research.v35.strategy import KPIHierarchicalStrategy, V35StrategyConfig
from energy_nowcast.research.v35.taxonomy import all_tickers
from energy_nowcast.research.v35.validation import V35ValidationResult, validate_v35
from energy_nowcast.validation.universe_backtest import load_e_and_p_panel


from equity_platform.data_catalog import DATA
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
DEFAULT_ARCANA_ROOT = ROOT.parent / "Arcana"
DEFAULT_OUTPUT = ROOT / "output" / "v3_5_kpi_hierarchical"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and time/LOCO-test the locked V3.5 KPI hierarchical research strategy"
    )
    parser.add_argument("--arcana-root", type=Path, default=DEFAULT_ARCANA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--reuse-standardized-kpis",
        action="store_true",
        help="Reuse the standardized parquet files already written to output-dir",
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


def _write_standardized(output: Path, bundle: StandardizedKPIBundle) -> None:
    artifacts = {
        "production_actuals": bundle.production_actuals,
        "production_guidance": bundle.production_guidance,
        "realized_prices": bundle.realized_prices,
    }
    for stem, frame in artifacts.items():
        frame.to_parquet(output / f"{stem}.parquet", index=False)
        frame.to_csv(output / f"{stem}.csv", index=False)
    bundle.coverage.to_csv(output / "source_coverage.csv", index=False)


def _read_standardized(output: Path) -> StandardizedKPIBundle:
    paths = [output / f"{name}.parquet" for name in (
        "production_actuals", "production_guidance", "realized_prices"
    )]
    coverage_path = output / "source_coverage.csv"
    missing = [str(path) for path in [*paths, coverage_path] if not path.exists()]
    if missing:
        raise FileNotFoundError("Cannot reuse standardized KPI cache; missing: " + ", ".join(missing))
    return StandardizedKPIBundle(
        production_actuals=pd.read_parquet(paths[0]),
        production_guidance=pd.read_parquet(paths[1]),
        realized_prices=pd.read_parquet(paths[2]),
        coverage=pd.read_csv(coverage_path),
    )


def _live_matches(root: Path) -> int:
    path = root / "output" / "operations" / "live_scorecard_summary.csv"
    if not path.exists():
        return 0
    frame = pd.read_csv(path)
    if frame.empty or "matched_observations" not in frame:
        return 0
    return int(pd.to_numeric(frame["matched_observations"], errors="coerce").fillna(0).iloc[0])


def _write_validation(output: Path, result: V35ValidationResult) -> None:
    artifacts = {
        "time_holdout_predictions.csv": result.time_predictions,
        "loco_predictions.csv": result.loco_predictions,
        "ticker_scorecard_time.csv": result.time_scorecard,
        "ticker_scorecard_loco.csv": result.loco_scorecard,
        "universe_summary.csv": result.universe_summary,
        "promotion_gate.csv": result.promotion_gate,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(output / filename, index=False)


def _write_report(
    output: Path,
    bundle: StandardizedKPIBundle,
    result: V35ValidationResult,
    live_matches: int,
    macro_status: str,
) -> None:
    loco_summary = result.universe_summary.loc[
        result.universe_summary["validation"].eq("LOCO_TIME_SAFE_8Q")
    ].iloc[0]
    ready = int(bundle.coverage["status"].eq("READY").sum())
    lines = [
        "# V3.5 KPI hierarchical research report",
        "",
        "V3.4 remains the frozen production champion. V3.5 is a locked research candidate built",
        "from company operational KPIs; the rejected revenue-implied-volume shortcut is not used.",
        "",
        "## Fixed design",
        "",
        "- Common structural engine: production volume × oil/NGL/gas price",
        "- Explicit 14-company adapter registry with fixed source policies",
        "- Fixed oil-heavy / gas-heavy / mixed taxonomy with company-to-group partial pooling",
        "- Point-in-time cutoff: day 61 of each target quarter",
        "- LOCO excludes the held company's revenue-derived basis labels",
        "- No revenue-implied production fallback",
        "- Eight-quarter time holdout and time-safe LOCO",
        "",
        "## KPI source coverage",
        "",
        f"Ready companies (at least 12 actual quarters): **{ready}/14**.",
        "",
        _markdown_table(bundle.coverage),
        "",
        "## Validation summary",
        "",
        _markdown_table(result.universe_summary.round(4)),
        "",
        "## LOCO ticker scorecard",
        "",
        _markdown_table(result.loco_scorecard.round(4)),
        "",
        "## Fixed promotion gate",
        "",
        _markdown_table(result.promotion_gate),
        "",
        "## Decision",
        "",
        f"- LOCO median / mean MASE: {loco_summary['median_ticker_mase']:.3f} / {loco_summary['mean_ticker_mase']:.3f}",
        f"- Beats naive / legacy: {loco_summary['beats_naive_pct']:.1f}% / {loco_summary['beats_legacy_pct']:.1f}%",
        f"- 80% PI coverage: {loco_summary['mean_pi_80_coverage']:.1%}",
        f"- Macro residual overlay: **{macro_status}**",
        f"- Live model-change lock: **{live_matches}/20 matched actuals**",
        "- Champion: **V3.4 (unchanged)**",
        "",
        "OVV has no local operational KPI source and NOG has only eight parsed actual quarters.",
        "Neither is filled with a revenue-derived proxy; the limitation remains visible in the gate.",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "configs" / "v3_5_kpi_hierarchical.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    before = verify_champion(ROOT, "3.4")
    if args.reuse_standardized_kpis:
        bundle = _read_standardized(output)
    else:
        bundle = build_standardized_kpis(
            ROOT / "data-lake",
            args.arcana_root.resolve() / "data-lake" / "bronze" / "sec" / "fillings" / "ir",
        )
        _write_standardized(output, bundle)
    adapter_registry_frame().to_csv(output / "adapter_registry.csv", index=False)

    panel = load_e_and_p_panel(
        args.arcana_root.resolve(),
        DATA.v33 / "energy_v3_3_price_quarters.csv",
        all_tickers(),
    )
    panel.to_csv(output / "revenue_evaluation_panel.csv", index=False)
    strategy = KPIHierarchicalStrategy(
        bundle,
        panel,
        pd.read_csv(DATA.v33 / "energy_v3_3_price_quarters.csv"),
        V35StrategyConfig(
            cutoff_day=int(config["forecast_cutoff_day_of_quarter"]),
            volume_history_quarters=int(config["volume_history_quarters"]),
            partial_pooling_k=float(config["partial_pooling_k"]),
            basis_clip_log_points=float(config["basis_adjustment_clip_log_points"]),
        ),
    )
    live_matches = _live_matches(ROOT)
    validation = validate_v35(
        strategy,
        panel,
        ready_company_count=int(bundle.coverage["status"].eq("READY").sum()),
        live_matches=live_matches,
    )
    _write_validation(output, validation)

    research_pass = bool(validation.promotion_gate["research_component_gate"].iloc[0])
    macro_status = "UNLOCKED_FOR_SEPARATE_RESIDUAL_EXPERIMENT" if research_pass else "BLOCKED_KPI_COMPONENT_GATE"
    macro_frame = pd.DataFrame([{
        "status": macro_status,
        "overlay_applied_to_v35_results": False,
        "prerequisite": "Every fixed KPI component research gate must pass",
        "candidate_features": "OVX z-score; WTI curve slope; crude inventory z-score; oil rig YoY lag1",
    }])
    macro_frame.to_csv(output / "macro_overlay_status.csv", index=False)

    after = verify_champion(ROOT, "3.4")
    if before["manifest_sha256"] != after["manifest_sha256"]:
        raise RuntimeError("V3.4 champion manifest changed during V3.5 research run")
    artifact_hashes = {
        path.name: sha256_file(path)
        for path in sorted(output.glob("*.parquet"))
    }
    metadata = {
        "version": config["version"],
        "status": "RESEARCH_GATE_PASS" if research_pass else "RESEARCH_GATE_FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "v3_4_champion_manifest": before["manifest_path"],
        "v3_4_champion_manifest_sha256_before": before["manifest_sha256"],
        "v3_4_champion_manifest_sha256_after": after["manifest_sha256"],
        "v3_4_unchanged": True,
        "rejected_experiment": str(ROOT / "output" / "universe" / "experiment_status.json"),
        "macro_overlay_status": macro_status,
        "live_matched_actuals": live_matches,
        "standardized_artifact_hashes": artifact_hashes,
        "source_limitations": {
            "OVV": "No local operational IR source; no proxy fallback",
            "NOG": "Eight actual KPI quarters; below 12-quarter READY threshold",
        },
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_report(output, bundle, validation, live_matches, macro_status)

    print(validation.universe_summary.round(4).to_string(index=False))
    print("\nFixed gate")
    print(validation.promotion_gate.to_string(index=False))
    print(f"\nMacro overlay: {macro_status}")
    print(f"V3.4 champion verified unchanged: {after['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
