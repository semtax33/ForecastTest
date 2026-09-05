from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from equity_platform.documents import CanonicalDocument

from ..document import document_text_blocks
from ..model import SemanticFrame
from ..runtime import _frame_claim, _frame_facts
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v26 import EvidenceRoute, RouteBindingEvidence
from ..v26.router import BlockRoute
from ..v290.semantics import _new_frame
from ..v291 import (
    ClauseSemanticTrace,
    QuantityBindingEdge,
    QuantityRoleEdge,
    V291ExtractionResult,
    extract_text_kpis_v291,
)
from .semantics import (
    V292_RULES,
    activity_predicate_arguments,
    impact_delta_arguments,
    is_share_transaction_event_scope,
)


_RULE_BY_ID = {rule.rule_id: rule for rule in V292_RULES}


def _replace_extraction(result, frames):
    return replace(
        result.extraction,
        frames=frames,
        facts=tuple(fact for frame in frames for fact in _frame_facts(frame)),
        evidence_claims=tuple(
            claim for frame in frames if (claim := _frame_claim(frame)) is not None
        ),
        backend_name="V292_SPACY_TYPED_SEMANTIC_CONTEXT_PIPELINE",
    )


def _recover_activity_arguments(
    document: CanonicalDocument,
    result: V291ExtractionResult,
) -> V291ExtractionResult:
    allowed_spans = {
        (route.char_start, route.char_end)
        for route in result.table_routes
        if route.char_start is not None
        and route.char_end is not None
        and route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    }
    candidates = list(result.candidates)
    frames = list(result.extraction.frames)
    bindings = list(result.bindings)
    traces = list(result.telemetry.clauses)
    rule = _RULE_BY_ID["v292.activity_predicate_argument"]

    for block in document_text_blocks(document):
        if (block.char_start, block.char_end) not in allowed_spans:
            continue
        arguments = activity_predicate_arguments(block.text)
        if not arguments:
            continue
        block_candidates = []
        block_frames = []
        binding_edges = []
        role_edges = []
        for argument in arguments:
            candidate_id = sha256(
                (
                    f"{document.source.sha256}:{block.char_start}:ACTIVITY_VOLUME:"
                    f"{argument.concept.char_start}:{argument.quantity.char_start}:v292"
                ).encode()
            ).hexdigest()[:20]
            candidate = RecallCandidate(
                candidate_id=candidate_id,
                block=block,
                metric=MetricAnchor(
                    "ACTIVITY_VOLUME",
                    argument.concept.alias,
                    argument.concept.char_start,
                    argument.concept.char_end,
                ),
                quantities=(argument.quantity,),
                origins=(CandidateOrigin.DEPENDENCY,),
                rule_ids=(rule.rule_id,),
            )
            candidates.append(candidate)
            block_candidates.append(candidate)
            frame = _new_frame(
                document,
                block,
                tuple(candidates),
                concept="ACTIVITY_VOLUME",
                semantic=SemanticFrame.ABSOLUTE_VALUE,
                value=argument.quantity,
            )
            if frame is None:
                continue
            context_trace = dict(frame.context_trace)
            context_trace.update({
                "candidate_id": candidate_id,
                "binding_eligibility": "V292_SPACY_PREDICATE_ARGUMENT",
                "rule_program_sha256": rule.source_sha256,
            })
            frame = replace(
                frame,
                rule_id=rule.rule_id,
                rule_version=rule.version,
                verified_by="V292_SPACY_PREDICATE_ARGUMENT_VERIFIER",
                context_trace=context_trace,
            )
            frames.append(frame)
            block_frames.append(frame)
            bindings.append(RouteBindingEvidence(
                route=EvidenceRoute.ADJUDICATED_DIRECT,
                frame=frame,
                upstream_candidate_id=candidate_id,
                verifier="V292_SPACY_PREDICATE_ARGUMENT_VERIFIER",
            ))
            binding_edges.append(QuantityBindingEdge(
                concept="ACTIVITY_VOLUME",
                quantity=argument.quantity,
                concept_char_start=argument.concept.char_start,
                concept_char_end=argument.concept.char_end,
            ))
            role_edges.append(QuantityRoleEdge(
                concept="ACTIVITY_VOLUME",
                role="VALUE_CURRENT",
                quantity=argument.quantity,
                concept_char_start=argument.concept.char_start,
                concept_char_end=argument.concept.char_end,
            ))
        if block_frames:
            traces.append(ClauseSemanticTrace(
                block_char_start=block.char_start,
                block_char_end=block.char_end,
                clause_char_start=block.char_start,
                clause_char_end=block.char_end,
                candidate_ids=tuple(item.candidate_id for item in block_candidates),
                concepts=tuple(item.concept for item in arguments),
                quantities=tuple(item.quantity for item in arguments),
                bindings=tuple(binding_edges),
                roles=tuple(role_edges),
                unresolved_bindings=(),
                reduced_frames=tuple(block_frames),
                adjudicated=True,
                primary_root_cause="EMITTED",
            ))

    if not frames or frames == list(result.extraction.frames):
        return result
    base = replace(
        result.base,
        extraction=_replace_extraction(result, tuple(frames)),
        candidates=tuple(candidates),
        bindings=tuple(bindings),
    )
    return V291ExtractionResult(
        base=base,
        telemetry=replace(result.telemetry, clauses=tuple(traces)),
    )


def _candidate_id_for(result, block, concept: str) -> str | None:
    matches = tuple(
        candidate
        for candidate in result.candidates
        if candidate.block.char_start == block.char_start
        and candidate.block.char_end == block.char_end
        and candidate.metric.concept == concept
    )
    return min(matches, key=lambda item: item.metric.char_start).candidate_id if matches else None


