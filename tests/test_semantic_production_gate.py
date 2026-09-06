from __future__ import annotations

from dataclasses import replace

from equity_platform.text_ie.training import (
    SelectiveTaskMetrics,
    SemanticProductionGateInput,
    assess_semantic_production_gate,
)


def _metrics(precision: float, silent_miss: int = 0) -> SelectiveTaskMetrics:
    return SelectiveTaskMetrics(
        total_gold=100,
        predicted=100,
        correct=int(precision * 100),
        explicit_abstentions=0,
        silent_miss=silent_miss,
        precision=precision,
        recall=precision,
        coverage=1.0,
        abstention_rate=0.0,
        coverage_adjusted_precision=precision,
    )


def _passing_input() -> SemanticProductionGateInput:
    return SemanticProductionGateInput(
        concept=_metrics(0.98),
        binding=_metrics(0.99),
        role=_metrics(0.99),
        deterministic_frame_precision=0.99,
        deterministic_frame_recall=0.80,
        hybrid_frame_precision=0.99,
        hybrid_frame_recall=0.81,
        cross_clause_violations=0,
        issuer_disjoint_pass=True,
        document_disjoint_pass=True,
        all_source_slices_pass=True,
    )


def test_semantic_production_gate_requires_quality_and_generalization() -> None:
    result = assess_semantic_production_gate(_passing_input())

    assert result.passed
    assert result.reasons == ()


def test_semantic_production_gate_fails_on_silent_miss_or_no_recall_lift() -> None:
    candidate = replace(
        _passing_input(),
        concept=_metrics(0.98, silent_miss=1),
        hybrid_frame_recall=0.80,
    )

    result = assess_semantic_production_gate(candidate)

    assert not result.passed
    assert "SILENT_MISS" in result.reasons
    assert "NO_FRAME_RECALL_LIFT" in result.reasons
