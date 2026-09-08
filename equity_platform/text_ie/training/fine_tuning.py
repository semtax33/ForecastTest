from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from ..llm.encoder_registry import DEFAULT_ENCODER_CANDIDATES, EncoderSourceSlice
from ..llm.transformer_backend import TransformerDevicePolicy
from ..semantic_challenger import SemanticTask
from .dataset import (
    SemanticTrainingDataset,
    SemanticTrainingReadiness,
    assess_semantic_training_readiness,
)


_SPLITS = ("TRAIN", "CALIBRATION", "CERTIFICATION")


class SemanticTrainingAuthority(StrEnum):
    BLOCKED = "BLOCKED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    CALIBRATION_ALLOWED = "CALIBRATION_ALLOWED"

    @property
    def training_allowed(self) -> bool:
        return self is not SemanticTrainingAuthority.BLOCKED

    @property
    def calibration_champion_allowed(self) -> bool:
        return self is SemanticTrainingAuthority.CALIBRATION_ALLOWED


def assess_semantic_training_authority(
    *,
    training_ready: bool,
    all_benchmark_slices_ready: bool,
) -> SemanticTrainingAuthority:
    """Separate research fitting authority from champion-selection authority."""

    if not training_ready:
        return SemanticTrainingAuthority.BLOCKED
    if not all_benchmark_slices_ready:
        return SemanticTrainingAuthority.RESEARCH_ONLY
    return SemanticTrainingAuthority.CALIBRATION_ALLOWED


@dataclass(frozen=True)
class SemanticTrainingMinimums:
    text_contexts: int = 300
    concept_examples: int = 300
    relation_pairs: int = 500
    role_examples: int = 200
    positive_bindings: int = 200
    negative_bindings: int = 200

    def __post_init__(self) -> None:
        if any(value < 1 for value in (
            self.text_contexts,
            self.concept_examples,
            self.relation_pairs,
            self.role_examples,
            self.positive_bindings,
            self.negative_bindings,
        )):
            raise ValueError("semantic training minimums must all be positive")


@dataclass(frozen=True)
class SemanticFineTuningCell:
    model_id: str
    task: SemanticTask
    labels: tuple[str, ...]
    train_count: int
    calibration_count: int
    certification_count: int
    train_source_counts: dict[str, int]
    calibration_source_counts: dict[str, int]
    certification_source_counts: dict[str, int]
    output_directory: str
    device_policy: str
    per_device_batch_size: int
    gradient_accumulation_steps: int
    max_length: int


@dataclass(frozen=True)
class SemanticFineTuningPlan:
    cells: tuple[SemanticFineTuningCell, ...]
    readiness: SemanticTrainingReadiness
    issuer_disjoint_pass: bool
    document_disjoint_pass: bool
    certification_sealed: bool


class SemanticFineTuningRuntime(Protocol):
    def train(self, cell, train_rows: tuple, calibration_rows: tuple): ...


def _task_rows(dataset: SemanticTrainingDataset):
    return {
        SemanticTask.CONCEPT: dataset.concepts,
        SemanticTask.BINDING: dataset.relations,
        SemanticTask.ROLE: dataset.roles,
    }


def _label(task: SemanticTask, row) -> str:
    if task is SemanticTask.CONCEPT:
        return row.concept_label
    if task is SemanticTask.BINDING:
        return row.binding_label
    return row.role_label


def _assert_disjoint(dataset: SemanticTrainingDataset) -> tuple[bool, bool]:
    entity_splits: dict[str, set[str]] = defaultdict(set)
    document_splits: dict[str, set[str]] = defaultdict(set)
    for rows in _task_rows(dataset).values():
        for row in rows:
            if row.holdout_axis not in _SPLITS:
                raise ValueError(f"unsupported semantic data split: {row.holdout_axis}")
            entity_splits[row.entity].add(row.holdout_axis)
            document_splits[row.source_sha256].add(row.holdout_axis)
    if any(len(splits) != 1 for splits in entity_splits.values()):
        raise ValueError("issuer crosses semantic data splits")
    if any(len(splits) != 1 for splits in document_splits.values()):
        raise ValueError("document crosses semantic data splits")
    return True, True


