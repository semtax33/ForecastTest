from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.operations.champion import sha256_file, verify_champion
from energy_nowcast.research.v35.adapters import StandardizedKPIBundle
from energy_nowcast.research.v35.strategy import KPIHierarchicalStrategy, V35StrategyConfig
from energy_nowcast.research.v353.validation import validate_grouped_component


from equity_platform.data_catalog import DATA
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
V352_OUTPUT = ROOT / "output" / "v3_5_2_clean_component"
DEFAULT_OUTPUT = ROOT / "output" / "v3_5_3_grouped_component"


def _live_matches() -> int:
    path = ROOT / "output" / "operations" / "live_scorecard_summary.csv"
    if not path.exists():
        return 0
    frame = pd.read_csv(path)
    return int(pd.to_numeric(frame.get("matched_observations"), errors="coerce").fillna(0).iloc[0])


def _load_inputs() -> tuple[StandardizedKPIBundle, pd.DataFrame, pd.DataFrame]:
    required = [
        V352_OUTPUT / "production_actuals.parquet",
        V352_OUTPUT / "production_guidance.parquet",
        V352_OUTPUT / "realized_prices.parquet",
        V352_OUTPUT / "source_coverage.csv",
        V352_OUTPUT / "audited_revenue_panel.parquet",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "V3.5.2 fixed inputs are required before V3.5.3: " + ", ".join(missing)
        )
    bundle = StandardizedKPIBundle(
        production_actuals=pd.read_parquet(required[0]),
        production_guidance=pd.read_parquet(required[1]),
        realized_prices=pd.read_parquet(required[2]),
        coverage=pd.read_csv(required[3]),
    )
    panel = pd.read_parquet(required[4])
    prices = pd.read_csv(DATA.v33 / "energy_v3_3_price_quarters.csv")
    return bundle, panel, prices


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