def _recover_impact_deltas(
    document: CanonicalDocument,
    result: V291ExtractionResult,
) -> V291ExtractionResult:
    blocks = {
        (block.char_start, block.char_end): block
        for block in document_text_blocks(document)
    }
    frames = list(result.extraction.frames)
    route_bindings = list(result.bindings)
    traces = []
    rule = _RULE_BY_ID["v292.impact_on_metric_delta"]
    changed = False
    for trace in result.telemetry.clauses:
        block = blocks.get((trace.block_char_start, trace.block_char_end))
        clause_start = trace.clause_char_start - trace.block_char_start
        clause_end = trace.clause_char_end - trace.block_char_start
        text = block.text[clause_start:clause_end] if block is not None else ""
        arguments = impact_delta_arguments(text, trace.concepts, trace.quantities)
        if not arguments or block is None:
            traces.append(trace)
            continue
        recovered = []
        roles = list(trace.roles)
        resolved_bindings = []
        candidate_id = _candidate_id_for(result, block, "ACTIVITY_VOLUME")
        for argument in arguments:
            frame = _new_frame(
                document,
                block,
                result.candidates,
                concept="ACTIVITY_VOLUME",
                semantic=SemanticFrame.CHANGE_BY,
                value=argument.quantity,
            )
            if frame is None:
                continue
            context_trace = dict(frame.context_trace)
            context_trace.update({
                "candidate_id": candidate_id,
                "binding_eligibility": "V292_SPACY_IMPACT_RELATION",
                "rule_program_sha256": rule.source_sha256,
            })
            frame = replace(
                frame,
                rule_id=rule.rule_id,
                rule_version=rule.version,
                verified_by="V292_SPACY_IMPACT_RELATION_VERIFIER",
                context_trace=context_trace,
            )
            frames.append(frame)
            recovered.append(frame)
            route_bindings.append(RouteBindingEvidence(
                route=EvidenceRoute.ADJUDICATED_DIRECT,
                frame=frame,
                upstream_candidate_id=candidate_id,
                verifier="V292_SPACY_IMPACT_RELATION_VERIFIER",
            ))
            role = QuantityRoleEdge(
                concept="ACTIVITY_VOLUME",
                role="DELTA",
                quantity=argument.quantity,
                concept_char_start=argument.concept.char_start,
                concept_char_end=argument.concept.char_end,
            )
            roles.append(role)
            resolved_bindings.append((role.concept, role.quantity, role.concept_char_start, role.concept_char_end))
        if not recovered:
            traces.append(trace)
            continue
        changed = True
        unresolved = tuple(
            edge
            for edge in trace.unresolved_bindings
            if (edge.concept, edge.quantity, edge.concept_char_start, edge.concept_char_end)
            not in resolved_bindings
        )
        traces.append(replace(
            trace,
            roles=tuple(roles),
            unresolved_bindings=unresolved,
            reduced_frames=trace.reduced_frames + tuple(recovered),
            adjudicated=True,
            primary_root_cause="EMITTED" if not unresolved else "PARTIAL_UNRESOLVED_BINDING",
        ))
    if not changed:
        return result
    base = replace(
        result.base,
        extraction=_replace_extraction(result, tuple(frames)),
        bindings=tuple(route_bindings),
    )
    return V291ExtractionResult(
        base=base,
        telemetry=replace(result.telemetry, clauses=tuple(traces)),
    )


def _suppress_non_state_share_events(
    document: CanonicalDocument,
    result: V291ExtractionResult,
) -> V291ExtractionResult:
    blocks = {
        (block.char_start, block.char_end): block
        for block in document_text_blocks(document)
    }
    suppressed_frames = []
    traces = []
    for trace in result.telemetry.clauses:
        block = blocks.get((trace.block_char_start, trace.block_char_end))
        clause_start = trace.clause_char_start - trace.block_char_start
        clause_end = trace.clause_char_end - trace.block_char_start
        clause_text = block.text[clause_start:clause_end] if block is not None else ""
        suppressed = bool(
            clause_text
            and is_share_transaction_event_scope(
                clause_text,
                trace.concepts,
                trace.quantities,
            )
        )
        if not suppressed:
            traces.append(trace)
            continue

        removed = tuple(frame for frame in trace.reduced_frames if frame.concept == "SHARES")
        suppressed_frames.extend(removed)
        kept_frames = tuple(frame for frame in trace.reduced_frames if frame.concept != "SHARES")
        kept_roles = tuple(edge for edge in trace.roles if edge.concept != "SHARES")
        share_bindings = tuple(edge for edge in trace.bindings if edge.concept == "SHARES")
        traces.append(replace(
            trace,
            roles=kept_roles,
            unresolved_bindings=trace.unresolved_bindings + share_bindings,
            reduced_frames=kept_frames,
            adjudicated=True,
            primary_root_cause=(
                "EMITTED"
                if kept_frames
                else "SUPPRESSED_EVENT_SCOPE"
            ),
        ))

    if not suppressed_frames:
        return result
    kept = tuple(frame for frame in result.extraction.frames if frame not in suppressed_frames)
    extraction = _replace_extraction(result, kept)
    base = replace(
        result.base,
        extraction=extraction,
        bindings=tuple(
            binding for binding in result.bindings if binding.frame not in suppressed_frames
        ),
    )
    return V291ExtractionResult(
        base=base,
        telemetry=replace(result.telemetry, clauses=tuple(traces)),
    )


def extract_text_kpis_v292(document: CanonicalDocument) -> V291ExtractionResult:
    recovered = _recover_activity_arguments(document, extract_text_kpis_v291(document))
    recovered = _recover_impact_deltas(document, recovered)
    return _suppress_non_state_share_events(document, recovered)


__all__ = ["extract_text_kpis_v292"]
