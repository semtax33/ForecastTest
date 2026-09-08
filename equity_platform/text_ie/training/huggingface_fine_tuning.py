from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
from typing import Mapping

from ..llm.encoder_compatibility import preprocess_encoder_text
from ..llm.transformer_backend import (
    TransformerDevicePolicy,
    resolve_transformer_device,
)
from .encoder_selection import EncoderCalibrationPrediction
from .fine_tuning import SemanticFineTuningCell


def configure_pytorch_only_transformers_environment() -> None:
    """Prevent an unrelated TensorFlow/Keras install from breaking Trainer."""

    os.environ["USE_TF"] = "0"
    os.environ["USE_TORCH"] = "1"


def trainer_checkpoint_policy() -> dict[str, object]:
    """Return the fail-closed checkpoint policy used by resumable cell runs.

    A cell becomes reusable only after its final checkpoint and atomic result
    receipt both exist.  Intermediate Trainer checkpoints are therefore both
    redundant and unsafe to treat as completion evidence.
    """

    return {
        "save_strategy": "no",
        "load_best_model_at_end": False,
    }


@dataclass(frozen=True)
class HuggingFaceFineTuningResult:
    model_id: str
    task: str
    checkpoint: str
    device: str
    train_count: int
    calibration_count: int
    evaluation_loss: float
    predictions: tuple[EncoderCalibrationPrediction, ...]
    input_fingerprint: str
    resumed_from_receipt: bool = False


