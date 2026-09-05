from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..model import KPIFrame
from ..staged_evaluation import (
    base_concept,
    explicit_quantity_values,
    score_stage,
    unmatched_expected_frames,
)
from ..training.staged_gold import (
    ConceptGoldNode,
    QuantityGoldNode,
    StagedGoldExample,
)
from .model import ClauseSemanticTrace, V291ExtractionResult


def _frame_dict(frame: KPIFrame) -> dict[str, object]:
    return {
        "concept": frame.concept,
        "frame": frame.frame.value,
        "value": frame.value,
        "change": frame.change,
        "lower_value": frame.lower_value,
        "upper_value": frame.upper_value,
        "polarity": "POSITIVE" if frame.polarity.positive else "NEGATIVE",
        "tier": frame.tier.value,
        "rule_id": frame.rule_id,
    }


def _inside(trace: ClauseSemanticTrace, start: int, end: int) -> bool:
    return trace.block_char_start >= start and trace.block_char_end <= end


def _unique_candidate_quantities(candidates: Sequence[object]) -> tuple[float, ...]:
    observed: dict[tuple[int, int, str], float] = {}
    for candidate in candidates:
        for quantity in candidate.quantities:
            signature = (
                candidate.block.char_start + quantity.char_start,
                candidate.block.char_start + quantity.char_end,
                quantity.kind.value,
            )
            observed[signature] = float(quantity.value)
    return tuple(observed.values())


def _unique_candidate_concepts(candidates: Sequence[object]) -> tuple[str, ...]:
    observed: dict[tuple[int, int, str], str] = {}
    for candidate in candidates:
        metric = candidate.metric
        signature = (
            candidate.block.char_start + metric.char_start,
            candidate.block.char_start + metric.char_end,
            metric.concept,
        )
        observed[signature] = metric.concept
    return tuple(observed.values())


def _gold_quantity_signature(node: QuantityGoldNode) -> tuple[object, ...]:
    return (
        node.kind,
        round(float(node.value), 8),
        node.char_start,
        node.char_end,
    )


def _gold_concept_signature(node: ConceptGoldNode) -> tuple[object, ...]:
    return (
        base_concept(node.concept),
        node.char_start,
        node.char_end,
    )


def _quantity_signature(quantity, offset: int) -> tuple[object, ...]:
    return (
        quantity.kind.value,
        round(float(quantity.value), 8),
        offset + quantity.char_start,
        offset + quantity.char_end,
    )


def _concept_signature(concept: str, start: int, end: int) -> tuple[object, ...]:
    return (base_concept(concept), start, end)


def native_staged_row(
    result: V291ExtractionResult,
    *,
    block_char_start: int,
    block_char_end: int,
    expected_frames: Sequence[Mapping[str, object]],
    candidate_hits: int,
    gold_route: str,
    predicted_table: bool,
) -> dict[str, object]:
    traces = tuple(
        trace
        for trace in result.telemetry.clauses
        if _inside(trace, block_char_start, block_char_end)
    )
    frames = tuple(
        frame
        for frame in result.extraction.frames
        if frame.source_span.char_start >= block_char_start
        and frame.source_span.char_end <= block_char_end
    )
    traced_candidate_ids = {
        candidate_id
        for trace in traces
        for candidate_id in trace.candidate_ids
    }
    block_candidates = tuple(
        candidate
        for candidate in result.candidates
        if candidate.block.char_start >= block_char_start
        and candidate.block.char_end <= block_char_end
    )
    block_candidate_ids = {candidate.candidate_id for candidate in block_candidates}
    inherited_rejections = {
        (rejection.candidate_id, rejection.primary_root_cause)
        for rejection in result.rejections
        if rejection.candidate_id in block_candidate_ids
    }
    inherited_rejection_ids = {
        candidate_id for candidate_id, _ in inherited_rejections
    }
    untraced_candidate_ids = (
        block_candidate_ids - traced_candidate_ids - inherited_rejection_ids
    )
    trace_rejections = {
        (
            trace.clause_char_start,
            trace.clause_char_end,
            trace.primary_root_cause,
        )
        for trace in traces
        if trace.primary_root_cause not in {"EMITTED", "NO_QUANTITY_IN_CLAUSE"}
    }
    reviews = tuple(
        review
        for review in result.extraction.reviews
        if review.source_span.char_start >= block_char_start
        and review.source_span.char_end <= block_char_end
    )
    candidate_by_id = {
        candidate.candidate_id: candidate
        for candidate in result.candidates
        if candidate.candidate_id in block_candidate_ids
    }
    observable_signatures = {
        (edge.concept, float(edge.quantity.value))
        for trace in traces
        for edge in trace.unresolved_bindings
    }
    rejected_candidate_ids = (
        untraced_candidate_ids
        | inherited_rejection_ids
        | {
            candidate_id
            for trace in traces
            if trace.primary_root_cause
            not in {"EMITTED", "PARTIAL_UNRESOLVED_BINDING"}
            for candidate_id in trace.candidate_ids
        }
    )
    observable_signatures.update(
        (
            base_concept(candidate.metric.concept),
            float(quantity.value),
        )
        for candidate_id in rejected_candidate_ids
        if (candidate := candidate_by_id.get(candidate_id)) is not None
        for quantity in candidate.quantities
    )
    actual_frame_dicts = tuple(_frame_dict(frame) for frame in frames)
    unmatched = unmatched_expected_frames(expected_frames, actual_frame_dicts)
    observable_abstained_frames = sum(
        any(
            (base_concept(str(frame["concept"])), value)
            in observable_signatures
            for value in explicit_quantity_values(frame)
        )
        for frame in unmatched
    )
    return {
        "expected_frames": tuple(dict(frame) for frame in expected_frames),
        "actual_frames": actual_frame_dicts,
        "candidate_hits": candidate_hits,
        "detected_quantities": _unique_candidate_quantities(block_candidates),
        "detected_concepts": _unique_candidate_concepts(block_candidates),
        "detected_bindings": tuple(
            (edge.concept, float(edge.quantity.value))
            for trace in traces
            for edge in trace.bindings
        ),
        "detected_roles": tuple(
            (edge.concept, edge.role, float(edge.quantity.value))
            for trace in traces
            for edge in trace.roles
        ),
        "rejection_count": (
            len(inherited_rejections)
            + len(trace_rejections)
            + int(bool(untraced_candidate_ids))
        ),
        "review_count": len(reviews),
        "observable_abstained_frames": observable_abstained_frames,
        "unresolved_binding_count": sum(
            len(trace.unresolved_bindings) for trace in traces
        ),
        "untraced_candidate_count": len(untraced_candidate_ids),
        "gold_route": gold_route,
        "predicted_table": predicted_table,
        "trace_root_causes": (
            tuple(trace.primary_root_cause for trace in traces)
            + (
                ("NO_RECOVERY_TRACE_FOR_CANDIDATE",)
                if untraced_candidate_ids
                else ()
            )
        ),
    }


