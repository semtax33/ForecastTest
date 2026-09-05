from __future__ import annotations

from equity_platform.documents import CanonicalDocument

from ..model import TextExtractionResult
from ..runtime import _frame_claim, _frame_facts
from ..v26 import EvidenceRoute, RouteBindingEvidence, V26ExtractionResult
from ..v26.router import BlockRoute
from ..v287 import extract_text_kpis_v287
from .router import route_document_blocks_v288
from .semantics import augment_candidates_v288, recover_v288_frames, resolve_frame_conflicts_v288


def extract_text_kpis_v288(document: CanonicalDocument) -> V26ExtractionResult:
    prior = extract_text_kpis_v287(document)
    candidates = augment_candidates_v288(document, prior.candidates)
    routes = route_document_blocks_v288(document)
    allowed_spans = {
        (route.char_start, route.char_end)
        for route in routes
        if route.char_start is not None
        and route.char_end is not None
        and route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    }
    existing = tuple(
        frame for frame in prior.extraction.frames
        if any(
            frame.source_span.char_start >= start and frame.source_span.char_end <= end
            for start, end in allowed_spans
        )
    )
    recovered = recover_v288_frames(document, candidates, allowed_spans)
    frames = resolve_frame_conflicts_v288(existing, recovered)
    extraction = TextExtractionResult(
        frames=frames,
        facts=tuple(fact for frame in frames for fact in _frame_facts(frame)),
        evidence_claims=tuple(
            claim for frame in frames if (claim := _frame_claim(frame)) is not None
        ),
        relations=prior.extraction.relations,
        reviews=prior.extraction.reviews,
        abstentions=prior.extraction.abstentions,
        backend_name="V288_SPACY_LOCAL_ROLE_BINDER_PIPELINE",
    )
    bindings = tuple(
        RouteBindingEvidence(
            route=EvidenceRoute.ADJUDICATED_DIRECT,
            frame=frame,
            upstream_candidate_id=(
                str(frame.context_trace.get("candidate_id"))
                if frame.context_trace.get("candidate_id")
                else None
            ),
            verifier=frame.verified_by or "V288_UNKNOWN",
        )
        for frame in frames
    )
    bound_ids = {binding.upstream_candidate_id for binding in bindings}
    return V26ExtractionResult(
        extraction=extraction,
        candidates=candidates,
        bindings=bindings,
        table_routes=routes,
        routed_blocks=routes,
        changes=prior.changes,
        comparisons=prior.comparisons,
        rejections=tuple(
            rejection for rejection in prior.rejections
            if rejection.candidate_id not in bound_ids
        ),
    )