def _write_report(
    output: Path,
    summary: pd.DataFrame,
    groups: pd.DataFrame,
    gate: pd.DataFrame,
    comparison: pd.DataFrame,
) -> None:
    compact_groups = groups[[
        "group",
        "time_evaluable_tickers",
        "time_median_mase",
        "time_mean_mase",
        "time_legacy_no_regression_count",
        "time_severe_regression_count",
        "group_component_gate",
        "active_model",
        "macro_research_unlocked",
    ]].copy()
    lines = [
        "# V3.5.3 grouped-component report",
        "",
        "The V3.5.2 clean component is evaluated independently by fixed E&P group.",
        "Passing groups use the clean component; failing groups retain the legacy structural model.",
        "No threshold was relaxed and no new feature was added to this experiment.",
        "",
        "## Group promotion",
        "",
        _markdown_table(compact_groups.round(4)),
        "",
        "## Active grouped-model results",
        "",
        _markdown_table(summary.round(4)),
        "",
        "## V3.5.2 clean versus V3.5.3 selected",
        "",
        _markdown_table(comparison.round(4)),
        "",
        "## Grouped success gate",
        "",
        _markdown_table(gate),
        "",
        "## Decision",
        "",
        "- Macro research is unlocked only for groups whose component gate passes.",
        "- Gas-heavy retains legacy until a separate gas-basis model passes its own gate.",
        "- The V3.4 production champion remains frozen and byte-verified.",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    output = DEFAULT_OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "configs" / "v3_5_3_grouped_component.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    before = verify_champion(ROOT, "3.4")
    bundle, panel, prices = _load_inputs()
    strategy = KPIHierarchicalStrategy(
        bundle,
        panel,
        prices,
        V35StrategyConfig(
            cutoff_day=int(config["forecast_cutoff_day_of_quarter"]),
            use_company_basis=False,
        ),
    )
    result = validate_grouped_component(strategy, panel, live_matches=_live_matches())

    active = result.group_promotion.set_index("group")["active_model"].to_dict()
    expected = {
        "oil_heavy": "CLEAN_COMPONENT",
        "gas_heavy": "LEGACY",
        "mixed": "CLEAN_COMPONENT",
    }
    if active != expected:
        raise AssertionError(f"Unexpected group selection: {active}")
    for predictions in (result.time_predictions, result.loco_predictions):
        gas = predictions["group"].eq("gas_heavy")
        clean = ~gas & predictions["candidate_status"].eq("AVAILABLE")
        if not np.allclose(
            predictions.loc[gas, "candidate_prediction"],
            predictions.loc[gas, "legacy_prediction"],
            equal_nan=True,
        ):
            raise AssertionError("Gas-heavy did not roll back exactly to legacy")
        if not np.allclose(
            predictions.loc[clean, "candidate_prediction"],
            predictions.loc[clean, "clean_component_prediction"],
            equal_nan=True,
        ):
            raise AssertionError("Passing group clean-component predictions changed")

    old_summary = pd.read_csv(V352_OUTPUT / "universe_summary.csv").iloc[0]
    new_summary = result.universe_summary.iloc[0]
    comparison = pd.DataFrame([
        {
            "metric": metric,
            "v3_5_2_clean": old_summary[old_column],
            "v3_5_3_grouped": new_summary[new_column],
            "change": float(new_summary[new_column]) - float(old_summary[old_column]),
        }
        for metric, old_column, new_column in (
            ("median_ticker_mase", "median_ticker_mase", "median_ticker_mase"),
            ("mean_ticker_mase", "mean_ticker_mase", "mean_ticker_mase"),
            ("mase_below_1_share", "mase_below_1_share", "mase_below_1_share"),
            ("legacy_no_regression_share", "legacy_no_regression_share", "legacy_no_regression_share"),
            ("median_improvement_log_points", "median_improvement_log_points", "median_improvement_log_points"),
            ("pi_80_coverage", "mean_pi_80_coverage", "mean_pi_80_coverage"),
            ("directional_hit_rate", "mean_directional_hit_rate", "mean_directional_hit_rate"),
            ("revenue_wape_pct", "overall_revenue_wape_pct", "overall_revenue_wape_pct"),
            ("revenue_median_ape_pct", "overall_revenue_median_ape_pct", "overall_revenue_median_ape_pct"),
        )
    ])
    artifacts = {
        "time_holdout_predictions.csv": result.time_predictions,
        "loco_predictions.csv": result.loco_predictions,
        "ticker_scorecard_time.csv": result.time_scorecard,
        "ticker_scorecard_loco.csv": result.loco_scorecard,
        "clean_ticker_scorecard_time.csv": result.clean_time_scorecard,
        "clean_ticker_scorecard_loco.csv": result.clean_loco_scorecard,
        "universe_summary.csv": result.universe_summary,
        "group_promotion.csv": result.group_promotion,
        "grouped_success_gate.csv": result.grouped_success_gate,
        "v352_v353_comparison.csv": comparison,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(output / filename, index=False)
    pd.DataFrame([
        {
            "group": row["group"],
            "component_model": row["active_model"],
            "macro_research_status": (
                "UNLOCKED" if row["macro_research_unlocked"] else "BLOCKED"
            ),
            "macro_applied_to_results": False,
        }
        for _, row in result.group_promotion.iterrows()
    ]).to_csv(output / "group_overlay_status.csv", index=False)
    _write_report(output, result.universe_summary, result.group_promotion, result.grouped_success_gate, comparison)

    after = verify_champion(ROOT, "3.4")
    if before["manifest_sha256"] != after["manifest_sha256"]:
        raise RuntimeError("V3.4 changed during V3.5.3 grouped research")
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "grouped_component_gate": bool(result.grouped_success_gate["grouped_component_gate"].iloc[0]),
        "active_models": active,
        "macro_research_unlocked_groups": result.group_promotion.loc[
            result.group_promotion["macro_research_unlocked"].eq(True), "group"  # noqa: E712
        ].tolist(),
        "macro_applied_to_results": False,
        "production_champion": "V3.4_FROZEN",
        "v3_4_unchanged": True,
        "v3_4_manifest_sha256": after["manifest_sha256"],
        "config_sha256": sha256_file(config_path),
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(result.group_promotion[[
        "group", "time_median_mase", "time_legacy_no_regression_share",
        "time_severe_regression_count", "group_component_gate", "active_model",
        "macro_research_unlocked",
    ]].to_string(index=False))
    print("\n", result.universe_summary.round(4).to_string(index=False))
    print("\n", result.grouped_success_gate.to_string(index=False))
    print(f"\nV3.4 unchanged: {after['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
