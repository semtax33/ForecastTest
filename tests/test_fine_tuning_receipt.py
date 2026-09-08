from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from equity_platform.text_ie.semantic_challenger import SemanticTask
from equity_platform.text_ie.training import SemanticFineTuningCell
from equity_platform.text_ie.training.encoder_selection import (
    EncoderCalibrationPrediction,
)
from equity_platform.text_ie.training.huggingface_fine_tuning import (
    HuggingFaceFineTuningRuntime,
    HuggingFaceFineTuningResult,
    fine_tuning_input_fingerprint,
    load_fine_tuning_result_receipt,
    write_fine_tuning_result_receipt,
)
from equity_platform.text_ie.training import huggingface_fine_tuning as hf_runtime


def _cell(tmp_path: Path) -> SemanticFineTuningCell:
    return SemanticFineTuningCell(
        model_id="test/model",
        task=SemanticTask.CONCEPT,
        labels=("REVENUE",),
        train_count=1,
        calibration_count=1,
        certification_count=1,
        train_source_counts={"SEC_10K": 1},
        calibration_source_counts={"SEC_10K": 1},
        certification_source_counts={"SEC_10K": 1},
        output_directory=str(tmp_path),
        device_policy="CUDA_REQUIRED",
        per_device_batch_size=2,
        gradient_accumulation_steps=8,
        max_length=512,
    )


def _row(label: str = "REVENUE") -> SimpleNamespace:
    return SimpleNamespace(
        example_id="example-1",
        entity="TEST",
        source_kind="SEC_10K",
        source_sha256="a" * 64,
        holdout_axis="TRAIN",
        marked_context="[METRIC]Revenue[/METRIC] was $10 million.",
        concept_label=label,
    )


def test_fingerprint_changes_when_training_label_changes(tmp_path) -> None:
    cell = _cell(tmp_path)

    first = fine_tuning_input_fingerprint(cell, (_row(),), (_row(),))
    second = fine_tuning_input_fingerprint(
        cell, (_row("OPERATING_MARGIN"),), (_row(),)
    )

    assert first != second


def test_fingerprint_changes_when_runtime_hyperparameters_change(tmp_path) -> None:
    cell = _cell(tmp_path)

    first = fine_tuning_input_fingerprint(
        cell,
        (_row(),),
        (_row(),),
        runtime_configuration={"epochs": 1.0, "seed": 7},
    )
    second = fine_tuning_input_fingerprint(
        cell,
        (_row(),),
        (_row(),),
        runtime_configuration={"epochs": 3.0, "seed": 7},
    )

    assert first != second


def test_completed_cell_receipt_can_be_loaded_without_retraining(tmp_path) -> None:
    checkpoint = tmp_path / "checkpoint-a"
    checkpoint.mkdir()
    (checkpoint / "config.json").write_text("{}", encoding="utf-8")
    result = HuggingFaceFineTuningResult(
        model_id="test/model",
        task="CONCEPT",
        checkpoint=str(checkpoint),
        device="cuda:0",
        train_count=1,
        calibration_count=1,
        evaluation_loss=0.25,
        predictions=(EncoderCalibrationPrediction(
            example_id="example-1",
            source_slice="SEC_10K",
            gold_label="REVENUE",
            predicted_label="REVENUE",
            confidence=0.9,
        ),),
        input_fingerprint="f" * 64,
    )
    receipt = tmp_path / "result.json"
    write_fine_tuning_result_receipt(receipt, result)

    loaded = load_fine_tuning_result_receipt(
        receipt,
        expected_model_id="test/model",
        expected_task="CONCEPT",
        expected_input_fingerprint="f" * 64,
    )

    assert loaded == HuggingFaceFineTuningResult(
        **{**result.__dict__, "resumed_from_receipt": True}
    )


def test_receipt_rejects_changed_training_corpus(tmp_path) -> None:
    checkpoint = tmp_path / "checkpoint-a"
    checkpoint.mkdir()
    (checkpoint / "config.json").write_text("{}", encoding="utf-8")
    result = HuggingFaceFineTuningResult(
        model_id="test/model",
        task="CONCEPT",
        checkpoint=str(checkpoint),
        device="cuda:0",
        train_count=1,
        calibration_count=1,
        evaluation_loss=0.25,
        predictions=(),
        input_fingerprint="f" * 64,
    )
    receipt = tmp_path / "result.json"
    write_fine_tuning_result_receipt(receipt, result)

    with pytest.raises(ValueError, match="input fingerprint mismatch"):
        load_fine_tuning_result_receipt(
            receipt,
            expected_model_id="test/model",
            expected_task="CONCEPT",
            expected_input_fingerprint="0" * 64,
        )


def test_completed_receipt_is_checked_before_heavy_runtime_imports(
    tmp_path, monkeypatch
) -> None:
    cell = _cell(tmp_path)
    train_rows = (_row(),)
    calibration_rows = (_row(),)
    runtime = HuggingFaceFineTuningRuntime()
    fingerprint = fine_tuning_input_fingerprint(
        cell,
        train_rows,
        calibration_rows,
        runtime_configuration={
            "epochs": 3.0,
            "learning_rate": 2e-5,
            "weight_decay": 0.01,
            "seed": 20260906,
        },
    )
    checkpoint = tmp_path / f"checkpoint-{fingerprint[:16]}"
    checkpoint.mkdir()
    (checkpoint / "config.json").write_text("{}", encoding="utf-8")
    receipt = tmp_path / f"result-{fingerprint[:16]}.json"
    write_fine_tuning_result_receipt(
        receipt,
        HuggingFaceFineTuningResult(
            model_id=cell.model_id,
            task=cell.task.value,
            checkpoint=str(checkpoint),
            device="cuda:0",
            train_count=1,
            calibration_count=1,
            evaluation_loss=0.25,
            predictions=(),
            input_fingerprint=fingerprint,
        ),
    )

    def reject_import(name: str):
        raise AssertionError(f"heavy runtime imported before receipt: {name}")

    monkeypatch.setattr(hf_runtime, "import_module", reject_import)

    result = runtime.train(cell, train_rows, calibration_rows)

    assert result.resumed_from_receipt is True
