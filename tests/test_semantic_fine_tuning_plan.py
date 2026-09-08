from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from equity_platform.text_ie.llm import DEFAULT_ENCODER_CANDIDATES
from equity_platform.text_ie.semantic_challenger import SemanticTask
from equity_platform.text_ie.training import (
    ConceptClassificationExample,
    RelationClassificationExample,
    RoleClassificationExample,
    SemanticTrainingDataset,
    SemanticTrainingMinimums,
    build_semantic_fine_tuning_plan,
    run_semantic_fine_tuning_plan,
)


SLICES = ("SEC_10K", "SEC_10Q", "IR_PREPARED_REMARKS", "IR_QA")
SPLITS = ("TRAIN", "CALIBRATION", "CERTIFICATION")


def _dataset() -> SemanticTrainingDataset:
    concepts = []
    relations = []
    roles = []
    for split_index, split in enumerate(SPLITS):
        for slice_index, source_slice in enumerate(SLICES):
            suffix = f"{split}-{source_slice}"
            source_hash = f"{split_index * 10 + slice_index + 1:064x}"
            common = {
                "example_id": f"context-{suffix}",
                "entity": f"ENTITY-{suffix}",
                "source_kind": source_slice,
                "source_sha256": source_hash,
                "holdout_axis": split,
                "gold_route": "TEXT_IE",
                "context": "Revenue was $10 million.",
                "marked_context": "[METRIC]Revenue[/METRIC] was $10 million.",
                "metric_literal": "Revenue",
                "metric_char_start": 0,
                "metric_char_end": 7,
                "annotation_source": "INDEPENDENT_HUMAN_GOLD_A",
            }
            concepts.append(ConceptClassificationExample(
                **common,
                concept_label="REVENUE",
            ))
            pair_common = {
                **common,
                "marked_context": (
                    "[METRIC]Revenue[/METRIC] was [QTY]$10 million[/QTY]."
                ),
                "quantity_literal": "$10 million",
                "quantity_char_start": 12,
                "quantity_char_end": 23,
                "quantity_kind": "MONEY",
                "concept_label": "REVENUE",
            }
            relations.append(RelationClassificationExample(
                **{**pair_common, "example_id": f"positive-{suffix}"},
                binding_label="BELONGS_TO",
            ))
            relations.append(RelationClassificationExample(
                **{**pair_common, "example_id": f"negative-{suffix}"},
                binding_label="NOT_RELATED",
            ))
            roles.append(RoleClassificationExample(
                **{**pair_common, "example_id": f"role-{suffix}"},
                role_label="VALUE_CURRENT",
            ))
    return SemanticTrainingDataset(
        concepts=tuple(concepts),
        relations=tuple(relations),
        roles=tuple(roles),
        source_example_count=len(concepts),
    )


MINIMUMS = SemanticTrainingMinimums(
    text_contexts=1,
    concept_examples=1,
    relation_pairs=1,
    role_examples=1,
    positive_bindings=1,
    negative_bindings=1,
)


def test_plan_has_three_gpu_heads_per_encoder_and_sealed_certification(tmp_path) -> None:
    plan = build_semantic_fine_tuning_plan(
        _dataset(),
        output_root=tmp_path,
        minimums=MINIMUMS,
    )

    assert len(plan.cells) == len(DEFAULT_ENCODER_CANDIDATES) * len(SemanticTask)
    assert plan.issuer_disjoint_pass
    assert plan.document_disjoint_pass
    assert plan.certification_sealed
    assert all(cell.device_policy == "CUDA_REQUIRED" for cell in plan.cells)
    assert all(cell.train_count > 0 for cell in plan.cells)
    assert all(cell.calibration_count > 0 for cell in plan.cells)
    assert all(cell.certification_count > 0 for cell in plan.cells)
    assert all(set(cell.calibration_source_counts) == set(SLICES) for cell in plan.cells)
    assert all(set(cell.certification_source_counts) == set(SLICES) for cell in plan.cells)
    assert all(Path(cell.output_directory).is_relative_to(tmp_path) for cell in plan.cells)


def test_plan_rejects_issuer_leakage_before_gpu_training(tmp_path) -> None:
    dataset = _dataset()
    leaked = replace(dataset.concepts[-1], entity=dataset.concepts[0].entity)
    dataset = replace(dataset, concepts=(*dataset.concepts[:-1], leaked))

    with pytest.raises(ValueError, match="issuer.*crosses semantic data splits"):
        build_semantic_fine_tuning_plan(
            dataset,
            output_root=tmp_path,
            minimums=MINIMUMS,
        )


def test_plan_rejects_label_seen_only_in_certification(tmp_path) -> None:
    dataset = _dataset()
    changed = tuple(
        replace(row, role_label="UNSEEN_CERT_ROLE")
        if row.holdout_axis == "CERTIFICATION" and row.source_kind == "SEC_10K"
        else row
        for row in dataset.roles
    )

    with pytest.raises(ValueError, match="ROLE.*unseen labels"):
        build_semantic_fine_tuning_plan(
            replace(dataset, roles=changed),
            output_root=tmp_path,
            minimums=MINIMUMS,
        )


def test_training_orchestrator_never_passes_certification_rows_to_runtime(tmp_path) -> None:
    dataset = _dataset()
    plan = build_semantic_fine_tuning_plan(
        dataset,
        output_root=tmp_path,
        minimums=MINIMUMS,
    )

    class Runtime:
        def __init__(self) -> None:
            self.calls = []

        def train(self, cell, train_rows, calibration_rows):
            self.calls.append((cell, train_rows, calibration_rows))
            return {
                "model_id": cell.model_id,
                "task": cell.task.value,
                "checkpoint": cell.output_directory,
            }

    runtime = Runtime()
    results = run_semantic_fine_tuning_plan(plan, dataset, runtime=runtime)

    assert len(results) == 9
    assert len(runtime.calls) == 9
    for _, train_rows, calibration_rows in runtime.calls:
        assert {row.holdout_axis for row in train_rows} == {"TRAIN"}
        assert {row.holdout_axis for row in calibration_rows} == {"CALIBRATION"}


def test_plan_rejects_training_only_gold_b_from_calibration_or_certification(tmp_path) -> None:
    dataset = _dataset()
    contaminated = tuple(
        replace(
            row,
            annotation_source=(
                "INDEPENDENT_HUMAN_ADJUDICATED_GOLD_B_INCOMPLETE_GRAPH"
            ),
        )
        if row.holdout_axis == "CALIBRATION"
        else row
        for row in dataset.relations
    )

    with pytest.raises(ValueError, match="BINDING.*GOLD_A"):
        build_semantic_fine_tuning_plan(
            replace(dataset, relations=contaminated),
            output_root=tmp_path,
            minimums=MINIMUMS,
        )
