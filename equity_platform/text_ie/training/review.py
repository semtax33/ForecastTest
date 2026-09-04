from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class ReviewAnnotation:
    review_id: str
    should_review: bool
    category: str
    reviewer: str
    note: str = ""


def load_review_annotations(path: Path) -> tuple[ReviewAnnotation, ...]:
    rows = tuple(
        ReviewAnnotation(
            review_id=str(row["review_id"]),
            should_review=bool(row["should_review"]),
            category=str(row["category"]),
            reviewer=str(row["reviewer"]),
            note=str(row.get("note", "")),
        )
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
        for row in (json.loads(raw),)
    )
    ids = [row.review_id for row in rows]
    if not rows or len(ids) != len(set(ids)):
        raise ValueError("Review annotations must be non-empty with unique ids")
    return rows


def review_precision(
    predicted_review_ids: set[str],
    annotations: tuple[ReviewAnnotation, ...],
) -> dict[str, object]:
    annotated = {row.review_id: row for row in annotations}
    evaluated = predicted_review_ids & annotated.keys()
    true_positive = sum(annotated[item].should_review for item in evaluated)
    false_positive = sum(not annotated[item].should_review for item in evaluated)
    missing = annotated.keys() - predicted_review_ids
    false_negative = sum(annotated[item].should_review for item in missing)
    return {
        "annotated": len(annotations),
        "evaluated": len(evaluated),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": true_positive / (true_positive + false_positive) if evaluated else 0.0,
        "recall": true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0,
        "annotation_coverage": len(evaluated) / len(annotations),
        "queue_annotation_coverage": (
            len(evaluated) / len(predicted_review_ids)
            if predicted_review_ids
            else 1.0
        ),
    }
