from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectivePrediction:
    example_id: str
    source_slice: str
    gold_label: str
    predicted_label: str | None
    abstention_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.example_id or not self.source_slice or not self.gold_label:
            raise ValueError("selective predictions require identity, source, and gold")
        if self.predicted_label is not None and self.abstention_reason is not None:
            raise ValueError("one prediction cannot be both emitted and abstained")


@dataclass(frozen=True)
class SelectiveTaskMetrics:
    total_gold: int
    predicted: int
    correct: int
    explicit_abstentions: int
    silent_miss: int
    precision: float
    recall: float
    coverage: float
    abstention_rate: float
    coverage_adjusted_precision: float


@dataclass(frozen=True)
class SemanticProductionGateInput:
    concept: SelectiveTaskMetrics
    binding: SelectiveTaskMetrics
    role: SelectiveTaskMetrics
    deterministic_frame_precision: float
    deterministic_frame_recall: float
    hybrid_frame_precision: float
    hybrid_frame_recall: float
    cross_clause_violations: int
    issuer_disjoint_pass: bool
    document_disjoint_pass: bool
    all_source_slices_pass: bool


@dataclass(frozen=True)
class SemanticProductionGateResult:
    passed: bool
    reasons: tuple[str, ...]


def evaluate_selective_predictions(
    predictions: tuple[SelectivePrediction, ...],
) -> SelectiveTaskMetrics:
    ids = [item.example_id for item in predictions]
    if not predictions or len(ids) != len(set(ids)):
        raise ValueError("evaluation requires non-empty unique example ids")
    emitted = tuple(item for item in predictions if item.predicted_label is not None)
    correct = sum(item.predicted_label == item.gold_label for item in emitted)
    abstentions = sum(
        item.predicted_label is None and item.abstention_reason is not None
        for item in predictions
    )
    silent = sum(
        item.predicted_label is None and item.abstention_reason is None
        for item in predictions
    )
    total = len(predictions)
    precision = correct / len(emitted) if emitted else 0.0
    coverage = len(emitted) / total
    return SelectiveTaskMetrics(
        total_gold=total,
        predicted=len(emitted),
        correct=correct,
        explicit_abstentions=abstentions,
        silent_miss=silent,
        precision=precision,
        recall=correct / total,
        coverage=coverage,
        abstention_rate=abstentions / total,
        coverage_adjusted_precision=precision * coverage,
    )


def assess_semantic_production_gate(
    candidate: SemanticProductionGateInput,
    *,
    minimum_concept_precision: float = 0.98,
    minimum_binding_precision: float = 0.99,
    minimum_role_precision: float = 0.99,
) -> SemanticProductionGateResult:
    reasons = []
    if candidate.concept.precision < minimum_concept_precision:
        reasons.append("LOW_CONCEPT_PRECISION")
    if candidate.binding.precision < minimum_binding_precision:
        reasons.append("LOW_BINDING_PRECISION")
    if candidate.role.precision < minimum_role_precision:
        reasons.append("LOW_ROLE_PRECISION")
    if candidate.hybrid_frame_precision < candidate.deterministic_frame_precision:
        reasons.append("FINAL_FRAME_PRECISION_REGRESSION")
    if candidate.hybrid_frame_recall <= candidate.deterministic_frame_recall:
        reasons.append("NO_FRAME_RECALL_LIFT")
    if any(
        metrics.silent_miss
        for metrics in (candidate.concept, candidate.binding, candidate.role)
    ):
        reasons.append("SILENT_MISS")
    if candidate.cross_clause_violations:
        reasons.append("CROSS_CLAUSE_VIOLATION")
    if not candidate.issuer_disjoint_pass:
        reasons.append("ISSUER_DISJOINT_FAIL")
    if not candidate.document_disjoint_pass:
        reasons.append("DOCUMENT_DISJOINT_FAIL")
    if not candidate.all_source_slices_pass:
        reasons.append("SOURCE_SLICE_FAIL")
    return SemanticProductionGateResult(not reasons, tuple(reasons))


__all__ = [
    "SelectivePrediction",
    "SemanticProductionGateInput",
    "SemanticProductionGateResult",
    "SelectiveTaskMetrics",
    "assess_semantic_production_gate",
    "evaluate_selective_predictions",
]