def native_stage_gold_row(
    result: V291ExtractionResult,
    example: StagedGoldExample,
    *,
    block_char_start: int,
    block_char_end: int,
    predicted_table: bool,
) -> dict[str, object]:
    concepts = {node.node_id: node for node in example.concepts}
    quantities = {node.node_id: node for node in example.quantities}
    expected_concepts = tuple(_gold_concept_signature(node) for node in example.concepts)
    expected_quantities = tuple(_gold_quantity_signature(node) for node in example.quantities)

    def gold_edge_signature(edge) -> tuple[object, ...]:
        return (
            *_gold_concept_signature(concepts[edge.concept_id]),
            *_gold_quantity_signature(quantities[edge.quantity_id]),
        )

    expected_candidate_edges = tuple(
        gold_edge_signature(edge) for edge in example.candidate_edges
    )
    expected_bindings = tuple(
        gold_edge_signature(edge) for edge in example.binding_edges
    )
    expected_roles = tuple(
        (
            *_gold_concept_signature(concepts[edge.concept_id]),
            edge.role,
            *_gold_quantity_signature(quantities[edge.quantity_id]),
        )
        for edge in example.role_edges
    )
    block_candidates = tuple(
        candidate
        for candidate in result.candidates
        if candidate.block.char_start >= block_char_start
        and candidate.block.char_end <= block_char_end
    )
    detected_quantities = {
        _quantity_signature(
            quantity,
            candidate.block.char_start - block_char_start,
        )
        for candidate in block_candidates
        for quantity in candidate.quantities
    }
    detected_concepts = {
        _concept_signature(
            candidate.metric.concept,
            candidate.block.char_start + candidate.metric.char_start - block_char_start,
            candidate.block.char_start + candidate.metric.char_end - block_char_start,
        )
        for candidate in block_candidates
    }
    detected_candidate_edges = tuple(
        (
            *_concept_signature(
                candidate.metric.concept,
                candidate.block.char_start + candidate.metric.char_start - block_char_start,
                candidate.block.char_start + candidate.metric.char_end - block_char_start,
            ),
            *_quantity_signature(
                quantity,
                candidate.block.char_start - block_char_start,
            ),
        )
        for candidate in block_candidates
        for quantity in candidate.quantities
    )
    traces = tuple(
        trace
        for trace in result.telemetry.clauses
        if _inside(trace, block_char_start, block_char_end)
    )
    detected_bindings = tuple(
        (
            *_concept_signature(
                edge.concept,
                trace.clause_char_start + edge.concept_char_start - block_char_start,
                trace.clause_char_start + edge.concept_char_end - block_char_start,
            ),
            *_quantity_signature(
                edge.quantity,
                trace.clause_char_start - block_char_start,
            ),
        )
        for trace in traces
        for edge in trace.bindings
    )
    detected_roles = tuple(
        (
            *_concept_signature(
                edge.concept,
                trace.clause_char_start + edge.concept_char_start - block_char_start,
                trace.clause_char_start + edge.concept_char_end - block_char_start,
            ),
            edge.role,
            *_quantity_signature(
                edge.quantity,
                trace.clause_char_start - block_char_start,
            ),
        )
        for trace in traces
        for edge in trace.roles
    )
    candidate_hits = score_stage(
        expected_candidate_edges,
        detected_candidate_edges,
    ).true_positive
    row = native_staged_row(
        result,
        block_char_start=block_char_start,
        block_char_end=block_char_end,
        expected_frames=example.expected_frames,
        candidate_hits=candidate_hits,
        gold_route=example.gold_route,
        predicted_table=predicted_table,
    )
    row.update({
        "candidate_expected": len(expected_candidate_edges),
        "expected_quantities": expected_quantities,
        "detected_quantities": tuple(sorted(detected_quantities)),
        "expected_concepts": expected_concepts,
        "detected_concepts": tuple(sorted(detected_concepts)),
        "expected_bindings": expected_bindings,
        "detected_bindings": detected_bindings,
        "expected_roles": expected_roles,
        "detected_roles": detected_roles,
    })
    return row
