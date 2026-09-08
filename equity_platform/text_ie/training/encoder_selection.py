from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

from ..llm.encoder_registry import DEFAULT_ENCODER_CANDIDATES, EncoderSourceSlice
from ..semantic_challenger import SemanticTask
from .selective_evaluation import (
    SelectivePrediction,
    SelectiveTaskMetrics,
    evaluate_selective_predictions,
)


@dataclass(frozen=True)
class EncoderCalibrationPrediction:
    example_id: str
    source_slice: str
    gold_label: str
    predicted_label: str
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("calibration confidence must be within [0, 1]")


@dataclass(frozen=True)
class EncoderCalibrationRun:
    model_id: str
    task: SemanticTask
    checkpoint: str
    predictions: tuple[EncoderCalibrationPrediction, ...]


@dataclass(frozen=True)
class EncoderSourceTaskCell:
    model_id: str
    task: SemanticTask
    checkpoint: str
    confidence_thresholds: dict[str, float | None]
    overall: SelectiveTaskMetrics
    by_source_slice: dict[str, SelectiveTaskMetrics]
    passed_all_source_slices: bool


@dataclass(frozen=True)
class EncoderChampionSelection:
    champion_model_id: str | None
    status: str
    cells: tuple[EncoderSourceTaskCell, ...]
    certification_sealed: bool = True


@dataclass(frozen=True)
class EncoderCertificationRun:
    model_id: str
    task: SemanticTask
    predictions: tuple[EncoderCalibrationPrediction, ...]


@dataclass(frozen=True)
class EncoderCertificationCell:
    model_id: str
    task: SemanticTask
    frozen_confidence_thresholds: dict[str, float]
    overall: SelectiveTaskMetrics
    by_source_slice: dict[str, SelectiveTaskMetrics]
    passed_all_source_slices: bool


@dataclass(frozen=True)
class EncoderCertificationResult:
    model_id: str
    passed: bool
    status: str
    cells: tuple[EncoderCertificationCell, ...]
    reasons: tuple[str, ...]


def _metrics_from_dict(row: Mapping[str, object]) -> SelectiveTaskMetrics:
    return SelectiveTaskMetrics(**{
        field: row[field]
        for field in SelectiveTaskMetrics.__dataclass_fields__
    })


def encoder_champion_selection_from_dict(
    row: Mapping[str, object],
) -> EncoderChampionSelection:
    cells = []
    for raw_cell in row.get("cells", ()):
        cells.append(EncoderSourceTaskCell(
            model_id=str(raw_cell["model_id"]),
            task=SemanticTask(str(raw_cell["task"])),
            checkpoint=str(raw_cell["checkpoint"]),
            confidence_thresholds={
                str(source): None if threshold is None else float(threshold)
                for source, threshold in raw_cell["confidence_thresholds"].items()
            },
            overall=_metrics_from_dict(raw_cell["overall"]),
            by_source_slice={
                str(source): _metrics_from_dict(metrics)
                for source, metrics in raw_cell["by_source_slice"].items()
            },
            passed_all_source_slices=bool(raw_cell["passed_all_source_slices"]),
        ))
    champion = row.get("champion_model_id")
    return EncoderChampionSelection(
        champion_model_id=None if champion is None else str(champion),
        status=str(row["status"]),
        cells=tuple(cells),
        certification_sealed=bool(row.get("certification_sealed", True)),
    )


def _selective(
    rows: tuple[EncoderCalibrationPrediction, ...], threshold: float | None
) -> tuple[SelectivePrediction, ...]:
    return tuple(
        SelectivePrediction(
            example_id=row.example_id,
            source_slice=row.source_slice,
            gold_label=row.gold_label,
            predicted_label=(
                row.predicted_label
                if threshold is not None and row.confidence >= threshold
                else None
            ),
            abstention_reason=(
                None
                if threshold is not None and row.confidence >= threshold
                else "BELOW_CALIBRATED_CONFIDENCE"
            ),
        )
        for row in rows
    )


