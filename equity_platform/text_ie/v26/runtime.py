from __future__ import annotations

from equity_platform.documents import CanonicalDocument

from ..runtime import _frame_claim, _frame_facts
from ..model import TextExtractionResult

from ..v251 import extract_text_kpis_v251
from .model import (
    EvidenceRoute,
    RouteBindingEvidence,
    RouteRejection,
    V26ExtractionResult,
)
from .router import BlockRoute, RoutedBlock, route_document_blocks
from .semantics import recover_route_aware_semantics


def _route_for(frame: object) -> EvidenceRoute:
    if frame.extraction_method.value == "INLINE_XBRL":
        return EvidenceRoute.XBRL_DIRECT
    if frame.rule_id.startswith("v251."):
        return EvidenceRoute.ADJUDICATED_DIRECT
    return EvidenceRoute.TEXT_BINDING


def _block_route(candidate: object, routes: tuple[RoutedBlock, ...]) -> BlockRoute:
    return next(
        (
            item.route
            for item in routes
            if item.char_start is not None
            and item.char_end is not None
            and candidate.block.char_start >= item.char_start
            and candidate.block.char_end <= item.char_end
        ),
        BlockRoute.PROSE,
    )


def _inside_non_text_route(frame: object, routes: tuple[RoutedBlock, ...]) -> bool:
    return any(
        item.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        and item.char_start is not None
        and item.char_end is not None
        and frame.source_span.char_start >= item.char_start
        and frame.source_span.char_end <= item.char_end
        for item in routes
    )


def extract_text_kpis_v26(document: CanonicalDocument) -> V26ExtractionResult:
    """Add complete route provenance without changing the frozen candidates."""

    routed_blocks = route_document_blocks(document)
    prior = extract_text_kpis_v251(document)
    prior_frames = tuple(
        frame for frame in prior.extraction.frames
        if not _inside_non_text_route(frame, routed_blocks)
    )
    changes, comparisons, recovered = recover_route_aware_semantics(
        document, prior.candidates, routed_blocks
    )
    frames_by_signature = {
        (frame.concept, frame.frame, frame.value, frame.change): frame
        for frame in prior_frames
    }
    for frame in recovered:
        frames_by_signature.setdefault(
            (frame.concept, frame.frame, frame.value, frame.change), frame
        )
    frames = tuple(frames_by_signature.values())
    extraction = TextExtractionResult(
        frames=frames,
        facts=tuple(fact for frame in frames for fact in _frame_facts(frame)),
        evidence_claims=tuple(
            claim for frame in frames if (claim := _frame_claim(frame)) is not None
        ),
        relations=prior.extraction.relations,
        reviews=prior.extraction.reviews,
        abstentions=prior.extraction.abstentions,
        backend_name="V26_ROUTE_AWARE_SEMANTIC_BINDING",
    )
    bindings = tuple(
        RouteBindingEvidence(
            route=_route_for(frame),
            frame=frame,
            upstream_candidate_id=str(frame.context_trace.get("candidate_id"))
            if frame.context_trace.get("candidate_id")
            else None,
            verifier=frame.verified_by or "UNKNOWN",
        )
        for frame in frames
    )
    bound_ids = {
        item.upstream_candidate_id for item in bindings if item.upstream_candidate_id
    }
    rejections = []
    for candidate in prior.candidates:
        if candidate.candidate_id in bound_ids:
            continue
        route = _block_route(candidate, routed_blocks)
        reasons = []
        if route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}:
            reasons.append(f"LAYOUT_ROUTED_{route.value}")
        for item in (*prior.extraction.reviews, *prior.extraction.abstentions):
            if (
                candidate.block.char_start >= item.source_span.char_start
                and candidate.block.char_end <= item.source_span.char_end
            ):
                reasons.append(item.reason)
        if not reasons:
            reasons.append("NO_SAFE_FINAL_BINDING")
        ordered = tuple(dict.fromkeys(reasons))
        rejections.append(RouteRejection(candidate.candidate_id, ordered[0], ordered[1:]))
    return V26ExtractionResult(
        extraction=extraction,
        candidates=prior.candidates,
        bindings=bindings,
        table_routes=prior.table_routes,
        routed_blocks=routed_blocks,
        changes=changes,
        comparisons=comparisons,
        rejections=tuple(rejections),
    )
