from __future__ import annotations

from dataclasses import dataclass

from ..model import TextExtractionResult


@dataclass(frozen=True)
class WeakLabel:
    source_sha256: str
    sentence_start: int
    sentence_end: int
    labeling_function: str
    label: str
    confidence: float
    abstained: bool


def weak_labels_from_result(result: TextExtractionResult) -> tuple[WeakLabel, ...]:
    labels = [
        WeakLabel(
            source_sha256=frame.source.sha256,
            sentence_start=frame.source_span.char_start,
            sentence_end=frame.source_span.char_end,
            labeling_function=f"{frame.rule_id}@{frame.rule_version}",
            label=f"{frame.frame.value}:{frame.concept}",
            confidence=frame.extraction_confidence,
            abstained=False,
        )
        for frame in result.frames
    ]
    labels.extend(
        WeakLabel(
            source_sha256="",
            sentence_start=review.source_span.char_start,
            sentence_end=review.source_span.char_end,
            labeling_function=review.rule_id,
            label=review.status,
            confidence=0.0,
            abstained=True,
        )
        for review in result.reviews
    )
    return tuple(labels)

