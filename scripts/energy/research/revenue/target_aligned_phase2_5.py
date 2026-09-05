from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path
import tomllib

import numpy as np
import pandas as pd

from energy_nowcast.core.company_kpi import (
    load_company_kpis,
    select_company_kpis_for_targets,
)
from energy_nowcast.core.platform import validate_subindustry
from energy_nowcast.core.proxy_benchmark import verify_proxy_benchmark
from energy_nowcast.operations.champion import sha256_file, verify_champion
from energy_nowcast.research.phase25.benchmark import verify_refining_kpi_benchmark
from energy_nowcast.research.phase25.macro_overlay import (
    ResidualCandidateResult,
    attach_target_aligned_macro_features,
    evaluate_residual_candidate,
)
from energy_nowcast.research.phase25.router import (
    energy_sector_scorecard,
    ep_subindustry,
    standardize_ebitda_predictions,
    standardize_revenue_predictions,
)
from energy_nowcast.research.phase25.target_data import (
    audit_midstream_ebitda_gold,
    build_midstream_ebitda_panel,
    extract_midstream_adjusted_ebitda,
    scan_integrated_forward_signals,
)
from energy_nowcast.research.v36.benchmark import verify_research_champion
from energy_nowcast.research.v36.macro_data import (
    build_macro_feature_panel,
    load_macro_snapshot,
    refresh_macro_snapshot,
)
from equity_platform.validation.cross_section_metrics import (
    ticker_scorecard,
    universe_summary,
)


from equity_platform.data_catalog import DATA
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
CONFIG = ROOT / "configs" / "phase2_5_target_aligned_research.toml"
OUTPUT = ROOT / "output" / "phase2_5_target_aligned_research"
P21 = ROOT / "benchmarks" / "phase2_1_refining_kpi"
PROXY_OUTPUT = ROOT / "output" / "phase2_4_structural_research"
KPI_SNAPSHOT = DATA.company_kpi_snapshot
PARSER_AUDIT = ROOT / "output" / "kpi_parser_gold_audit"
MACRO_SNAPSHOT = DATA.macro_snapshot
EBITDA_GOLD = ROOT / "configs" / "phase2_5_midstream_ebitda_gold_labels.csv"
V353_OUTPUT = ROOT / "output" / "v3_5_3_grouped_component"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run target-aligned Phase 2-5 energy research"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--refresh-macro-data", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    return frame.to_markdown(index=False)


def _parser_gate_status() -> tuple[pd.DataFrame, str]:
    gate_path = PARSER_AUDIT / "parser_quality_gate.csv"
    metadata_path = PARSER_AUDIT / "metadata.json"
    if not gate_path.exists() or not metadata_path.exists():
        return pd.DataFrame(), "MISSING_FAIL_CLOSED"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    actual = sha256_file(KPI_SNAPSHOT / "company_kpi_quarterly.csv")
    if metadata.get("post_snapshot_sha256") != actual:
        return pd.DataFrame(), "STALE_SNAPSHOT_FAIL_CLOSED"
    gates = pd.read_csv(gate_path)
    if not gates["parser_quality_gate"].astype(bool).all():
        return gates, "QUALITY_GATE_FAILED"
    return gates, "CURRENT"


