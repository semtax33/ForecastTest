from __future__ import annotations

from collections import Counter, defaultdict
from statistics import fmean
from typing import Mapping, Sequence


PredictionRow = Mapping[str, object]


def _validate(rows: Sequence[PredictionRow]) -> None:
    if not rows:
        raise ValueError("research evaluation requires non-empty predictions")
    for row in rows:
        confidence = float(row["confidence"])
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("prediction confidence must be within [0, 1]")


def _metrics(rows: Sequence[PredictionRow]) -> dict[str, object]:
    gold = [str(row["gold_label"]) for row in rows]
    predicted = [str(row["predicted_label"]) for row in rows]
    confidences = [float(row["confidence"]) for row in rows]
    correct = [left == right for left, right in zip(gold, predicted, strict=True)]
    labels = sorted(set(gold) | set(predicted))
    per_label = {}
    f1_scores = []
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for left, right in zip(gold, predicted, strict=True):
        confusion[left][right] += 1
    for label in labels:
        true_positive = sum(
            left == label and right == label
            for left, right in zip(gold, predicted, strict=True)
        )
        false_positive = sum(
            left != label and right == label
            for left, right in zip(gold, predicted, strict=True)
        )
        false_negative = sum(
            left == label and right != label
            for left, right in zip(gold, predicted, strict=True)
        )
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = (
            2.0 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        f1_scores.append(f1)
        per_label[label] = {
            "support": gold.count(label),
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    error_confidences = [
        confidence
        for confidence, is_correct in zip(confidences, correct, strict=True)
        if not is_correct
    ]
    return {
        "count": len(rows),
        "unique_example_count": len({str(row["example_id"]) for row in rows}),
        "accuracy": sum(correct) / len(rows),
        "macro_f1": fmean(f1_scores),
        "naive_majority_accuracy": max(Counter(gold).values()) / len(rows),
        "mean_confidence": fmean(confidences),
        "mean_error_confidence": (
            fmean(error_confidences) if error_confidences else None
        ),
        "per_label": per_label,
        "confusion": {
            label: dict(sorted(confusion[label].items())) for label in labels
        },
    }


def evaluate_research_predictions(
    rows: Sequence[PredictionRow],
) -> dict[str, object]:
    """Score raw calibration predictions without selecting or calibrating a model.

    These metrics are descriptive research diagnostics.  They intentionally do
    not tune confidence thresholds, rank encoders, or open certification.
    """

    _validate(rows)
    result = _metrics(rows)
    sources = sorted({str(row["source_slice"]) for row in rows})
    result["by_source_slice"] = {
        source: _metrics(
            tuple(row for row in rows if str(row["source_slice"]) == source)
        )
        for source in sources
    }
    return result


def build_research_diagnostics(
    receipts: Sequence[PredictionRow],
    *,
    expected_matrix: Sequence[tuple[str, str]],
) -> dict[str, object]:
    """Build a descriptive report while keeping calibration authority locked."""

    expected = tuple(expected_matrix)
    if not expected or len(set(expected)) != len(expected):
        raise ValueError("expected research matrix must be non-empty and unique")
    indexed = {}
    for receipt in receipts:
        key = (str(receipt["model_id"]), str(receipt["task"]))
        if key in indexed:
            raise ValueError("duplicate cell in research diagnostic matrix")
        indexed[key] = receipt
    if set(indexed) != set(expected):
        raise ValueError("research diagnostic matrix is incomplete or unexpected")
    cells = []
    for model_id, task in expected:
        receipt = indexed[(model_id, task)]
        predictions = tuple(receipt.get("predictions", ()))
        cells.append({
            "model_id": model_id,
            "task": task,
            "checkpoint": str(receipt["checkpoint"]),
            "device": str(receipt["device"]),
            "evaluation_loss": float(receipt["evaluation_loss"]),
            "metrics": evaluate_research_predictions(predictions),
        })
    return {
        "schema_version": "1.0.0",
        "status": "RESEARCH_DIAGNOSTICS_ONLY_CALIBRATION_LOCKED",
        "research_only": True,
        "calibration_allowed": False,
        "champion_model_id": None,
        "certification_opened": False,
        "cells": cells,
    }
