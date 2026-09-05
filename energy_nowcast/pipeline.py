from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .benchmark import verify_frozen_benchmark
from .config import ModelConfig, ProjectPaths
from .data.consensus import (
    current_model_vs_consensus,
    evaluate_model_vs_consensus,
    load_arcana_consensus,
    load_consensus,
    point_in_time_consensus,
)
from .data.loaders import LegacyArtifacts, load_legacy_artifacts
from .features.component_prices import build_component_candidates
from .features.realized_basis import add_realized_basis_candidates
from .models.blender import quality_adjusted_weight
from equity_platform.validation.baselines import attach_naive_baseline
from .validation.cutoff_audit import build_release_cutoff_audit
from equity_platform.validation.intervals import (
    add_walk_forward_intervals,
    prediction_intervals_for_nowcast,
)
from equity_platform.validation.metrics import (
    build_metric_table,
    enrich_revenue_level_errors,
    mean_absolute_error,
)
from .validation.walk_forward import current_weights, walk_forward_validation


@dataclass
class PipelineResult:
    validation: pd.DataFrame
    metrics: pd.DataFrame
    nowcast: pd.DataFrame
    weights: pd.DataFrame
    intervals: pd.DataFrame
    cutoff_audit: pd.DataFrame
    promotion_decisions: pd.DataFrame
    component_candidates: pd.DataFrame
    basis_candidates: pd.DataFrame
    consensus_provider_coverage: pd.DataFrame
    current_consensus: pd.DataFrame
    consensus_comparison: pd.DataFrame
    consensus_summary: pd.DataFrame
    metadata: dict[str, Any]


def _prepare_validation(artifacts: LegacyArtifacts) -> pd.DataFrame:
    source = artifacts.validation.copy()
    source["quarter"] = source["quarter"].astype(str)
    source = attach_naive_baseline(source, artifacts.v21_validation)
    return source


def _candidate_decision(
    ticker: str,
    model_name: str,
    joined: pd.DataFrame,
    candidate_column: str,
    tolerance: float,
    minimum_observations: int,
) -> dict[str, Any]:
    available = joined.dropna(
        subset=["actual_log_yoy", "structural_log_yoy", candidate_column]
    )
    n = int(len(available))
    legacy_mae = mean_absolute_error(
        available["actual_log_yoy"], available["structural_log_yoy"]
    )
    candidate_mae = mean_absolute_error(
        available["actual_log_yoy"], available[candidate_column]
    )
    promoted = bool(
        n >= minimum_observations
        and np.isfinite(candidate_mae)
        and candidate_mae <= legacy_mae + tolerance
    )
    if n < minimum_observations:
        reason = f"INSUFFICIENT_HISTORY_{n}_OF_{minimum_observations}"
    elif promoted:
        reason = "PROMOTED_NO_MAE_REGRESSION"
    else:
        reason = "REJECTED_MAE_REGRESSION"
    return {
        "stage": model_name,
        "ticker": ticker,
        "observations": n,
        "legacy_structural_mae_log_points": legacy_mae,
        "candidate_structural_mae_log_points": candidate_mae,
        "mae_improvement_log_points": legacy_mae - candidate_mae,
        "promoted": promoted,
        "reason": reason,
    }


