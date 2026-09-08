from __future__ import annotations

from dataclasses import asdict

from equity_platform.text_ie.llm import DEFAULT_ENCODER_CANDIDATES
from equity_platform.text_ie.semantic_challenger import SemanticTask
from equity_platform.text_ie.training.encoder_selection import (
    EncoderCertificationRun,
    EncoderCalibrationRun,
    EncoderCalibrationPrediction,
    encoder_champion_selection_from_dict,
    evaluate_champion_certification,
    select_encoder_champion,
)


SLICES = ("SEC_10K", "SEC_10Q", "IR_PREPARED_REMARKS", "IR_QA")


def _runs() -> tuple[EncoderCalibrationRun, ...]:
    rows = []
    for model_index, candidate in enumerate(DEFAULT_ENCODER_CANDIDATES):
        for task in SemanticTask:
            predictions = []
            for source_index, source_slice in enumerate(SLICES):
                predictions.append(EncoderCalibrationPrediction(
                    example_id=f"{model_index}-{task.value}-{source_index}-good",
                    source_slice=source_slice,
                    gold_label="RIGHT",
                    predicted_label="RIGHT",
                    confidence=0.95,
                ))
                if model_index > 0:
                    predictions.append(EncoderCalibrationPrediction(
                        example_id=f"{model_index}-{task.value}-{source_index}-bad",
                        source_slice=source_slice,
                        gold_label="RIGHT",
                        predicted_label="WRONG",
                        confidence=0.50 if model_index == 1 else 0.96,
                    ))
            rows.append(EncoderCalibrationRun(
                model_id=candidate.model_id,
                task=task,
                checkpoint=f"models/{model_index}/{task.value.lower()}",
                predictions=tuple(predictions),
            ))
    return tuple(rows)


def test_champion_uses_calibration_only_and_requires_every_source_task_cell() -> None:
    selection = select_encoder_champion(
        _runs(),
        minimum_precision={task: 0.90 for task in SemanticTask},
    )

    assert selection.status == "CALIBRATION_CHAMPION_SELECTED_CERTIFICATION_SEALED"
    assert selection.champion_model_id == DEFAULT_ENCODER_CANDIDATES[0].model_id
    assert len(selection.cells) == 9
    assert all(set(cell.by_source_slice) == set(SLICES) for cell in selection.cells)
    assert all(set(cell.confidence_thresholds) == set(SLICES) for cell in selection.cells)
    assert all(
        cell.passed_all_source_slices
        for cell in selection.cells
        if cell.model_id == selection.champion_model_id
    )


def test_no_model_is_selected_when_every_candidate_fails_a_source_slice() -> None:
    runs = tuple(
        EncoderCalibrationRun(
            model_id=run.model_id,
            task=run.task,
            checkpoint=run.checkpoint,
            predictions=tuple(
                EncoderCalibrationPrediction(
                    example_id=row.example_id,
                    source_slice=row.source_slice,
                    gold_label=row.gold_label,
                    predicted_label=(
                        "WRONG" if row.source_slice == "IR_QA" else row.predicted_label
                    ),
                    confidence=0.99,
                )
                for row in run.predictions
            ),
        )
        for run in _runs()
    )

    selection = select_encoder_champion(
        runs,
        minimum_precision={task: 0.90 for task in SemanticTask},
    )

    assert selection.champion_model_id is None
    assert selection.status == "NO_CALIBRATION_CHAMPION_PRODUCTION_LOCKED"


def test_certification_reuses_frozen_thresholds_and_cannot_reselect_model() -> None:
    selection = select_encoder_champion(
        _runs(),
        minimum_precision={task: 0.90 for task in SemanticTask},
    )
    champion = selection.champion_model_id
    certification = tuple(
        EncoderCertificationRun(
            model_id=champion,
            task=task,
            predictions=tuple(
                EncoderCalibrationPrediction(
                    example_id=f"cert-{task.value}-{source_slice}",
                    source_slice=source_slice,
                    gold_label="RIGHT",
                    predicted_label="RIGHT",
                    confidence=0.95,
                )
                for source_slice in SLICES
            ),
        )
        for task in SemanticTask
    )

    result = evaluate_champion_certification(
        selection,
        certification,
        minimum_precision={task: 0.90 for task in SemanticTask},
    )

    assert result.passed
    assert result.status == "TASK_CERTIFICATION_PASS_END_TO_END_GATE_STILL_REQUIRED"
    assert {cell.model_id for cell in result.cells} == {champion}

    restored = encoder_champion_selection_from_dict(asdict(selection))
    assert restored == selection