def fine_tuning_input_fingerprint(
    cell: SemanticFineTuningCell,
    train_rows: tuple,
    calibration_rows: tuple,
    *,
    runtime_configuration: Mapping[str, object] | None = None,
) -> str:
    """Bind a cell receipt to its model, hyperparameters and exact row payload."""

    cell_payload = {
        "model_id": cell.model_id,
        "task": cell.task.value,
        "labels": list(cell.labels),
        "device_policy": cell.device_policy,
        "per_device_batch_size": cell.per_device_batch_size,
        "gradient_accumulation_steps": cell.gradient_accumulation_steps,
        "max_length": cell.max_length,
    }
    payload = {
        "cell": cell_payload,
        "runtime": dict(runtime_configuration or {}),
        "train": [vars(row) for row in train_rows],
        "calibration": [vars(row) for row in calibration_rows],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def write_fine_tuning_result_receipt(
    path: Path,
    result: HuggingFaceFineTuningResult,
) -> None:
    payload = {
        "schema_version": "1.0.0",
        **asdict(replace(result, resumed_from_receipt=False)),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_fine_tuning_result_receipt(
    path: Path,
    *,
    expected_model_id: str,
    expected_task: str,
    expected_input_fingerprint: str,
) -> HuggingFaceFineTuningResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0.0":
        raise ValueError("unsupported fine-tuning receipt schema")
    if payload.get("model_id") != expected_model_id:
        raise ValueError("fine-tuning receipt model mismatch")
    if payload.get("task") != expected_task:
        raise ValueError("fine-tuning receipt task mismatch")
    if payload.get("input_fingerprint") != expected_input_fingerprint:
        raise ValueError("fine-tuning receipt input fingerprint mismatch")
    checkpoint = Path(str(payload["checkpoint"]))
    if not checkpoint.is_dir() or not (checkpoint / "config.json").is_file():
        raise ValueError("fine-tuning receipt checkpoint is incomplete")
    predictions = tuple(
        EncoderCalibrationPrediction(**row) for row in payload["predictions"]
    )
    return HuggingFaceFineTuningResult(
        model_id=str(payload["model_id"]),
        task=str(payload["task"]),
        checkpoint=str(checkpoint),
        device=str(payload["device"]),
        train_count=int(payload["train_count"]),
        calibration_count=int(payload["calibration_count"]),
        evaluation_loss=float(payload["evaluation_loss"]),
        predictions=predictions,
        input_fingerprint=str(payload["input_fingerprint"]),
        resumed_from_receipt=True,
    )


class _EncodedRows:
    def __init__(self, rows, *, tokenizer, label2id, model_id, max_length, nlp) -> None:
        self.rows = rows
        self.features = []
        for row in rows:
            text = preprocess_encoder_text(
                row.marked_context,
                model_id=model_id,
                tokenizer=tokenizer,
                nlp=nlp,
            )
            encoded = tokenizer(text, truncation=True, max_length=max_length)
            encoded["labels"] = label2id[_row_label(row)]
            self.features.append(encoded)

    def __len__(self) -> int:
        return len(self.features)

    def __getitem__(self, index: int):
        return self.features[index]


def _row_label(row) -> str:
    if hasattr(row, "binding_label"):
        return row.binding_label
    if hasattr(row, "role_label"):
        return row.role_label
    return row.concept_label


class HuggingFaceFineTuningRuntime:
    """Sequential CUDA trainer for a 4 GB-class research GPU.

    Each task model is loaded, trained, saved and released independently. The
    runtime receives TRAIN and CALIBRATION only; certification cannot leak into
    model fitting or checkpoint selection through this interface.
    """

    def __init__(
        self,
        *,
        epochs: float = 3.0,
        learning_rate: float = 2e-5,
        weight_decay: float = 0.01,
        seed: int = 20260906,
    ) -> None:
        if epochs <= 0 or learning_rate <= 0 or weight_decay < 0:
            raise ValueError("fine-tuning hyperparameters are invalid")
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.seed = seed

    def train(self, cell: SemanticFineTuningCell, train_rows, calibration_rows):
        if cell.device_policy != TransformerDevicePolicy.CUDA_REQUIRED.value:
            raise ValueError("production semantic fine-tuning must require CUDA")
        output = Path(cell.output_directory)
        output.mkdir(parents=True, exist_ok=True)
        runtime_configuration = {
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "weight_decay": self.weight_decay,
            "seed": self.seed,
        }
        input_fingerprint = fine_tuning_input_fingerprint(
            cell,
            train_rows,
            calibration_rows,
            runtime_configuration=runtime_configuration,
        )
        run_key = input_fingerprint[:16]
        receipt = output / f"result-{run_key}.json"
        if receipt.exists():
            return load_fine_tuning_result_receipt(
                receipt,
                expected_model_id=cell.model_id,
                expected_task=cell.task.value,
                expected_input_fingerprint=input_fingerprint,
            )
        configure_pytorch_only_transformers_environment()
        torch = import_module("torch")
        transformers = import_module("transformers")
        spacy = import_module("spacy")
        selected = resolve_transformer_device(
            torch_module=torch,
            policy=TransformerDevicePolicy.CUDA_REQUIRED,
        )
        label2id = {label: index for index, label in enumerate(cell.labels)}
        id2label = {index: label for label, index in label2id.items()}
        tokenizer = transformers.AutoTokenizer.from_pretrained(cell.model_id)
        added = tokenizer.add_special_tokens({
            "additional_special_tokens": [
                "[METRIC]", "[/METRIC]", "[QTY]", "[/QTY]",
            ]
        })
        model = transformers.AutoModelForSequenceClassification.from_pretrained(
            cell.model_id,
            num_labels=len(cell.labels),
            label2id=label2id,
            id2label=id2label,
            ignore_mismatched_sizes=True,
        )
        if added:
            model.resize_token_embeddings(len(tokenizer))
        nlp = spacy.blank("en")
        train_dataset = _EncodedRows(
            train_rows,
            tokenizer=tokenizer,
            label2id=label2id,
            model_id=cell.model_id,
            max_length=cell.max_length,
            nlp=nlp,
        )
        calibration_dataset = _EncodedRows(
            calibration_rows,
            tokenizer=tokenizer,
            label2id=label2id,
            model_id=cell.model_id,
            max_length=cell.max_length,
            nlp=nlp,
        )
        checkpoint_policy = trainer_checkpoint_policy()
        arguments = transformers.TrainingArguments(
            output_dir=str(output / f"trainer-{run_key}"),
            overwrite_output_dir=True,
            num_train_epochs=self.epochs,
            learning_rate=self.learning_rate,
            weight_decay=self.weight_decay,
            per_device_train_batch_size=cell.per_device_batch_size,
            per_device_eval_batch_size=cell.per_device_batch_size,
            gradient_accumulation_steps=cell.gradient_accumulation_steps,
            fp16=True,
            use_cpu=False,
            eval_strategy="epoch",
            # A completed cell is persisted below as one fingerprinted checkpoint
            # plus an atomic receipt.  Trainer's extra epoch checkpoint duplicates
            # a ~440 MB write and has been observed to stall on Windows while
            # replacing its temporary safetensors file.  It is not a recovery
            # boundary because a cell without a receipt is deliberately rerun.
            save_strategy=checkpoint_policy["save_strategy"],
            logging_strategy="epoch",
            load_best_model_at_end=checkpoint_policy["load_best_model_at_end"],
            dataloader_num_workers=0,
            report_to=[],
            seed=self.seed,
            data_seed=self.seed,
        )
        trainer = transformers.Trainer(
            model=model,
            args=arguments,
            train_dataset=train_dataset,
            eval_dataset=calibration_dataset,
            data_collator=transformers.DataCollatorWithPadding(tokenizer=tokenizer),
            processing_class=tokenizer,
        )
        try:
            trainer.train()
            prediction_output = trainer.predict(calibration_dataset)
            probabilities = torch.softmax(
                torch.as_tensor(prediction_output.predictions), dim=-1
            )
            confidence, predicted_ids = probabilities.max(dim=-1)
            predictions = tuple(
                EncoderCalibrationPrediction(
                    example_id=row.example_id,
                    source_slice=row.source_kind,
                    gold_label=_row_label(row),
                    predicted_label=id2label[int(predicted_id)],
                    confidence=float(score),
                )
                for row, predicted_id, score in zip(
                    calibration_rows,
                    predicted_ids.tolist(),
                    confidence.tolist(),
                    strict=True,
                )
            )
            checkpoint = output / f"checkpoint-{run_key}"
            trainer.save_model(str(checkpoint))
            tokenizer.save_pretrained(str(checkpoint))
            evaluation_loss = float(prediction_output.metrics.get("test_loss", 0.0))
        finally:
            model.to("cpu")
            del trainer
            del model
            del tokenizer
            torch.cuda.empty_cache()
        result = HuggingFaceFineTuningResult(
            model_id=cell.model_id,
            task=cell.task.value,
            checkpoint=str(checkpoint),
            device=selected.device,
            train_count=len(train_rows),
            calibration_count=len(calibration_rows),
            evaluation_loss=evaluation_loss,
            predictions=predictions,
            input_fingerprint=input_fingerprint,
        )
        write_fine_tuning_result_receipt(receipt, result)
        return result

    def predict(
        self,
        cell: SemanticFineTuningCell,
        rows: tuple,
        *,
        checkpoint: str,
    ) -> tuple[EncoderCalibrationPrediction, ...]:
        """Score a frozen holdout without any fitting or threshold changes."""

        if not rows:
            raise ValueError("certification prediction requires non-empty rows")
        configure_pytorch_only_transformers_environment()
        torch = import_module("torch")
        transformers = import_module("transformers")
        spacy = import_module("spacy")
        selected = resolve_transformer_device(
            torch_module=torch,
            policy=TransformerDevicePolicy.CUDA_REQUIRED,
        )
        tokenizer = transformers.AutoTokenizer.from_pretrained(checkpoint)
        model = transformers.AutoModelForSequenceClassification.from_pretrained(
            checkpoint
        )
        model.to(selected.device)
        model.eval()
        label2id = {str(label): int(index) for label, index in model.config.label2id.items()}
        id2label = {int(index): str(label) for index, label in model.config.id2label.items()}
        dataset = _EncodedRows(
            rows,
            tokenizer=tokenizer,
            label2id=label2id,
            model_id=cell.model_id,
            max_length=cell.max_length,
            nlp=spacy.blank("en"),
        )
        loader = torch.utils.data.DataLoader(
            dataset,
            batch_size=cell.per_device_batch_size,
            shuffle=False,
            num_workers=0,
            collate_fn=transformers.DataCollatorWithPadding(
                tokenizer=tokenizer,
                return_tensors="pt",
            ),
        )
        predicted_ids = []
        confidences = []
        try:
            for batch in loader:
                batch.pop("labels", None)
                batch = {key: value.to(selected.device) for key, value in batch.items()}
                with torch.inference_mode(), torch.autocast(
                    device_type="cuda", dtype=torch.float16
                ):
                    logits = model(**batch).logits
                probability = torch.softmax(logits, dim=-1)
                confidence, predicted = probability.max(dim=-1)
                predicted_ids.extend(predicted.detach().cpu().tolist())
                confidences.extend(confidence.detach().cpu().tolist())
        finally:
            model.to("cpu")
            del model
            del tokenizer
            torch.cuda.empty_cache()
        return tuple(
            EncoderCalibrationPrediction(
                example_id=row.example_id,
                source_slice=row.source_kind,
                gold_label=_row_label(row),
                predicted_label=id2label[int(predicted_id)],
                confidence=float(confidence),
            )
            for row, predicted_id, confidence in zip(
                rows, predicted_ids, confidences, strict=True
            )
        )


__all__ = [
    "HuggingFaceFineTuningResult",
    "HuggingFaceFineTuningRuntime",
    "configure_pytorch_only_transformers_environment",
    "fine_tuning_input_fingerprint",
    "load_fine_tuning_result_receipt",
    "write_fine_tuning_result_receipt",
]