def _apply_v34_candidates(
    base_validation: pd.DataFrame,
    artifacts: LegacyArtifacts,
    config: ModelConfig,
    paths: ProjectPaths,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[tuple[str, str], dict]]:
    validation = base_validation.copy()
    decisions: list[dict[str, Any]] = []
    current_overrides: dict[tuple[str, str], dict] = {}

    basis = add_realized_basis_candidates(
        artifacts.component_panel, artifacts.panel, config, paths
    )
    eog = validation.loc[validation["ticker"].eq("EOG")].merge(
        basis[["quarter", "v34_structural_log_yoy", "basis_adjustment_log_points"]],
        on="quarter",
        how="left",
    )
    basis_decision = _candidate_decision(
        "EOG",
        "V3.4_REALIZED_BASIS",
        eog,
        "v34_structural_log_yoy",
        config.promotion_tolerance_log_points,
        config.basis_min_history,
    )
    decisions.append(basis_decision)
    if basis_decision["promoted"]:
        basis_map = basis.set_index("quarter")["v34_structural_log_yoy"]
        mask = validation["ticker"].eq("EOG")
        replacements = validation.loc[mask, "quarter"].map(basis_map)
        validation.loc[mask, "structural_log_yoy"] = replacements.combine_first(
            validation.loc[mask, "structural_log_yoy"]
        )
        for _, row in basis.dropna(subset=["v34_structural_log_yoy"]).iterrows():
            current_overrides[("EOG", str(row["quarter"]))] = {
                "structural_log_yoy": float(row["v34_structural_log_yoy"]),
                "structural_model_type": "V3_4_REALIZED_BASIS",
                "basis_adjustment_log_points": float(row["basis_adjustment_log_points"]),
            }

    targets = pd.concat(
        [
            validation[["ticker", "quarter"]],
            artifacts.nowcast.rename(columns={"nowcast_quarter": "quarter"})[
                ["ticker", "quarter"]
            ],
        ],
        ignore_index=True,
    ).drop_duplicates()
    components = build_component_candidates(
        targets,
        artifacts.prices,
        artifacts.panel,
        config,
        paths,
    )
    if not components.empty:
        for ticker, candidates in components.groupby("ticker", sort=True):
            joined = validation.loc[validation["ticker"].eq(ticker)].merge(
                candidates[
                    ["quarter", "component_structural_log_yoy", "source_quality_score"]
                ],
                on="quarter",
                how="left",
                suffixes=("", "_candidate"),
            )
            decision = _candidate_decision(
                str(ticker),
                "COMPONENT_EXPANSION",
                joined,
                "component_structural_log_yoy",
                config.promotion_tolerance_log_points,
                4,
            )
            decisions.append(decision)
            if not decision["promoted"]:
                continue
            candidate_map = candidates.set_index("quarter")
            mask = validation["ticker"].eq(ticker)
            structural_replacements = validation.loc[mask, "quarter"].map(
                candidate_map["component_structural_log_yoy"]
            )
            quality_replacements = validation.loc[mask, "quarter"].map(
                candidate_map["source_quality_score"]
            )
            validation.loc[mask, "structural_log_yoy"] = (
                structural_replacements.combine_first(
                    validation.loc[mask, "structural_log_yoy"]
                )
            )
            validation.loc[mask, "source_quality_score"] = quality_replacements.combine_first(
                validation.loc[mask, "source_quality_score"]
            )
            validation.loc[mask, "structural_model_type"] = np.where(
                structural_replacements.notna(),
                "OIL_PLUS_NON_OIL_PRICE_X_VOLUME",
                validation.loc[mask, "structural_model_type"],
            )
            for _, row in candidates.iterrows():
                current_overrides[(str(ticker), str(row["quarter"]))] = {
                    "structural_log_yoy": float(row["component_structural_log_yoy"]),
                    "structural_model_type": str(row["component_model_type"]),
                    "source_quality_score": float(row["source_quality_score"]),
                }
    return (
        validation,
        pd.DataFrame(decisions),
        components,
        basis,
        current_overrides,
    )


def _build_nowcast(
    artifacts: LegacyArtifacts,
    model_validation: pd.DataFrame,
    weights: pd.DataFrame,
    config: ModelConfig,
    overrides: dict[tuple[str, str], dict],
) -> pd.DataFrame:
    result = artifacts.nowcast.copy()
    result["nowcast_quarter"] = result["nowcast_quarter"].astype(str)
    result = result.rename(
        columns={
            "predicted_revenue_log_yoy": "v3_3_champion_log_yoy",
            "predicted_revenue_yoy_pct": "v3_3_champion_yoy_pct",
            "predicted_revenue_B": "v3_3_champion_revenue_B",
            "structural_weight": "v3_3_structural_weight",
        }
    )
    for index, row in result.iterrows():
        override = overrides.get((str(row["ticker"]), str(row["nowcast_quarter"])))
        if override:
            for key, value in override.items():
                result.at[index, key] = value

    result = result.merge(
        weights,
        on="ticker",
        how="left",
        validate="one_to_one",
    )
    effective_weights: list[float] = []
    for _, row in result.iterrows():
        effective_weights.append(
            quality_adjusted_weight(
                float(row["shrunk_structural_weight"]),
                float(pd.to_numeric(row["source_quality_score"], errors="coerce")),
                str(row["production_yoy_source"]),
            )
        )
    result["structural_weight"] = effective_weights
    result["v21_weight"] = 1.0 - result["structural_weight"]
    result["predicted_revenue_log_yoy"] = (
        result["structural_weight"] * result["structural_log_yoy"]
        + result["v21_weight"] * result["v21_log_yoy"]
    ).clip(-100.0, 150.0)
    result["predicted_revenue_yoy_pct"] = 100.0 * np.expm1(
        result["predicted_revenue_log_yoy"] / 100.0
    )
    inferred_prior_revenue = result["v3_3_champion_revenue_B"] / np.exp(
        result["v3_3_champion_log_yoy"] / 100.0
    )
    result["predicted_revenue_B"] = inferred_prior_revenue * np.exp(
        result["predicted_revenue_log_yoy"] / 100.0
    )
    result["model_spread_log_points"] = (
        result["structural_log_yoy"] - result["v21_log_yoy"]
    ).abs()
    result["selected_model"] = np.where(
        result["structural_weight"].le(0.001),
        "V2.1_ONLY",
        np.where(result["structural_weight"].ge(0.999), "STRUCTURAL_ONLY", "BLEND"),
    )
    return prediction_intervals_for_nowcast(
        result,
        model_validation,
        config.interval_levels,
        config.ticker_residual_weight,
    )


