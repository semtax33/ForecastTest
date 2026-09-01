from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from energy_nowcast.validation.cross_section_metrics import ticker_scorecard, universe_summary
from energy_nowcast.validation.promotion_gate import apply_combined_promotion, universe_promotion_gate
from energy_nowcast.validation.universe_backtest import (
    DEFAULT_E_AND_P_UNIVERSE,
    UniverseBacktester,
    load_e_and_p_panel,
)


ROOT = Path(__file__).resolve().parent


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
    parser = argparse.ArgumentParser(description="Run E&P time and company holdout backtests")
    parser.add_argument("--arcana-root", type=Path, default=ROOT.parent / "Arcana")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "universe")
    parser.add_argument("--alpha", type=float, default=8.0)
    return parser.parse_args()


def _report(
    output: Path,
    summaries: pd.DataFrame,
    time_score: pd.DataFrame,
    loco_score: pd.DataFrame,
    gate: pd.DataFrame,
) -> None:
    lines = [
        "# E&P universe scorecard",
        "",
        "This is a 14-company cross-company diagnostic, not a replacement for the frozen V3.4 champion.",
        "The common candidate uses SEC quarterly revenue plus a lagged implied volume/basis proxy derived",
        "from revenue and the fixed WTI/Henry/propane basket. It does not claim to parse each company's",
        "production actuals or guidance. All forecasts use the same features, alpha, and gate rules.",
        "",
        "## Universe summary",
        "",
    ]
    for _, row in summaries.iterrows():
        lines.extend([
            f"### {row['validation']}",
            "",
            f"- Companies: {int(row['company_count'])}",
            f"- Quarter forecasts: {int(row['quarter_forecasts'])}",
            f"- Median / mean ticker MASE: {row['median_ticker_mase']:.3f} / {row['mean_ticker_mase']:.3f}",
            f"- MASE < 1.0 / 0.8 / 0.6: {int(row['mase_below_1_count'])} / {int(row['mase_below_0_8_count'])} / {int(row['mase_below_0_6_count'])}",
            f"- Beats naive / common legacy: {row['beats_naive_pct']:.1f}% / {row['beats_legacy_pct']:.1f}%",
            f"- Mean 80% PI coverage: {row['mean_pi_80_coverage']:.1%}",
            "",
        ])
    lines.extend([
        "## LOCO ticker scorecard", "", _markdown_table(loco_score.round(3)), "",
        "## Promotion gate", "", _markdown_table(gate), "",
    ])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    panel = load_e_and_p_panel(
        args.arcana_root.resolve(),
        ROOT / "data-lake" / "energy_v3_3_price_quarters.csv",
        DEFAULT_E_AND_P_UNIVERSE,
    )
    backtester = UniverseBacktester(alpha=args.alpha)
    time_predictions = backtester.run_time_holdout(panel)
    loco_predictions = backtester.run_loco(panel)
    time_score = ticker_scorecard(time_predictions)
    loco_score = ticker_scorecard(loco_predictions)
    gate = universe_promotion_gate(time_score, loco_score, live_forward_not_worse=None)
    time_score = apply_combined_promotion(time_score, gate)
    loco_score = apply_combined_promotion(loco_score, gate)
    summaries = pd.concat([
        universe_summary(time_score, time_predictions, "TIME_HOLDOUT"),
        universe_summary(loco_score, loco_predictions, "LOCO_TIME_SAFE"),
    ], ignore_index=True)
    artifacts = {
        "panel.csv": panel,
        "time_holdout_predictions.csv": time_predictions,
        "loco_predictions.csv": loco_predictions,
        "ticker_scorecard_time.csv": time_score,
        "ticker_scorecard_loco.csv": loco_score,
        "universe_summary.csv": summaries,
        "promotion_gate.csv": gate,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(args.output_dir / filename, index=False)
    _report(args.output_dir, summaries, time_score, loco_score, gate)
    print(summaries.round(3).to_string(index=False))
    print("\nLOCO scorecard")
    print(loco_score.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