def _selective_by_source(
    rows: tuple[EncoderCalibrationPrediction, ...],
    thresholds: Mapping[str, float | None],
) -> tuple[SelectivePrediction, ...]:
    return tuple(
        prediction
        for source in sorted(thresholds)
        for prediction in _selective(
            tuple(row for row in rows if row.source_slice == source),
            thresholds[source],
        )
    )


def _calibrate_cell(
    run: EncoderCalibrationRun,
    *,
    minimum_precision: float,
) -> EncoderSourceTaskCell:
    if not run.predictions:
        raise ValueError("encoder calibration runs require predictions")
    required_sources = {source.value for source in EncoderSourceSlice}
    observed_sources = {row.source_slice for row in run.predictions}
    if observed_sources != required_sources:
        raise ValueError(
            f"{run.model_id} {run.task.value} calibration source set mismatch"
        )
    thresholds = {}
    selected_by_source = {}
    for source in sorted(required_sources):
        source_rows = tuple(
            row for row in run.predictions if row.source_slice == source
        )
        selected_threshold = None
        selected_metrics = None
        for threshold in sorted({row.confidence for row in source_rows}):
            metrics = evaluate_selective_predictions(
                _selective(source_rows, threshold)
            )
            if metrics.predicted > 0 and metrics.precision >= minimum_precision:
                selected_threshold = threshold
                selected_metrics = metrics
                break
        if selected_metrics is None:
            selected_metrics = evaluate_selective_predictions(
                _selective(source_rows, None)
            )
        thresholds[source] = selected_threshold
        selected_by_source[source] = selected_metrics
    selected_overall = evaluate_selective_predictions(
        _selective_by_source(run.predictions, thresholds)
    )
    passed = (
        all(threshold is not None for threshold in thresholds.values())
        and selected_overall.precision >= minimum_precision
        and all(
            metrics.predicted > 0 and metrics.precision >= minimum_precision
            for metrics in selected_by_source.values()
        )
    )
    return EncoderSourceTaskCell(
        model_id=run.model_id,
        task=run.task,
        checkpoint=run.checkpoint,
        confidence_thresholds=thresholds,
        overall=selected_overall,
        by_source_slice=selected_by_source,
        passed_all_source_slices=passed,
    )


def select_encoder_champion(
    runs: tuple[EncoderCalibrationRun, ...],
    *,
    minimum_precision: Mapping[SemanticTask, float] | None = None,
) -> EncoderChampionSelection:
    """Select on calibration only; certification remains unopened."""

    minimum_precision = minimum_precision or {
        SemanticTask.CONCEPT: 0.98,
        SemanticTask.BINDING: 0.99,
        SemanticTask.ROLE: 0.99,
    }
    if set(minimum_precision) != set(SemanticTask):
        raise ValueError("minimum precision is required for every semantic task")
    expected_models = {candidate.model_id for candidate in DEFAULT_ENCODER_CANDIDATES}
    indexed = {}
    for run in runs:
        key = (run.model_id, run.task)
        if key in indexed:
            raise ValueError("duplicate encoder calibration run")
        indexed[key] = run
    expected_keys = {
        (model_id, task) for model_id in expected_models for task in SemanticTask
    }
    if set(indexed) != expected_keys:
        raise ValueError("encoder calibration matrix is incomplete")
    cells = tuple(
        _calibrate_cell(
            indexed[(candidate.model_id, task)],
            minimum_precision=float(minimum_precision[task]),
        )
        for candidate in DEFAULT_ENCODER_CANDIDATES
        for task in SemanticTask
    )
    by_model: dict[str, list[EncoderSourceTaskCell]] = defaultdict(list)
    for cell in cells:
        by_model[cell.model_id].append(cell)
    eligible = {
        model_id: rows
        for model_id, rows in by_model.items()
        if len(rows) == len(SemanticTask)
        and all(row.passed_all_source_slices for row in rows)
    }
    if not eligible:
        return EncoderChampionSelection(
            champion_model_id=None,
            status="NO_CALIBRATION_CHAMPION_PRODUCTION_LOCKED",
            cells=cells,
        )
    champion = max(
        eligible,
        key=lambda model_id: (
            sum(
                metrics.coverage_adjusted_precision
                for cell in eligible[model_id]
                for metrics in cell.by_source_slice.values()
            ),
            model_id,
        ),
    )
    return EncoderChampionSelection(
        champion_model_id=champion,
        status="CALIBRATION_CHAMPION_SELECTED_CERTIFICATION_SEALED",
        cells=cells,
    )