def _interval_summary(
    validation: pd.DataFrame,
    levels: tuple[float, ...],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for level in levels:
        label = int(round(level * 100))
        column = f"covered_{label}"
        for split in ("all", "train_validation", "untouched_test"):
            selected = (
                validation if split == "all" else validation.loc[
                    validation["evaluation_split"].eq(split)
                ]
            )
            observed = selected[column].dropna()
            rows.append(
                {
                    "interval_level": level,
                    "evaluation_split": split,
                    "observations": int(len(observed)),
                    "empirical_coverage": (
                        float(observed.astype(bool).mean()) if len(observed) else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def run_pipeline(config: ModelConfig, paths: ProjectPaths) -> PipelineResult:
    manifest = verify_frozen_benchmark(paths)
    artifacts = load_legacy_artifacts(paths)
    base_validation = _prepare_validation(artifacts)
    infrastructure_validation = walk_forward_validation(base_validation, config)
    infrastructure_mae = mean_absolute_error(
        infrastructure_validation["actual_log_yoy"],
        infrastructure_validation["prediction_log_yoy"],
    )
    benchmark_mae = float(manifest["expected_metrics"]["overall_mae_log_points"])
    infrastructure_regression_pct = (
        (infrastructure_mae / benchmark_mae - 1.0) * 100.0
    )
    infrastructure_gate_passed = bool(
        infrastructure_regression_pct <= config.validation_regression_tolerance_pct
    )
    if config.realized_basis and not infrastructure_gate_passed:
        raise RuntimeError(
            "V3.4 blocked: V3.3.1 validation infrastructure exceeded the "
            f"{config.validation_regression_tolerance_pct:.2f}% regression tolerance"
        )

    decisions = pd.DataFrame(
        columns=[
            "stage",
            "ticker",
            "observations",
            "legacy_structural_mae_log_points",
            "candidate_structural_mae_log_points",
            "mae_improvement_log_points",
            "promoted",
            "reason",
        ]
    )
    components = pd.DataFrame()
    basis = pd.DataFrame()
    overrides: dict[tuple[str, str], dict] = {}
    model_source = base_validation
    if config.realized_basis:
        model_source, decisions, components, basis, overrides = _apply_v34_candidates(
            base_validation, artifacts, config, paths
        )

    validation = walk_forward_validation(model_source, config)
    cutoff = build_release_cutoff_audit(validation, config, paths)
    validation = validation.merge(
        cutoff[["ticker", "quarter", "forecast_cutoff_date", "cutoff_status"]],
        on=["ticker", "quarter"],
        how="left",
    )
    validation = enrich_revenue_level_errors(validation, artifacts.panel)
    validation = add_walk_forward_intervals(
        validation,
        config.interval_levels,
        config.ticker_residual_weight,
        min_history=4,
    )
    metrics = build_metric_table(validation)
    weights = current_weights(model_source, config)
    nowcast = _build_nowcast(
        artifacts, validation, weights, config, overrides
    )
    intervals = _interval_summary(validation, config.interval_levels)

    assert paths.data_lake is not None
    arcana_dir = (paths.root / config.arcana_consensus_dir).resolve()
    arcana_consensus, provider_coverage = load_arcana_consensus(
        arcana_dir, config.tickers
    )
    manual_consensus = load_consensus(paths.data_lake / config.consensus_file)
    consensus_raw = pd.concat(
        [arcana_consensus, manual_consensus], ignore_index=True, sort=False
    )
    consensus_pit = point_in_time_consensus(
        consensus_raw, config.release_cutoff_day_of_quarter
    )
    current_consensus = current_model_vs_consensus(nowcast, consensus_pit)
    model_levels = validation[
        ["ticker", "quarter", "predicted_revenue", "actual_revenue"]
    ].copy()
    consensus_comparison, consensus_summary = evaluate_model_vs_consensus(
        model_levels,
        consensus_pit,
        config.minimum_consensus_observations,
    )

    all_metrics = metrics.loc[
        metrics["ticker"].eq("ALL") & metrics["evaluation_split"].eq("all")
    ].iloc[0]
    final_regression_pct = (
        float(all_metrics["mae_log_points"]) / benchmark_mae - 1.0
    ) * 100.0
    metadata = {
        "version": config.version,
        "source_version": config.source_version,
        "as_of_date": config.as_of_date.isoformat(),
        "benchmark": {
            "name": manifest["name"],
            "verified": True,
            "git_commit": manifest["git_commit"],
        },
        "config": _json_safe_config(config),
        "overall_metrics": {
            "mae_log_points": float(all_metrics["mae_log_points"]),
            "mae_yoy_pct_points": float(all_metrics["mae_yoy_pct_points"]),
            "mase": float(all_metrics["mase"]),
            "revenue_level_mape_pct": float(all_metrics["revenue_level_mape_pct"]),
        },
        "validation_gates": {
            "v3_3_1_infrastructure": {
                "benchmark_mae_log_points": benchmark_mae,
                "candidate_mae_log_points": infrastructure_mae,
                "regression_pct": infrastructure_regression_pct,
                "tolerance_pct": config.validation_regression_tolerance_pct,
                "passed": infrastructure_gate_passed,
            },
            "final_model": {
                "benchmark_mae_log_points": benchmark_mae,
                "candidate_mae_log_points": float(all_metrics["mae_log_points"]),
                "regression_pct": final_regression_pct,
                "passed": final_regression_pct <= config.validation_regression_tolerance_pct,
            },
        },
        "consensus_status": consensus_summary.iloc[0].to_dict(),
        "consensus_sources": {
            "arcana_directory": str(arcana_dir),
            "normalized_revenue_estimate_rows": int(len(arcana_consensus)),
            "finnworlds_note": "company-ratings has no revenue estimate field",
        },
    }
    return PipelineResult(
        validation=validation,
        metrics=metrics,
        nowcast=nowcast,
        weights=weights,
        intervals=intervals,
        cutoff_audit=cutoff,
        promotion_decisions=decisions,
        component_candidates=components,
        basis_candidates=basis,
        consensus_provider_coverage=provider_coverage,
        current_consensus=current_consensus,
        consensus_comparison=consensus_comparison,
        consensus_summary=consensus_summary,
        metadata=metadata,
    )


def _json_safe_config(config: ModelConfig) -> dict[str, Any]:
    values = asdict(config)
    values["as_of_date"] = config.as_of_date.isoformat()
    for key in ("tickers", "component_tickers", "interval_levels"):
        values[key] = list(values[key])
    return values


def _json_sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_sanitize(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def write_pipeline_result(result: PipelineResult, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = {
        "validation.csv": result.validation,
        "metrics.csv": result.metrics,
        "nowcast.csv": result.nowcast,
        "blend_weights.csv": result.weights,
        "interval_calibration.csv": result.intervals,
        "release_cutoff_audit.csv": result.cutoff_audit,
        "promotion_decisions.csv": result.promotion_decisions,
        "component_candidates.csv": result.component_candidates,
        "basis_candidates.csv": result.basis_candidates,
        "consensus_provider_coverage.csv": result.consensus_provider_coverage,
        "current_model_vs_consensus.csv": result.current_consensus,
        "consensus_comparison.csv": result.consensus_comparison,
        "consensus_summary.csv": result.consensus_summary,
    }
    written: list[Path] = []
    for filename, frame in frames.items():
        target = output_dir / filename
        frame.to_csv(target, index=False)
        written.append(target)
    metadata_path = output_dir / "metadata.json"
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(
            _json_sanitize(result.metadata),
            handle,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
    written.append(metadata_path)
    return written
