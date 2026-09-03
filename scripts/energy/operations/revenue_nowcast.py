from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.data.consensus import load_arcana_consensus
from energy_nowcast.operations.champion import verify_champion
from energy_nowcast.operations.scorecard import build_live_scorecard
from energy_nowcast.operations.snapshot import capture_v34_snapshots
from energy_nowcast.operations.store import (
    connect_store,
    ingest_consensus_vintages,
    insert_actual_release,
    read_table,
    write_store_metadata,
)
from energy_nowcast.validation.promotion_gate import seven_condition_promotion_gate


from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
UNIVERSE = ("EOG", "COP", "FANG", "DVN", "EQT", "AR", "RRC", "MTDR", "PR", "OVV", "CNX", "SM", "MGY", "NOG")


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        values = ["" if pd.isna(row[column]) else str(row[column]) for column in columns]
        lines.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run frozen V3.4 forecast operations")
    parser.add_argument("--db", type=Path, default=ROOT / "output" / "operations" / "forecast_store.sqlite")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "operations")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 8, 31))
    parser.add_argument("--timing-label", default="FROZEN_BASELINE")
    parser.add_argument("--actuals-csv", type=Path, default=None)
    return parser.parse_args()


def _ingest_actuals(connection: object, path: Path) -> int:
    frame = pd.read_csv(path)
    required = {"ticker", "quarter", "actual_revenue", "release_date"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Actuals CSV missing columns: {sorted(missing)}")
    count = 0
    for _, row in frame.iterrows():
        status = insert_actual_release(connection, {
            "ticker": str(row["ticker"]).upper(),
            "quarter": str(row["quarter"]),
            "actual_revenue": float(row["actual_revenue"]),
            "release_date": date.fromisoformat(str(row["release_date"])).isoformat(),
            "source_path": str(row.get("source_path", path)),
        })
        count += status == "INSERTED"
    return count


def _dashboard(score_summary: pd.DataFrame) -> pd.DataFrame:
    metrics = pd.read_csv(ROOT / "output" / "v3_4" / "metrics.csv")
    overall = metrics.loc[metrics["ticker"].eq("ALL") & metrics["evaluation_split"].eq("all")].iloc[0]
    intervals = pd.read_csv(ROOT / "output" / "v3_4" / "interval_calibration.csv")
    coverage = intervals.loc[
        intervals["interval_level"].eq(0.8) & intervals["evaluation_split"].eq("all"),
        "empirical_coverage",
    ]
    live = score_summary.iloc[0]
    return pd.DataFrame([
        {"metric": "MASE", "value": overall["mase"], "status": "V3.4_FROZEN_BACKTEST"},
        {"metric": "Revenue-level MAPE", "value": overall["revenue_level_mape_pct"], "status": "V3.4_FROZEN_BACKTEST"},
        {"metric": "80% PI coverage", "value": float(coverage.iloc[0]) if not coverage.empty else np.nan, "status": "V3.4_FROZEN_BACKTEST"},
        {"metric": "Model vs consensus MAE", "value": live["model_mae"], "status": live["model_change_lock"]},
        {"metric": "Model-consensus directional hit", "value": live["directional_hit_rate"], "status": live["model_change_lock"]},
    ])


def _model_change_gate(score_summary: pd.DataFrame) -> pd.DataFrame:
    """Materialize the seven-condition policy even when no candidate exists."""
    champion = {"mase": 0.5315818422629403, "revenue_mape_pct": 8.733009256400173}
    candidate = {
        "mase": np.nan,
        "revenue_mape_pct": np.nan,
        "observations": 0,
        "untouched_not_worse": False,
        "untouched_status": "NO_CANDIDATE_REGISTERED",
        "pi_80_coverage": np.nan,
    }
    ticker_state = pd.DataFrame({"improvement_log_points": [np.nan]})
    return seven_condition_promotion_gate(
        champion,
        candidate,
        ticker_state,
        score_summary.iloc[0].to_dict(),
    )


def _write_report(
    output_dir: Path,
    snapshots: pd.DataFrame,
    score_summary: pd.DataFrame,
    dashboard: pd.DataFrame,
    gate: pd.DataFrame,
    vintage_counts: dict[str, int],
    total_vintages: int,
) -> None:
    score = score_summary.iloc[0]
    lines = [
        "# V3.4 live-forward operations",
        "",
        "The frozen champion passed code, config, input, schema, and model-artifact hash verification.",
        f"The consensus vintage store contains {total_vintages} rows "
        f"({vintage_counts['inserted']} new this run) and matched "
        f"{int(score['matched_observations'])} released actuals.",
        f"Model changes are **{score['model_change_lock']}**; {int(score['observations_needed'])} more matched observations are required.",
        "",
        "`EDGE` in this report means model-consensus disagreement only. It is not investment alpha or a buy/sell recommendation.",
        "",
        "## Current decisions",
        "",
    ]
    for _, row in snapshots.sort_values("ticker").iterrows():
        lines.append(
            f"- {row['ticker']} {row['quarter']}: {row['decision']} "
            f"(model-consensus {row['disagreement_gap_pct']:+.1f}%)"
        )
    lines.extend([
        "",
        "## Dashboard",
        "",
        _markdown_table(dashboard),
        "",
        "## Seven-condition candidate gate",
        "",
        _markdown_table(gate),
        "",
    ])
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = verify_champion(ROOT)
    arcana_consensus = ROOT.parent / "Arcana" / "data-lake" / "bronze" / "consensus"
    consensus, coverage = load_arcana_consensus(arcana_consensus, UNIVERSE)
    with connect_store(args.db) as connection:
        vintage_counts = ingest_consensus_vintages(connection, consensus, coverage)
        snapshots = capture_v34_snapshots(connection, ROOT, args.as_of, args.timing_label)
        actual_count = _ingest_actuals(connection, args.actuals_csv) if args.actuals_csv else 0
        score_rows, score_summary = build_live_scorecard(connection)
        write_store_metadata(connection, "champion_manifest_sha256", manifest["manifest_sha256"])
        write_store_metadata(connection, "model_change_policy", {"minimum_matched_observations": 20, "locked": int(score_summary.iloc[0]["matched_observations"]) < 20})
        for table in ("consensus_vintages", "consensus_source_coverage", "forecast_snapshots", "actual_releases"):
            read_table(connection, table).to_csv(args.output_dir / f"{table}.csv", index=False)
    snapshots.to_csv(args.output_dir / "capture_result.csv", index=False)
    score_rows.to_csv(args.output_dir / "live_scorecard.csv", index=False)
    score_summary.to_csv(args.output_dir / "live_scorecard_summary.csv", index=False)
    dashboard = _dashboard(score_summary)
    gate = _model_change_gate(score_summary)
    dashboard.to_csv(args.output_dir / "dashboard.csv", index=False)
    gate.to_csv(args.output_dir / "model_change_gate.csv", index=False)
    total_vintages = len(pd.read_csv(args.output_dir / "consensus_vintages.csv"))
    _write_report(
        args.output_dir,
        snapshots,
        score_summary,
        dashboard,
        gate,
        vintage_counts,
        total_vintages,
    )
    print(f"Verified frozen champion: {manifest['manifest_sha256']}")
    print(f"Consensus vintages: {vintage_counts}; new actuals: {actual_count}")
    print(score_summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