def evaluate_champion_certification(
    selection: EncoderChampionSelection,
    runs: tuple[EncoderCertificationRun, ...],
    *,
    minimum_precision: Mapping[SemanticTask, float] | None = None,
) -> EncoderCertificationResult:
    """Open certification once for the frozen calibration champion."""

    if selection.champion_model_id is None or not selection.certification_sealed:
        raise ValueError("certification requires one frozen calibration champion")
    minimum_precision = minimum_precision or {
        SemanticTask.CONCEPT: 0.98,
        SemanticTask.BINDING: 0.99,
        SemanticTask.ROLE: 0.99,
    }
    if set(minimum_precision) != set(SemanticTask):
        raise ValueError("minimum precision is required for every semantic task")
    indexed = {}
    for run in runs:
        if run.model_id != selection.champion_model_id:
            raise ValueError("certification cannot reselect or compare encoder models")
        if run.task in indexed:
            raise ValueError("duplicate champion certification task")
        indexed[run.task] = run
    if set(indexed) != set(SemanticTask):
        raise ValueError("champion certification requires all semantic tasks")
    calibration_cells = {
        cell.task: cell
        for cell in selection.cells
        if cell.model_id == selection.champion_model_id
    }
    required_sources = {source.value for source in EncoderSourceSlice}
    cells = []
    reasons = []
    for task in SemanticTask:
        calibration = calibration_cells[task]
        thresholds = calibration.confidence_thresholds
        if any(threshold is None for threshold in thresholds.values()):
            raise ValueError("champion task has no frozen source confidence threshold")
        run = indexed[task]
        observed_sources = {row.source_slice for row in run.predictions}
        if observed_sources != required_sources:
            raise ValueError(
                f"{task.value} certification source set mismatch"
            )
        frozen_thresholds = {
            source: float(threshold)
            for source, threshold in thresholds.items()
            if threshold is not None
        }
        predictions = _selective_by_source(run.predictions, frozen_thresholds)
        overall = evaluate_selective_predictions(predictions)
        by_source = {
            source: evaluate_selective_predictions(tuple(
                row for row in predictions if row.source_slice == source
            ))
            for source in sorted(required_sources)
        }
        passed = (
            overall.precision >= float(minimum_precision[task])
            and all(
                metrics.predicted > 0
                and metrics.precision >= float(minimum_precision[task])
                for metrics in by_source.values()
            )
        )
        if not passed:
            reasons.append(f"{task.value}_SOURCE_SLICE_CERTIFICATION_FAIL")
        cells.append(EncoderCertificationCell(
            model_id=run.model_id,
            task=task,
            frozen_confidence_thresholds=frozen_thresholds,
            overall=overall,
            by_source_slice=by_source,
            passed_all_source_slices=passed,
        ))
    all_passed = not reasons
    return EncoderCertificationResult(
        model_id=selection.champion_model_id,
        passed=all_passed,
        status=(
            "TASK_CERTIFICATION_PASS_END_TO_END_GATE_STILL_REQUIRED"
            if all_passed
            else "TASK_CERTIFICATION_FAIL_PRODUCTION_LOCKED"
        ),
        cells=tuple(cells),
        reasons=tuple(reasons),
    )


__all__ = [
    "EncoderCalibrationPrediction",
    "EncoderCalibrationRun",
    "EncoderCertificationCell",
    "EncoderCertificationResult",
    "EncoderCertificationRun",
    "EncoderChampionSelection",
    "EncoderSourceTaskCell",
    "encoder_champion_selection_from_dict",
    "evaluate_champion_certification",
    "select_encoder_champion",
]