def build_semantic_fine_tuning_plan(
    dataset: SemanticTrainingDataset,
    *,
    output_root: Path,
    minimums: SemanticTrainingMinimums = SemanticTrainingMinimums(),
    per_device_batch_size: int = 2,
    gradient_accumulation_steps: int = 8,
    max_length: int = 512,
) -> SemanticFineTuningPlan:
    """Plan sequential CUDA fine-tuning without opening certification labels.

    Calibration may select confidence thresholds and a champion. Certification
    is carried through only as a sealed count until that selection is frozen.
    """

    if per_device_batch_size < 1 or gradient_accumulation_steps < 1:
        raise ValueError("GPU batch and accumulation sizes must be positive")
    if max_length < 32:
        raise ValueError("max_length must be at least 32")
    readiness = assess_semantic_training_readiness(
        dataset,
        minimum_text_contexts=minimums.text_contexts,
        minimum_concept_examples=minimums.concept_examples,
        minimum_relation_pairs=minimums.relation_pairs,
        minimum_role_examples=minimums.role_examples,
        minimum_positive_bindings=minimums.positive_bindings,
        minimum_negative_bindings=minimums.negative_bindings,
    )
    if not readiness.ready:
        raise ValueError(
            "semantic fine-tuning corpus is not ready: " + "|".join(readiness.reasons)
        )
    issuer_disjoint, document_disjoint = _assert_disjoint(dataset)
    required_sources = {source.value for source in EncoderSourceSlice}
    task_partitions = {}
    for task, rows in _task_rows(dataset).items():
        partitions = {
            split: tuple(row for row in rows if row.holdout_axis == split)
            for split in _SPLITS
        }
        for split, split_rows in partitions.items():
            if not split_rows:
                raise ValueError(f"{task.value} has no {split} examples")
            observed = {row.source_kind for row in split_rows}
            missing = required_sources - observed
            if missing:
                raise ValueError(
                    f"{task.value} {split} is missing source slices: {sorted(missing)}"
                )
            if split in {"CALIBRATION", "CERTIFICATION"} and any(
                row.annotation_source != "INDEPENDENT_HUMAN_GOLD_A"
                for row in split_rows
            ):
                raise ValueError(
                    f"{task.value} {split} may contain only complete-context GOLD_A"
                )
        train_labels = {_label(task, row) for row in partitions["TRAIN"]}
        for split in ("CALIBRATION", "CERTIFICATION"):
            unseen = {
                _label(task, row) for row in partitions[split]
            } - train_labels
            if unseen:
                raise ValueError(
                    f"{task.value} {split} has unseen labels: {sorted(unseen)}"
                )
        task_partitions[task] = partitions
    cells = []
    for candidate in DEFAULT_ENCODER_CANDIDATES:
        safe_model_name = candidate.model_id.replace("/", "--")
        for task in SemanticTask:
            partitions = task_partitions[task]
            source_counts = {
                split: dict(sorted(Counter(
                    row.source_kind for row in partitions[split]
                ).items()))
                for split in _SPLITS
            }
            cells.append(SemanticFineTuningCell(
                model_id=candidate.model_id,
                task=task,
                labels=tuple(sorted({
                    _label(task, row) for row in partitions["TRAIN"]
                })),
                train_count=len(partitions["TRAIN"]),
                calibration_count=len(partitions["CALIBRATION"]),
                certification_count=len(partitions["CERTIFICATION"]),
                train_source_counts=source_counts["TRAIN"],
                calibration_source_counts=source_counts["CALIBRATION"],
                certification_source_counts=source_counts["CERTIFICATION"],
                output_directory=str(output_root / safe_model_name / task.value.lower()),
                device_policy=TransformerDevicePolicy.CUDA_REQUIRED.value,
                per_device_batch_size=per_device_batch_size,
                gradient_accumulation_steps=gradient_accumulation_steps,
                max_length=max_length,
            ))
    return SemanticFineTuningPlan(
        cells=tuple(cells),
        readiness=readiness,
        issuer_disjoint_pass=issuer_disjoint,
        document_disjoint_pass=document_disjoint,
        certification_sealed=True,
    )


def run_semantic_fine_tuning_plan(
    plan: SemanticFineTuningPlan,
    dataset: SemanticTrainingDataset,
    *,
    runtime: SemanticFineTuningRuntime | None = None,
) -> tuple:
    """Train every encoder/head cell while keeping certification sealed."""

    if not plan.readiness.ready or not plan.certification_sealed:
        raise ValueError("fine-tuning requires a ready plan with sealed certification")
    if runtime is None:
        from .huggingface_fine_tuning import HuggingFaceFineTuningRuntime

        runtime = HuggingFaceFineTuningRuntime()
    task_rows = _task_rows(dataset)
    results = []
    for cell in plan.cells:
        rows = task_rows[cell.task]
        train_rows = tuple(row for row in rows if row.holdout_axis == "TRAIN")
        calibration_rows = tuple(
            row for row in rows if row.holdout_axis == "CALIBRATION"
        )
        if len(train_rows) != cell.train_count:
            raise ValueError(f"{cell.task.value} train count changed after planning")
        if len(calibration_rows) != cell.calibration_count:
            raise ValueError(
                f"{cell.task.value} calibration count changed after planning"
            )
        results.append(runtime.train(cell, train_rows, calibration_rows))
    return tuple(results)


__all__ = [
    "SemanticFineTuningCell",
    "SemanticFineTuningPlan",
    "SemanticTrainingMinimums",
    "SemanticTrainingAuthority",
    "assess_semantic_training_authority",
    "build_semantic_fine_tuning_plan",
    "run_semantic_fine_tuning_plan",
]
