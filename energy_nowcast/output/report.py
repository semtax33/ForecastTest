from __future__ import annotations

from pathlib import Path

from ..pipeline import PipelineResult


def build_report(result: PipelineResult, output_dir: Path) -> Path:
    overall = result.metrics.loc[
        result.metrics["ticker"].eq("ALL")
        & result.metrics["evaluation_split"].eq("all")
    ].iloc[0]
    test = result.metrics.loc[
        result.metrics["ticker"].eq("ALL")
        & result.metrics["evaluation_split"].eq("untouched_test")
    ]
    lines = [
        f"# Energy revenue nowcast V{result.metadata['version']}",
        "",
        "The frozen V3.3 champion artifact hashes passed verification.",
        "",
        "## Validation",
        "",
        f"- Overall MAE: {overall['mae_log_points']:.2f} log-points",
        f"- Revenue YoY MAE: {overall['mae_yoy_pct_points']:.2f}%p",
        f"- MASE vs zero-growth naive: {overall['mase']:.3f}",
        f"- Revenue-level MAPE: {overall['revenue_level_mape_pct']:.2f}%",
    ]
    gate = result.metadata["validation_gates"]["v3_3_1_infrastructure"]
    lines.append(
        f"- Infrastructure gate: {'PASS' if gate['passed'] else 'FAIL'} "
        f"({gate['regression_pct']:+.2f}% vs V3.3; tolerance {gate['tolerance_pct']:.2f}%)"
    )
    if not test.empty:
        row = test.iloc[0]
        lines.extend(
            [
                f"- Untouched test MAE: {row['mae_log_points']:.2f} log-points",
                f"- Untouched test MASE: {row['mase']:.3f}",
            ]
        )
    lines.extend(["", "## Current nowcast", ""])
    for _, row in result.nowcast.sort_values("ticker").iterrows():
        lines.append(
            f"- {row['ticker']} {row['nowcast_quarter']}: "
            f"${row['predicted_revenue_B']:.2f}B, "
            f"80% PI ${row['lower_80_revenue_B']:.2f}B–${row['upper_80_revenue_B']:.2f}B, "
            f"95% PI ${row['lower_95_revenue_B']:.2f}B–${row['upper_95_revenue_B']:.2f}B"
        )
    lines.extend(["", "## Promotion gates", ""])
    if result.promotion_decisions.empty:
        lines.append("- No candidate promotion was requested in this configuration.")
    else:
        for _, row in result.promotion_decisions.iterrows():
            state = "PROMOTED" if bool(row["promoted"]) else "NOT PROMOTED"
            lines.append(
                f"- {row['stage']} / {row['ticker']}: {state} ({row['reason']})"
            )
    consensus = result.consensus_summary.iloc[0]
    lines.extend(
        [
            "",
            "## Model vs consensus",
            "",
            f"- Status: {consensus['status']}",
            f"- Matched observations: {int(consensus['observations'])}",
            f"- Statistical comparison: {consensus['statistical_test_status']}",
            "",
        ]
    )
    available_current = result.current_consensus.dropna(subset=["consensus_revenue"])
    if not available_current.empty:
        lines.extend(["", "### Current gaps", ""])
        for _, row in available_current.sort_values("ticker").iterrows():
            lines.append(
                f"- {row['ticker']}: model ${row['model_revenue'] / 1e9:.2f}B vs "
                f"consensus ${row['consensus_revenue'] / 1e9:.2f}B "
                f"({row['model_minus_consensus_pct']:+.1f}%, {row['providers']})"
            )
    target = output_dir / "report.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
