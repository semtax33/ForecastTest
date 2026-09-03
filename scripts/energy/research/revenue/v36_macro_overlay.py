from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from energy_nowcast.operations.champion import sha256_file, verify_champion
from energy_nowcast.research.v35.strategy import KPIHierarchicalStrategy, V35StrategyConfig
from energy_nowcast.research.v353.validation import validate_grouped_component
from energy_nowcast.research.v36.benchmark import verify_research_champion
from energy_nowcast.research.v36.macro_data import (
    build_macro_feature_panel,
    load_macro_snapshot,
    refresh_macro_snapshot,
)
from energy_nowcast.research.v36.validation import (
    MacroCandidateResult,
    evaluate_macro_candidate,
    passing_pairwise_combinations,
)
from energy_nowcast.validation.cross_section_metrics import ticker_scorecard, universe_summary
from scripts.energy.research.revenue.v353_grouped_component import _load_inputs


from equity_platform.data_catalog import DATA
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
DEFAULT_OUTPUT = ROOT / "output" / "v3_6_macro_overlay_research"
SNAPSHOT = DATA.macro_snapshot


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V3.6 group macro research")
    parser.add_argument(
        "--refresh-macro-data",
        action="store_true",
        help="Refresh the versioned local macro snapshot from official sources",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _assert_frozen_baseline(actual: pd.DataFrame, filename: str) -> None:
    frozen = pd.read_csv(ROOT / "output" / "v3_5_3_grouped_component" / filename)
    keys = ["ticker", "quarter"]
    columns = ["candidate_prediction", "legacy_prediction", "actual_log_yoy"]
    left = actual.sort_values(keys).reset_index(drop=True)
    right = frozen.sort_values(keys).reset_index(drop=True)
    if left[keys].astype(str).to_dict("records") != right[keys].astype(str).to_dict("records"):
        raise AssertionError(f"V3.5.3 {filename} test keys changed")
    for column in columns:
        if not np.allclose(
            pd.to_numeric(left[column], errors="coerce"),
            pd.to_numeric(right[column], errors="coerce"),
            equal_nan=True,
        ):
            raise AssertionError(f"V3.5.3 {filename} {column} changed")


def _feature_eligibility(
    baseline: pd.DataFrame,
    macro: pd.DataFrame,
    groups: dict[str, list[str]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group, features in groups.items():
        if group == "gas_heavy":
            rows.append({
                "group": group,
                "feature": "ALL_MACRO_FEATURES",
                "eligible_test_rows": 0,
                "baseline_test_rows": int(baseline["group"].eq(group).sum()),
                "coverage_share": 0.0,
                "policy": "PROHIBITED_V3_5_3_GAS_GATE_FAILED",
            })
            continue
        group_rows = baseline.loc[
            baseline["group"].eq(group)
            & baseline["candidate_prediction"].notna(),
            ["ticker", "quarter"],
        ]
        qualified = group_rows.groupby("ticker").size().loc[lambda count: count.ge(8)].index
        group_rows = group_rows.loc[group_rows["ticker"].isin(qualified)].merge(
            macro, on="quarter", how="left"
        )
        for feature in features:
            available = group_rows[feature].notna()
            observations = (
                group_rows.assign(_available=available)
                .groupby("ticker")["_available"]
                .sum()
            )
            rows.append({
                "group": group,
                "feature": feature,
                "eligible_test_rows": int(available.sum()),
                "baseline_test_rows": len(group_rows),
                "coverage_share": float(available.mean()) if len(group_rows) else 0.0,
                "minimum_rows_per_baseline_ticker": (
                    int(observations.min()) if len(observations) else 0
                ),
                "stale_or_missing_test_rows": int((~available).sum()),
                "policy": "POINT_IN_TIME_FRESHNESS_REQUIRED",
            })
    return pd.DataFrame(rows)


def _evaluate(
    baseline,
    panel: pd.DataFrame,
    macro: pd.DataFrame,
    group: str,
    features: tuple[str, ...],
    config: dict[str, object],
) -> tuple[MacroCandidateResult, MacroCandidateResult]:
    model = config["model"]
    kwargs = {
        "alpha": float(model["ridge_alpha"]),
        "minimum_training_observations": int(model["minimum_training_observations"]),
        "clip_log_points": float(model["overlay_clip_log_points"]),
    }
    time = evaluate_macro_candidate(
        baseline.time_predictions,
        baseline.time_scorecard,
        panel,
        baseline.candidate_history,
        macro,
        group,
        features,
        "TIME_HOLDOUT_8Q_PRIMARY_V36",
        **kwargs,
    )
    loco = evaluate_macro_candidate(
        baseline.loco_predictions,
        baseline.loco_scorecard,
        panel,
        baseline.candidate_history,
        macro,
        group,
        features,
        "LOCO_TIME_SAFE_8Q_COLD_START_V36",
        **kwargs,
    )
    return time, loco


def _tag(result: MacroCandidateResult, stage: str) -> MacroCandidateResult:
    predictions = result.predictions.copy()
    score = result.scorecard.copy()
    gate = result.gate.copy()
    for frame in (predictions, score, gate):
        frame["research_stage"] = stage
    return MacroCandidateResult(predictions, score, gate)


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _assemble(
    baseline: pd.DataFrame,
    selected: dict[str, MacroCandidateResult],
    validation: str,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for group in ("oil_heavy", "mixed", "gas_heavy"):
        if group in selected:
            part = selected[group].predictions.copy()
            part["selected_macro_candidate"] = part["macro_features"]
        else:
            part = baseline.loc[baseline["group"].eq(group)].copy()
            part["selected_macro_candidate"] = "NONE_V3_5_3_BASELINE"
        parts.append(part)
    result = pd.concat(parts, ignore_index=True, sort=False).sort_values(
        ["quarter_ordinal", "ticker"]
    ).reset_index(drop=True)
    result["validation"] = validation
    return result


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No candidates were eligible for this stage._"
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
    single_gates: pd.DataFrame,
    combination_gates: pd.DataFrame,
    decisions: pd.DataFrame,
    summary: pd.DataFrame,
    eligibility: pd.DataFrame,
) -> None:
    gate_columns = [
        "group", "features", "candidate_median_mase", "candidate_mean_mase",
        "baseline_no_regression_share", "severe_regression_count", "candidate_pi80",
        "candidate_direction", "minimum_candidate_forecasts", "candidate_gate",
    ]
    lines = [
        "# V3.6 macro-overlay research",
        "",
        "V3.5.3 is the frozen grouped research benchmark. Every macro variable is",
        "tested alone by group under the same TIME and LOCO splits. Gas macro remains prohibited.",
        "Pairwise combinations are generated only from single variables that pass every TIME gate.",
        "",
        "## Single-variable TIME gates",
        "",
        _markdown_table(single_gates[gate_columns].round(4)),
        "",
        "## Eligible pairwise combinations",
        "",
        _markdown_table(combination_gates[gate_columns].round(4) if not combination_gates.empty else combination_gates),
        "",
        "## Group decision",
        "",
        _markdown_table(decisions),
        "",
        "## Selected research result",
        "",
        _markdown_table(summary.round(4)),
        "",
        "## Point-in-time feature coverage",
        "",
        _markdown_table(eligibility.round(4)),
        "",
        "V3.4 remains the frozen production champion. No live-model change is allowed at 0/20 matches.",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "configs" / "v3_6_macro_overlay_research.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    v34_before = verify_champion(ROOT, "3.4")
    v353_before = verify_research_champion(ROOT, "3.5.3")
    if args.refresh_macro_data:
        refresh_macro_snapshot(
            SNAPSHOT, DATA.v33 / "energy_v3_3_eia_prices_daily.csv"
        )
    raw_macro = load_macro_snapshot(SNAPSHOT)

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
    baseline = validate_grouped_component(strategy, panel, live_matches=0)
    _assert_frozen_baseline(baseline.time_predictions, "time_holdout_predictions.csv")
    _assert_frozen_baseline(baseline.loco_predictions, "loco_predictions.csv")
    expected = v353_before["expected_time_metrics"]
    actual = baseline.universe_summary.iloc[0]
    for metric, value in expected.items():
        if not np.isclose(float(actual[metric]), float(value), atol=1e-12, rtol=0.0):
            raise AssertionError(f"Frozen V3.5.3 metric changed: {metric}")

    macro = build_macro_feature_panel(
        panel["quarter"].astype(str).unique().tolist(), raw_macro
    )
    groups: dict[str, list[str]] = config["groups"]
    eligibility = _feature_eligibility(baseline.time_predictions, macro, groups)

    singles: dict[tuple[str, str, str], MacroCandidateResult] = {}
    single_time: list[pd.DataFrame] = []
    single_loco: list[pd.DataFrame] = []
    single_time_scores: list[pd.DataFrame] = []
    single_loco_scores: list[pd.DataFrame] = []
    single_time_gates: list[pd.DataFrame] = []
    single_loco_gates: list[pd.DataFrame] = []
    for group in ("oil_heavy", "mixed"):
        for feature in groups[group]:
            time, loco = _evaluate(baseline, panel, macro, group, (feature,), config)
            time, loco = _tag(time, "SINGLE"), _tag(loco, "SINGLE")
            singles[(group, feature, "TIME")] = time
            singles[(group, feature, "LOCO")] = loco
            single_time.append(time.predictions)
            single_loco.append(loco.predictions)
            single_time_scores.append(time.scorecard)
            single_loco_scores.append(loco.scorecard)
            single_time_gates.append(time.gate)
            single_loco_gates.append(loco.gate)
    time_gate_frame = _concat(single_time_gates)
    loco_gate_frame = _concat(single_loco_gates)

    combinations: dict[tuple[str, str, str], MacroCandidateResult] = {}
    combo_time: list[pd.DataFrame] = []
    combo_loco: list[pd.DataFrame] = []
    combo_time_scores: list[pd.DataFrame] = []
    combo_loco_scores: list[pd.DataFrame] = []
    combo_time_gates: list[pd.DataFrame] = []
    combo_loco_gates: list[pd.DataFrame] = []
    for group in ("oil_heavy", "mixed"):
        for features in passing_pairwise_combinations(time_gate_frame, group):
            time, loco = _evaluate(baseline, panel, macro, group, features, config)
            time, loco = _tag(time, "COMBINATION"), _tag(loco, "COMBINATION")
            label = "+".join(features)
            combinations[(group, label, "TIME")] = time
            combinations[(group, label, "LOCO")] = loco
            combo_time.append(time.predictions)
            combo_loco.append(loco.predictions)
            combo_time_scores.append(time.scorecard)
            combo_loco_scores.append(loco.scorecard)
            combo_time_gates.append(time.gate)
            combo_loco_gates.append(loco.gate)
    combo_time_gate_frame = _concat(combo_time_gates)
    combo_loco_gate_frame = _concat(combo_loco_gates)
    single_time_prediction_frame = _concat(single_time)
    single_loco_prediction_frame = _concat(single_loco)
    single_time_score_frame = _concat(single_time_scores)
    single_loco_score_frame = _concat(single_loco_scores)
    combo_time_prediction_frame = _concat(combo_time)
    combo_loco_prediction_frame = _concat(combo_loco)
    combo_time_score_frame = _concat(combo_time_scores)
    combo_loco_score_frame = _concat(combo_loco_scores)
    if combo_time_gate_frame.empty:
        combo_time_gate_frame = time_gate_frame.iloc[0:0].copy()
        combo_loco_gate_frame = loco_gate_frame.iloc[0:0].copy()
        combo_time_prediction_frame = single_time_prediction_frame.iloc[0:0].copy()
        combo_loco_prediction_frame = single_loco_prediction_frame.iloc[0:0].copy()
        combo_time_score_frame = single_time_score_frame.iloc[0:0].copy()
        combo_loco_score_frame = single_loco_score_frame.iloc[0:0].copy()

    all_time_gates = pd.concat(
        [frame for frame in (time_gate_frame, combo_time_gate_frame) if not frame.empty],
        ignore_index=True,
    )
    selected_time: dict[str, MacroCandidateResult] = {}
    selected_loco: dict[str, MacroCandidateResult] = {}
    decision_rows: list[dict[str, object]] = []
    for group in ("oil_heavy", "mixed"):
        passing = all_time_gates.loc[
            all_time_gates["group"].eq(group)
            & all_time_gates["candidate_gate"].eq(True)  # noqa: E712
        ].sort_values(["candidate_median_mase", "candidate_mean_mase", "features"])
        if passing.empty:
            decision_rows.append({
                "group": group,
                "selected_macro": "NONE",
                "research_model": "V3.5.3_GROUPED",
                "decision": "RETAIN_RESEARCH_BENCHMARK",
                "production_model": "V3.4_FROZEN",
            })
            continue
        label = str(passing.iloc[0]["features"])
        source = combinations if "+" in label else singles
        selected_time[group] = source[(group, label, "TIME")]
        selected_loco[group] = source[(group, label, "LOCO")]
        decision_rows.append({
            "group": group,
            "selected_macro": label,
            "research_model": "V3.6_MACRO_OVERLAY_RESEARCH",
            "decision": "RESEARCH_GATE_PASS",
            "production_model": "V3.4_FROZEN",
        })
    decision_rows.append({
        "group": "gas_heavy",
        "selected_macro": "PROHIBITED",
        "research_model": "V3.5.3_LEGACY",
        "decision": "GAS_MACRO_BLOCKED",
        "production_model": "V3.4_FROZEN",
    })
    decisions = pd.DataFrame(decision_rows)

    selected_time_predictions = _assemble(
        baseline.time_predictions,
        selected_time,
        "TIME_HOLDOUT_8Q_PRIMARY_V36_SELECTED",
    )
    selected_loco_predictions = _assemble(
        baseline.loco_predictions,
        selected_loco,
        "LOCO_TIME_SAFE_8Q_COLD_START_V36_SELECTED",
    )
    selected_time_score = ticker_scorecard(selected_time_predictions, minimum_observations=8)
    selected_loco_score = ticker_scorecard(selected_loco_predictions, minimum_observations=8)
    selected_summary = pd.concat([
        universe_summary(
            selected_time_score,
            selected_time_predictions,
            "TIME_HOLDOUT_8Q_PRIMARY_V36_SELECTED",
        ),
        universe_summary(
            selected_loco_score,
            selected_loco_predictions,
            "LOCO_TIME_SAFE_8Q_COLD_START_V36_SELECTED",
        ),
    ], ignore_index=True)

    artifacts = {
        "macro_feature_panel.csv": macro,
        "macro_feature_eligibility.csv": eligibility,
        "single_time_predictions.csv": single_time_prediction_frame,
        "single_loco_predictions.csv": single_loco_prediction_frame,
        "single_time_scorecards.csv": single_time_score_frame,
        "single_loco_scorecards.csv": single_loco_score_frame,
        "single_time_gates.csv": time_gate_frame,
        "single_loco_diagnostics.csv": loco_gate_frame,
        "combination_time_predictions.csv": combo_time_prediction_frame,
        "combination_loco_predictions.csv": combo_loco_prediction_frame,
        "combination_time_scorecards.csv": combo_time_score_frame,
        "combination_loco_scorecards.csv": combo_loco_score_frame,
        "combination_time_gates.csv": combo_time_gate_frame,
        "combination_loco_diagnostics.csv": combo_loco_gate_frame,
        "selected_time_predictions.csv": selected_time_predictions,
        "selected_loco_predictions.csv": selected_loco_predictions,
        "selected_time_scorecard.csv": selected_time_score,
        "selected_loco_scorecard.csv": selected_loco_score,
        "selected_universe_summary.csv": selected_summary,
        "group_decision.csv": decisions,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(output / filename, index=False)
    _write_report(
        output,
        time_gate_frame,
        combo_time_gate_frame,
        decisions,
        selected_summary,
        eligibility,
    )

    v34_after = verify_champion(ROOT, "3.4")
    v353_after = verify_research_champion(ROOT, "3.5.3")
    if v34_before["manifest_sha256"] != v34_after["manifest_sha256"]:
        raise RuntimeError("V3.4 changed during V3.6 research")
    if v353_before["manifest_sha256"] != v353_after["manifest_sha256"]:
        raise RuntimeError("V3.5.3 changed during V3.6 research")
    macro_metadata = json.loads((SNAPSHOT / "metadata.json").read_text(encoding="utf-8"))
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_benchmark": "V3.5.3_FROZEN",
        "research_benchmark_manifest_sha256": v353_after["manifest_sha256"],
        "production_champion": "V3.4_FROZEN",
        "production_champion_manifest_sha256": v34_after["manifest_sha256"],
        "production_champion_changed": False,
        "live_model_change_matches": "0/20",
        "macro_snapshot_sha256": macro_metadata["macro_series_sha256"],
        "macro_snapshot_retrieved_at_utc": macro_metadata["retrieved_at_utc"],
        "single_candidates_tested": len(time_gate_frame),
        "single_candidates_passed": int(time_gate_frame["candidate_gate"].eq(True).sum()),
        "combinations_tested": len(combo_time_gate_frame),
        "selected_group_overlays": {
            row["group"]: row["selected_macro"] for _, row in decisions.iterrows()
        },
        "gas_macro_tested": False,
        "config_sha256": sha256_file(config_path),
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(time_gate_frame[[
        "group", "features", "candidate_median_mase", "candidate_mean_mase",
        "baseline_no_regression_share", "severe_regression_count",
        "candidate_pi80", "candidate_direction", "candidate_gate",
    ]].round(4).to_string(index=False))
    print("\nGroup decisions\n", decisions.to_string(index=False))
    print("\nSelected summary\n", selected_summary.round(4).to_string(index=False))
    print(f"\nV3.5.3 unchanged: {v353_after['manifest_sha256']}")
    print(f"V3.4 unchanged: {v34_after['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