def _candidate_gate(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    label: str,
    parser_gate: bool,
    required_tickers: int | None = None,
) -> pd.DataFrame:
    baseline_score = ticker_scorecard(baseline, minimum_observations=8)
    candidate_score = ticker_scorecard(candidate, minimum_observations=8)
    comparison = baseline_score[[
        "ticker",
        "mase",
        "candidate_mae_log_points",
        "directional_hit_rate",
        "pi_80_coverage",
    ]].rename(
        columns={
            "mase": "baseline_mase",
            "candidate_mae_log_points": "baseline_mae",
            "directional_hit_rate": "baseline_direction",
            "pi_80_coverage": "baseline_pi80",
        }
    ).merge(
        candidate_score[[
            "ticker",
            "observations",
            "mase",
            "candidate_mae_log_points",
            "directional_hit_rate",
            "pi_80_coverage",
        ]],
        on="ticker",
        how="left",
    )
    qualified = comparison.loc[comparison["observations"].ge(8)].copy()
    delta = qualified["candidate_mae_log_points"] - qualified["baseline_mae"]
    required = required_tickers if required_tickers is not None else len(comparison)
    checks = {
        "minimum_8_forecasts_per_required_ticker": (
            len(qualified) == required and required > 0
        ),
        "median_mase_improves": (
            qualified["mase"].median() < comparison["baseline_mase"].median()
        ),
        "mean_mase_no_worse": (
            qualified["mase"].mean() <= comparison["baseline_mase"].mean() + 1e-12
        ),
        "baseline_no_regression_share_at_least_80pct": (
            float(delta.le(0.0).mean()) >= 0.80 if len(delta) else False
        ),
        "severe_regression_count_zero": int(delta.gt(2.0).sum()) == 0,
        "pi80_between_75_85pct": (
            0.75 <= float(qualified["pi_80_coverage"].mean()) <= 0.85
            if len(qualified)
            else False
        ),
        "direction_no_worse": (
            qualified["directional_hit_rate"].mean()
            >= comparison["baseline_direction"].mean() - 1e-12
            if len(qualified)
            else False
        ),
        "parser_quality_gate": parser_gate,
    }
    return pd.DataFrame(
        [
            {
                "candidate": label,
                "required_tickers": required,
                "qualified_tickers": len(qualified),
                "baseline_median_mase": comparison["baseline_mase"].median(),
                "candidate_median_mase": qualified["mase"].median(),
                "baseline_mean_mase": comparison["baseline_mase"].mean(),
                "candidate_mean_mase": qualified["mase"].mean(),
                "baseline_no_regression_share": (
                    float(delta.le(0.0).mean()) if len(delta) else 0.0
                ),
                "severe_regression_count": int(delta.gt(2.0).sum()),
                "candidate_pi80": (
                    float(qualified["pi_80_coverage"].mean())
                    if len(qualified)
                    else np.nan
                ),
                "candidate_direction": (
                    float(qualified["directional_hit_rate"].mean())
                    if len(qualified)
                    else np.nan
                ),
                **checks,
                "candidate_gate": all(bool(value) for value in checks.values()),
            }
        ]
    )


def _feature_eligibility(
    panel: pd.DataFrame,
    baseline: pd.DataFrame,
    subindustry: str,
    features: list[str],
) -> pd.DataFrame:
    keys = baseline.loc[baseline["subindustry"].eq(subindustry), ["ticker", "quarter"]]
    view = keys.merge(
        panel[["ticker", "quarter", *features]],
        on=["ticker", "quarter"],
        how="left",
    )
    rows: list[dict[str, object]] = []
    for feature in features:
        available = view[feature].notna()
        by_ticker = view.assign(_available=available).groupby("ticker")["_available"].sum()
        rows.append(
            {
                "subindustry": subindustry,
                "feature": feature,
                "eligible_rows": int(available.sum()),
                "test_rows": len(view),
                "coverage_share": float(available.mean()),
                "minimum_rows_per_ticker": int(by_ticker.min()),
                "policy": "POINT_IN_TIME_CUTOFF_AND_FRESHNESS_REQUIRED",
            }
        )
    return pd.DataFrame(rows)


