from __future__ import annotations

from dataclasses import dataclass


Span = tuple[int, int]


@dataclass(frozen=True)
class SpanEvaluationExample:
    example_id: str
    source_slice: str
    gold_spans: tuple[Span, ...]
    predicted_spans: tuple[Span, ...]

    def __post_init__(self) -> None:
        if not self.example_id or not self.source_slice:
            raise ValueError("span evaluation requires example and source identity")
        for span in (*self.gold_spans, *self.predicted_spans):
            if len(span) != 2 or span[0] < 0 or span[1] <= span[0]:
                raise ValueError("span evaluation requires ordered non-negative spans")
        if len(set(self.gold_spans)) != len(self.gold_spans):
            raise ValueError("gold spans must be unique")
        if len(set(self.predicted_spans)) != len(self.predicted_spans):
            raise ValueError("predicted spans must be unique")


@dataclass(frozen=True)
class ExactSpanMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float
    by_source_slice: dict[str, "ExactSpanMetrics"]


def _counts(examples: tuple[SpanEvaluationExample, ...]) -> tuple[int, int, int]:
    true_positive = false_positive = false_negative = 0
    for example in examples:
        gold = set(example.gold_spans)
        predicted = set(example.predicted_spans)
        true_positive += len(gold & predicted)
        false_positive += len(predicted - gold)
        false_negative += len(gold - predicted)
    return true_positive, false_positive, false_negative


def _metrics(
    examples: tuple[SpanEvaluationExample, ...],
    *,
    include_slices: bool,
) -> ExactSpanMetrics:
    true_positive, false_positive, false_negative = _counts(examples)
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
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    by_source = {}
    if include_slices:
        by_source = {
            source_slice: _metrics(
                tuple(row for row in examples if row.source_slice == source_slice),
                include_slices=False,
            )
            for source_slice in sorted({row.source_slice for row in examples})
        }
    return ExactSpanMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=f1,
        by_source_slice=by_source,
    )


def evaluate_exact_spans(
    examples: tuple[SpanEvaluationExample, ...],
) -> ExactSpanMetrics:
    if not examples:
        raise ValueError("span evaluation requires non-empty examples")
    ids = [row.example_id for row in examples]
    if len(ids) != len(set(ids)):
        raise ValueError("span evaluation example ids must be unique")
    return _metrics(examples, include_slices=True)


@dataclass(frozen=True)
class SpanSafetyGateInput:
    period_accuracy: float
    unit_accuracy: float
    binding_precision: float
    guidance_actual_accuracy: float
    scope_accuracy: float
    span_recall: float
    explicit_abstention_rate: float
    silent_miss_count: int

    def __post_init__(self) -> None:
        values = (
            self.period_accuracy,
            self.unit_accuracy,
            self.binding_precision,
            self.guidance_actual_accuracy,
            self.scope_accuracy,
            self.span_recall,
            self.explicit_abstention_rate,
        )
        if any(not 0.0 <= value <= 1.0 for value in values):
            raise ValueError("span safety rates must be within [0, 1]")
        if self.silent_miss_count < 0:
            raise ValueError("silent miss count cannot be negative")


@dataclass(frozen=True)
class SpanSafetyGateResult:
    passed: bool
    reasons: tuple[str, ...]


def assess_span_safety_gate(
    candidate: SpanSafetyGateInput,
    *,
    minimum_binding_precision: float = 0.99,
    minimum_guidance_actual_accuracy: float = 0.99,
    minimum_scope_accuracy: float = 0.99,
    minimum_span_recall: float = 0.90,
) -> SpanSafetyGateResult:
    """Gate downstream semantics before considering candidate-span recall."""

    reasons = []
    if candidate.period_accuracy < 1.0:
        reasons.append("PERIOD_ACCURACY_BELOW_100_PERCENT")
    if candidate.unit_accuracy < 1.0:
        reasons.append("UNIT_ACCURACY_BELOW_100_PERCENT")
    if candidate.binding_precision < minimum_binding_precision:
        reasons.append("LOW_BINDING_PRECISION")
    if candidate.guidance_actual_accuracy < minimum_guidance_actual_accuracy:
        reasons.append("LOW_GUIDANCE_ACTUAL_ACCURACY")
    if candidate.scope_accuracy < minimum_scope_accuracy:
        reasons.append("LOW_SCOPE_ACCURACY")
    if candidate.silent_miss_count:
        reasons.append("SILENT_MISS")
    if candidate.span_recall < minimum_span_recall:
        reasons.append("LOW_SPAN_RECALL")
    # Span recall is checked last and cannot compensate for an earlier
    # semantic safety failure. Explicit abstention remains a valid outcome.
    return SpanSafetyGateResult(passed=not reasons, reasons=tuple(reasons))


__all__ = [
    "ExactSpanMetrics",
    "SpanEvaluationExample",
    "SpanSafetyGateInput",
    "SpanSafetyGateResult",
    "assess_span_safety_gate",
    "evaluate_exact_spans",
]