def _macro_track(
    *,
    subindustry: str,
    features: list[str],
    time_baseline: pd.DataFrame,
    loco_baseline: pd.DataFrame,
    panel: pd.DataFrame,
    parser_gate: bool,
    model_config: dict[str, object],
) -> tuple[
    dict[str, pd.DataFrame],
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    kwargs = {
        "parser_quality_gate": parser_gate,
        "alpha": float(model_config["ridge_alpha"]),
        "minimum_training_observations": int(
            model_config["minimum_training_observations"]
        ),
        "clip_log_points": float(model_config["overlay_clip_log_points"]),
    }
    results: dict[tuple[str, str], ResidualCandidateResult] = {}
    time_gates: list[pd.DataFrame] = []
    loco_gates: list[pd.DataFrame] = []
    for feature in features:
        time = evaluate_residual_candidate(
            time_baseline,
            panel,
            subindustry,
            (feature,),
            f"TIME_HOLDOUT_8Q_{subindustry.upper()}_MACRO",
            **kwargs,
        )
        loco = evaluate_residual_candidate(
            loco_baseline,
            panel,
            subindustry,
            (feature,),
            f"LOCO_TIME_SAFE_8Q_{subindustry.upper()}_MACRO",
            **kwargs,
        )
        results[(feature, "TIME")] = time
        results[(feature, "LOCO")] = loco
        time_gates.append(time.gate.assign(research_stage="SINGLE"))
        loco_gates.append(loco.gate.assign(research_stage="SINGLE"))
    single_time_gates = _concat(time_gates)
    passing_singles = single_time_gates.loc[
        single_time_gates["candidate_gate"].eq(True), "features"  # noqa: E712
    ].astype(str).tolist()
    for pair in combinations(sorted(passing_singles), 2):
        label = "+".join(pair)
        time = evaluate_residual_candidate(
            time_baseline,
            panel,
            subindustry,
            pair,
            f"TIME_HOLDOUT_8Q_{subindustry.upper()}_MACRO",
            **kwargs,
        )
        loco = evaluate_residual_candidate(
            loco_baseline,
            panel,
            subindustry,
            pair,
            f"LOCO_TIME_SAFE_8Q_{subindustry.upper()}_MACRO",
            **kwargs,
        )
        results[(label, "TIME")] = time
        results[(label, "LOCO")] = loco
        time_gates.append(time.gate.assign(research_stage="PAIRWISE_AFTER_SINGLE_PASS"))
        loco_gates.append(loco.gate.assign(research_stage="PAIRWISE_AFTER_SINGLE_PASS"))
    all_time_gates = _concat(time_gates)
    all_loco_gates = _concat(loco_gates)
    passing = all_time_gates.loc[
        all_time_gates["candidate_gate"].eq(True)  # noqa: E712
    ].sort_values(["candidate_median_mase", "candidate_mean_mase", "features"])
    if passing.empty:
        selected_time = time_baseline.loc[
            time_baseline["subindustry"].eq(subindustry)
        ].copy()
        selected_loco = loco_baseline.loc[
            loco_baseline["subindustry"].eq(subindustry)
        ].copy()
        selected_feature = "NONE"
        decision = "RETAIN_FROZEN_BENCHMARK"
    else:
        selected_feature = str(passing.iloc[0]["features"])
        selected_time = results[(selected_feature, "TIME")].predictions.copy()
        selected_loco = results[(selected_feature, "LOCO")].predictions.copy()
        decision = "RESEARCH_GATE_PASS"
    benchmark_name = (
        "P2.1_REFINING_COMPANY_KPI" if subindustry == "refining"
        else "STRUCTURAL_PROXY_RECALIBRATED"
    )
    selected_model = (
        f"P2.2_{subindustry.upper()}_MACRO_{selected_feature}"
        if selected_feature != "NONE"
        else benchmark_name
    )
    selected_time["research_route_model"] = selected_model
    selected_loco["research_route_model"] = selected_model
    decision_frame = pd.DataFrame(
        [
            {
                "subindustry": subindustry,
                "benchmark": benchmark_name,
                "selected_macro": selected_feature,
                "research_route_model": selected_model,
                "decision": decision,
                "production_model": "LAG_REVENUE_BASELINE",
            }
        ]
    )
    artifact_frames = {
        "time_predictions": _concat(
            [result.predictions for (label, split), result in results.items() if split == "TIME"]
        ),
        "loco_predictions": _concat(
            [result.predictions for (label, split), result in results.items() if split == "LOCO"]
        ),
        "time_scorecards": _concat(
            [result.scorecard for (label, split), result in results.items() if split == "TIME"]
        ),
        "loco_scorecards": _concat(
            [result.scorecard for (label, split), result in results.items() if split == "LOCO"]
        ),
    }
    return (
        artifact_frames,
        all_time_gates,
        all_loco_gates,
        decision_frame,
        selected_time,
        selected_loco,
    )


def _orders_lag_study(
    company_kpis: pd.DataFrame,
    proxy_panel: pd.DataFrame,
    time_baseline: pd.DataFrame,
    loco_baseline: pd.DataFrame,
    lags: list[int],
    parser_gate: bool,
) -> dict[str, pd.DataFrame]:
    bkr_orders = company_kpis.loc[
        company_kpis["ticker"].eq("BKR")
        & company_kpis["metric_id"].eq("orders_activity")
    ].copy()
    bkr_panel = proxy_panel.loc[proxy_panel["ticker"].eq("BKR")].copy()
    bkr_time = time_baseline.loc[time_baseline["ticker"].eq("BKR")].copy()
    bkr_loco = loco_baseline.loc[loco_baseline["ticker"].eq("BKR")].copy()
    time_predictions: list[pd.DataFrame] = []
    loco_predictions: list[pd.DataFrame] = []
    gates: list[pd.DataFrame] = []
    for lag in lags:
        features = select_company_kpis_for_targets(
            bkr_orders,
            bkr_panel[["ticker", "quarter"]],
            report_lag_quarters=lag,
        )
        feature = features[["ticker", "quarter", "orders_activity_log_yoy"]].rename(
            columns={"orders_activity_log_yoy": "orders_lag_feature"}
        )
        panel = bkr_panel.merge(feature, on=["ticker", "quarter"], how="left")
        time = evaluate_residual_candidate(
            bkr_time,
            panel,
            "services",
            ("orders_lag_feature",),
            f"TIME_BKR_ORDERS_LAG_{lag}",
            parser_quality_gate=parser_gate,
            minimum_training_observations=12,
        )
        loco = evaluate_residual_candidate(
            bkr_loco,
            panel,
            "services",
            ("orders_lag_feature",),
            f"LOCO_BKR_ORDERS_LAG_{lag}",
            parser_quality_gate=parser_gate,
            minimum_training_observations=12,
        )
        time.predictions["orders_report_lag_quarters"] = lag
        loco.predictions["orders_report_lag_quarters"] = lag
        gate = time.gate.copy()
        gate["orders_report_lag_quarters"] = lag
        gate["industry_ticker_coverage"] = "1/3"
        gate["industry_coverage_gate"] = False
        gate["loco_overlay_applied_share"] = float(
            loco.predictions["macro_overlay_applied"].mean()
        )
        gate["loco_cold_start_gate"] = False
        gate["candidate_gate"] = False
        gate["decision"] = "DIAGNOSTIC_ONLY_RETAIN_SERVICES_PROXY"
        time_predictions.append(time.predictions)
        loco_predictions.append(loco.predictions)
        gates.append(gate)
    return {
        "time": _concat(time_predictions),
        "loco": _concat(loco_predictions),
        "gates": _concat(gates),
    }


def _write_report(
    output: Path,
    macro_decisions: pd.DataFrame,
    macro_gates: pd.DataFrame,
    orders_gates: pd.DataFrame,
    forward_coverage: pd.DataFrame,
    ebitda_audit: pd.DataFrame,
    ebitda_summary: pd.DataFrame,
    ebitda_gate: pd.DataFrame,
    router_scorecard: pd.DataFrame,
    target_registry: pd.DataFrame,
) -> None:
    macro_columns = [
        "subindustry",
        "features",
        "baseline_median_mase",
        "candidate_median_mase",
        "baseline_no_regression_share",
        "candidate_pi80",
        "candidate_direction",
        "candidate_gate",
    ]
    lines = [
        "# Phase 2.5 target-aligned research",
        "",
        "P2.1 Refining KPI and the Services proxy are fixed input benchmarks.",
        "Macro variables are tested one at a time; combinations are forbidden unless",
        "every constituent first passes the full TIME gate. Production remains frozen",
        "at 0/20 live observations.",
        "",
        "## Refining and Services macro decisions",
        "",
        _markdown(macro_decisions),
        "",
        "## Single/passing-combination TIME gates",
        "",
        _markdown(macro_gates[macro_columns].round(4)),
        "",
        "## Services orders lag diagnostic",
        "",
        _markdown(orders_gates.round(4)),
        "",
        "Orders are available only for BKR. TIME lag results are diagnostic and LOCO",
        "must fail cold-start; neither lag can replace the three-company Services proxy.",
        "",
        "## Integrated forward-signal unlock",
        "",
        _markdown(forward_coverage),
        "",
        "Historical Integrated KPI expansion remains disabled. Text candidates do not",
        "enter a model until numeric meaning and target quarter pass manual gold review.",
        "",
        "## Midstream Adjusted EBITDA target",
        "",
        _markdown(ebitda_audit.round(4)),
        "",
        _markdown(ebitda_summary.round(4)),
        "",
        _markdown(ebitda_gate),
        "",
        "## Phase 5 static router scorecard",
        "",
        _markdown(router_scorecard.round(4)),
        "",
        "The router dispatches by ticker taxonomy only. It does not train an energy-wide",
        "meta-model or re-optimize child forecasts.",
        "",
        "## Target expansion registry",
        "",
        _markdown(target_registry),
        "",
        "Unstandardized margin and CapEx targets fail closed. They do not enter a",
        "forecast merely because a plausible structural driver exists.",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))

    p21_before = verify_refining_kpi_benchmark(ROOT)
    proxy_before = verify_proxy_benchmark(ROOT)
    v34_before = verify_champion(ROOT, "3.4")
    v353_before = verify_research_champion(ROOT, "3.5.3")
    parser_gates, parser_status = _parser_gate_status()
    parser_lookup = (
        parser_gates.set_index("subindustry")["parser_quality_gate"].astype(bool).to_dict()
        if not parser_gates.empty
        else {}
    )

    if args.refresh_macro_data:
        refresh_macro_snapshot(
            MACRO_SNAPSHOT, DATA.v33 / "energy_v3_3_eia_prices_daily.csv"
        )
    raw_macro = load_macro_snapshot(MACRO_SNAPSHOT)
    proxy_panel = pd.read_parquet(
        PROXY_OUTPUT / "structural_panel.parquet"
    )
    company_panel = pd.read_parquet(P21 / "company_kpi_panel.parquet")
    all_quarters = sorted(
        set(proxy_panel["quarter"].astype(str)), key=lambda value: pd.Period(value, freq="Q")
    )
    macro = build_macro_feature_panel(all_quarters, raw_macro)
    proxy_panel = attach_target_aligned_macro_features(proxy_panel, macro)
    company_panel = attach_target_aligned_macro_features(company_panel, macro)

    company_time = pd.read_csv(P21 / "company_kpi_time_predictions.csv")
    company_loco = pd.read_csv(P21 / "company_kpi_loco_predictions.csv")
    proxy_time = pd.read_csv(P21 / "proxy_recalibrated_time_predictions.csv")
    proxy_loco = pd.read_csv(P21 / "proxy_recalibrated_loco_predictions.csv")
    model_config = config["macro_model"]

    refining_features = list(config["refining"]["features"])
    services_features = list(config["services"]["features"])
    (
        ref_artifacts,
        ref_time_gates,
        ref_loco_gates,
        ref_decision,
        ref_selected_time,
        ref_selected_loco,
    ) = _macro_track(
        subindustry="refining",
        features=refining_features,
        time_baseline=company_time,
        loco_baseline=company_loco,
        panel=company_panel,
        parser_gate=parser_status == "CURRENT" and parser_lookup.get("refining", False),
        model_config=model_config,
    )
    (
        svc_artifacts,
        svc_time_gates,
        svc_loco_gates,
        svc_decision,
        svc_selected_time,
        svc_selected_loco,
    ) = _macro_track(
        subindustry="services",
        features=services_features,
        time_baseline=proxy_time,
        loco_baseline=proxy_loco,
        panel=proxy_panel,
        parser_gate=parser_status == "CURRENT" and parser_lookup.get("services", False),
        model_config=model_config,
    )
    macro_decisions = pd.concat([ref_decision, svc_decision], ignore_index=True)
    macro_time_gates = pd.concat([ref_time_gates, svc_time_gates], ignore_index=True)
    macro_loco_gates = pd.concat([ref_loco_gates, svc_loco_gates], ignore_index=True)

    eligibility = pd.concat(
        [
            _feature_eligibility(
                company_panel, company_time, "refining", refining_features
            ),
            _feature_eligibility(proxy_panel, proxy_time, "services", services_features),
        ],
        ignore_index=True,
    )

    company_kpis = load_company_kpis(KPI_SNAPSHOT)
    orders = _orders_lag_study(
        company_kpis,
        proxy_panel,
        proxy_time,
        proxy_loco,
        [int(value) for value in config["services"]["orders_lags_to_test"]],
        parser_status == "CURRENT" and parser_lookup.get("services", False),
    )

    source_manifest = pd.read_csv(KPI_SNAPSHOT / "source_manifest.csv")
    ebitda_candidates, ebitda_selected = extract_midstream_adjusted_ebitda(
        source_manifest
    )
    ebitda_gold = pd.read_csv(EBITDA_GOLD)
    ebitda_audit_rows, ebitda_audit = audit_midstream_ebitda_gold(
        ebitda_selected, ebitda_gold
    )
    ebitda_parser_gate = bool(ebitda_audit.loc[0, "parser_quality_gate"])
    ebitda_panel = build_midstream_ebitda_panel(
        ebitda_selected, company_kpis, proxy_panel
    )
    ebitda_result = validate_subindustry(ebitda_panel, "midstream", quarters=8)
    ebitda_gate = ebitda_result.gate.copy()
    ebitda_gate["adjusted_ebitda_parser_quality_gate"] = ebitda_parser_gate
    ebitda_gate["target_research_gate"] = (
        ebitda_gate["research_gate"].astype(bool) & ebitda_parser_gate
    )
    ebitda_gate["production_eligible"] = False
    ebitda_passed = bool(ebitda_gate.loc[0, "target_research_gate"])
    ebitda_selected_time = ebitda_result.time_predictions.copy()
    ebitda_selected_loco = ebitda_result.loco_predictions.copy()
    ebitda_route = "P3.2_MIDSTREAM_ADJUSTED_EBITDA_VOLUME_FEE"
    if not ebitda_passed:
        ebitda_route = "LAG_ADJUSTED_EBITDA_BASELINE"
        for frame in (ebitda_selected_time, ebitda_selected_loco):
            frame["candidate_prediction"] = frame["legacy_prediction"]
            frame["candidate_revenue"] = frame["prior_year_revenue"] * np.exp(
                frame["candidate_prediction"] / 100.0
            )
            frame["candidate_revenue_ape_pct"] = abs(
                frame["candidate_revenue"] / frame["revenue"] - 1.0
            ) * 100.0
            frame["direction_correct"] = np.sign(frame["candidate_prediction"]) == np.sign(
                frame["actual_log_yoy"]
            )

    forward_candidates, forward_coverage = scan_integrated_forward_signals(
        source_manifest
    )

    downstream_time_parts = []
    downstream_loco_parts = []
    for subindustry, time_part, loco_part, model in (
        (
            "integrated",
            proxy_time.loc[proxy_time["subindustry"].eq("integrated")],
            proxy_loco.loc[proxy_loco["subindustry"].eq("integrated")],
            "STRUCTURAL_PROXY_RECALIBRATED",
        ),
        (
            "refining",
            ref_selected_time,
            ref_selected_loco,
            str(ref_decision.iloc[0]["research_route_model"]),
        ),
        (
            "midstream",
            proxy_time.loc[proxy_time["subindustry"].eq("midstream")],
            proxy_loco.loc[proxy_loco["subindustry"].eq("midstream")],
            "STRUCTURAL_PROXY_RECALIBRATED",
        ),
        (
            "services",
            svc_selected_time,
            svc_selected_loco,
            str(svc_decision.iloc[0]["research_route_model"]),
        ),
    ):
        for frame, parts in (
            (time_part.copy(), downstream_time_parts),
            (loco_part.copy(), downstream_loco_parts),
        ):
            frame["research_route_model"] = model
            parts.append(frame)
    downstream_time = pd.concat(downstream_time_parts, ignore_index=True, sort=False)
    downstream_loco = pd.concat(downstream_loco_parts, ignore_index=True, sort=False)

    ep_time = pd.read_csv(V353_OUTPUT / "time_holdout_predictions.csv")
    ep_loco = pd.read_csv(V353_OUTPUT / "loco_predictions.csv")
    for frame in (ep_time, ep_loco):
        frame["subindustry"] = frame["ticker"].map(ep_subindustry)
        frame["research_route_model"] = (
            "V3.5.3_GROUPED_" + frame["selected_model"].astype(str)
        )
    common_time = pd.concat(
        [
            standardize_revenue_predictions(
                ep_time,
                phase=1,
                subindustry=None,
                route_model=None,
                validation="TIME_HOLDOUT_PHASE5_ROUTER",
                production_model="V3.4_FROZEN",
            ),
            standardize_revenue_predictions(
                downstream_time,
                phase=None,
                subindustry=None,
                route_model=None,
                validation="TIME_HOLDOUT_PHASE5_ROUTER",
                production_model="LAG_REVENUE_BASELINE",
            ),
            standardize_ebitda_predictions(
                ebitda_selected_time,
                "TIME_HOLDOUT_PHASE5_ROUTER",
                ebitda_route,
            ),
        ],
        ignore_index=True,
        sort=False,
    )
    common_loco = pd.concat(
        [
            standardize_revenue_predictions(
                ep_loco,
                phase=1,
                subindustry=None,
                route_model=None,
                validation="LOCO_TIME_SAFE_PHASE5_ROUTER",
                production_model="V3.4_FROZEN",
            ),
            standardize_revenue_predictions(
                downstream_loco,
                phase=None,
                subindustry=None,
                route_model=None,
                validation="LOCO_TIME_SAFE_PHASE5_ROUTER",
                production_model="LAG_REVENUE_BASELINE",
            ),
            standardize_ebitda_predictions(
                ebitda_selected_loco,
                "LOCO_TIME_SAFE_PHASE5_ROUTER",
                ebitda_route,
            ),
        ],
        ignore_index=True,
        sort=False,
    )
    router_predictions = pd.concat([common_time, common_loco], ignore_index=True)
    router_scorecard = energy_sector_scorecard(router_predictions)

    unavailable_forward = pd.DataFrame(
        [
            {
                "subindustry": "services",
                "feature": feature,
                "status": "NOT_STANDARDIZED_NO_MODEL_ENTRY",
            }
            for feature in config["services"]["unavailable_forward_features"]
        ]
    )
    target_registry = pd.DataFrame(config["target_registry"])
    artifacts = {
        "macro_feature_panel.csv": macro,
        "macro_feature_eligibility.csv": eligibility,
        "macro_time_gates.csv": macro_time_gates,
        "macro_loco_diagnostics.csv": macro_loco_gates,
        "macro_research_decisions.csv": macro_decisions,
        "refining_macro_time_predictions.csv": ref_artifacts["time_predictions"],
        "refining_macro_loco_predictions.csv": ref_artifacts["loco_predictions"],
        "services_macro_time_predictions.csv": svc_artifacts["time_predictions"],
        "services_macro_loco_predictions.csv": svc_artifacts["loco_predictions"],
        "services_orders_lag_time_predictions.csv": orders["time"],
        "services_orders_lag_loco_predictions.csv": orders["loco"],
        "services_orders_lag_gates.csv": orders["gates"],
        "services_unavailable_forward_features.csv": unavailable_forward,
        "integrated_forward_signal_candidates.csv": forward_candidates,
        "integrated_forward_signal_coverage.csv": forward_coverage,
        "midstream_adjusted_ebitda_parser_candidates.csv": ebitda_candidates,
        "midstream_adjusted_ebitda_quarterly.csv": ebitda_selected,
        "midstream_adjusted_ebitda_gold_audit_rows.csv": ebitda_audit_rows,
        "midstream_adjusted_ebitda_gold_audit_summary.csv": ebitda_audit,
        "midstream_adjusted_ebitda_panel.csv": ebitda_panel,
        "midstream_adjusted_ebitda_time_predictions.csv": ebitda_result.time_predictions,
        "midstream_adjusted_ebitda_loco_predictions.csv": ebitda_result.loco_predictions,
        "midstream_adjusted_ebitda_summary.csv": ebitda_result.summary,
        "midstream_adjusted_ebitda_gate.csv": ebitda_gate,
        "phase5_routing_table.csv": pd.DataFrame(
            [
                {"taxonomy": "E&P", "research_route": "V3.5.3_GROUPED", "target": "GAAP_REVENUE"},
                {"taxonomy": "Integrated", "research_route": "STRUCTURAL_PROXY_RECALIBRATED", "target": "GAAP_REVENUE"},
                {"taxonomy": "Refining", "research_route": ref_decision.iloc[0]["research_route_model"], "target": "GAAP_REVENUE"},
                {"taxonomy": "Midstream", "research_route": "STRUCTURAL_PROXY_RECALIBRATED", "target": "GAAP_REVENUE"},
                {"taxonomy": "Midstream", "research_route": ebitda_route, "target": "ADJUSTED_EBITDA_NON_GAAP"},
                {"taxonomy": "Services", "research_route": svc_decision.iloc[0]["research_route_model"], "target": "GAAP_REVENUE"},
            ]
        ),
        "phase5_target_registry.csv": target_registry,
        "phase5_common_forecast_schema_time.csv": common_time,
        "phase5_common_forecast_schema_loco.csv": common_loco,
        "phase5_sector_scorecard.csv": router_scorecard,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(output / filename, index=False)

    _write_report(
        output,
        macro_decisions,
        macro_time_gates,
        orders["gates"],
        forward_coverage,
        ebitda_audit,
        ebitda_result.summary,
        ebitda_gate,
        router_scorecard,
        target_registry,
    )

    p21_after = verify_refining_kpi_benchmark(ROOT)
    proxy_after = verify_proxy_benchmark(ROOT)
    v34_after = verify_champion(ROOT, "3.4")
    v353_after = verify_research_champion(ROOT, "3.5.3")
    for name, before, after in (
        ("P2.1", p21_before, p21_after),
        ("proxy", proxy_before, proxy_after),
        ("V3.4", v34_before, v34_after),
        ("V3.5.3", v353_before, v353_after),
    ):
        if before["manifest_sha256"] != after["manifest_sha256"]:
            raise RuntimeError(f"Frozen {name} benchmark changed during research")

    macro_metadata = json.loads(
        (MACRO_SNAPSHOT / "metadata.json").read_text(encoding="utf-8")
    )
    metadata = {
        "version": config["version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "parser_audit_status": parser_status,
        "p2_1_refining_benchmark": p21_after,
        "phase2_4_proxy_benchmark": proxy_after,
        "v3_4_manifest_sha256": v34_after["manifest_sha256"],
        "v3_5_3_manifest_sha256": v353_after["manifest_sha256"],
        "macro_snapshot_sha256": macro_metadata["macro_series_sha256"],
        "refining_selected_macro": ref_decision.iloc[0]["selected_macro"],
        "services_selected_macro": svc_decision.iloc[0]["selected_macro"],
        "services_orders_decision": "DIAGNOSTIC_ONLY_1_OF_3_TICKERS",
        "integrated_historical_kpi_expansion_allowed": False,
        "integrated_forward_candidate_unlocked": False,
        "midstream_ebitda_parser_gate": ebitda_parser_gate,
        "midstream_ebitda_research_gate": ebitda_passed,
        "midstream_ebitda_route": ebitda_route,
        "phase5_router_meta_model_trained": False,
        "production_champion_changed": False,
        "live_matched_observations": "0/20",
        "paid_market_data_used": False,
        "config_sha256": _sha256(CONFIG),
        "ebitda_gold_sha256": _sha256(EBITDA_GOLD),
        "company_kpi_snapshot_sha256": _sha256(
            KPI_SNAPSHOT / "company_kpi_quarterly.csv"
        ),
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nMACRO DECISIONS\n", macro_decisions.to_string(index=False))
    print("\nMACRO TIME GATES\n", macro_time_gates[[
        "subindustry", "features", "candidate_median_mase",
        "baseline_no_regression_share", "candidate_pi80", "candidate_gate",
    ]].round(4).to_string(index=False))
    print("\nORDERS LAG\n", orders["gates"][[
        "orders_report_lag_quarters", "baseline_median_mase",
        "candidate_median_mase", "industry_ticker_coverage", "decision",
    ]].round(4).to_string(index=False))
    print("\nMIDSTREAM EBITDA\n", ebitda_result.summary.round(4).to_string(index=False))
    print("\nPHASE 5 ROUTER\n", router_scorecard.round(4).to_string(index=False))
    print(f"\nP2.1 unchanged: {p21_after['manifest_sha256']}")
    print(f"V3.4 unchanged: {v34_after['manifest_sha256']}")
    print(f"V3.5.3 unchanged: {v353_after['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
