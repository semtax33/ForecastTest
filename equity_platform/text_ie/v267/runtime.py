from __future__ import annotations

from equity_platform.documents import CanonicalDocument

from ..model import TextExtractionResult
from ..runtime import _frame_claim, _frame_facts
from ..v26 import EvidenceRoute, RouteBindingEvidence, V26ExtractionResult
from ..v26.router import BlockRoute
from ..v266 import extract_text_kpis_v266
from .router import route_document_blocks_v267
from .semantics import (
    augment_candidates_v267,
    recover_v267_frames,
    resolve_frame_conflicts_v267,
    semantic_backend_v267,
)


def extract_text_kpis_v267(document: CanonicalDocument) -> V26ExtractionResult:
    prior = extract_text_kpis_v266(document)
    backend = semantic_backend_v267()
    candidates = augment_candidates_v267(document, prior.candidates, backend)
    routes = route_document_blocks_v267(document)
    allowed_spans = {
        (route.char_start, route.char_end)
        for route in routes
        if route.char_start is not None
        and route.char_end is not None
        and route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    }
    existing = tuple(
        frame
        for frame in prior.extraction.frames
        if any(
            frame.source_span.char_start >= start
            and frame.source_span.char_end <= end
            for start, end in allowed_spans
        )
    )
    recovered = recover_v267_frames(
        document, candidates, allowed_spans, backend=backend
    )
    frames = resolve_frame_conflicts_v267(existing, recovered, backend)
    extraction = TextExtractionResult(
        frames=frames,
        facts=tuple(fact for frame in frames for fact in _frame_facts(frame)),
        evidence_claims=tuple(
            claim
            for frame in frames
            if (claim := _frame_claim(frame)) is not None
        ),
        relations=prior.extraction.relations,
        reviews=prior.extraction.reviews,
        abstentions=prior.extraction.abstentions,
        backend_name="V267_SPACY_SEMANTIC_FIREWALL_PIPELINE",
    )
    bindings = tuple(
        RouteBindingEvidence(
            route=(
                EvidenceRoute.ADJUDICATED_DIRECT
                if frame.rule_id.startswith(("v264.", "v265.", "v266.", "v267."))
                else EvidenceRoute.TEXT_BINDING
            ),
            frame=frame,
            upstream_candidate_id=(
                str(frame.context_trace.get("candidate_id"))
                if frame.context_trace.get("candidate_id")
                else None
            ),
            verifier=frame.verified_by or "V267_UNKNOWN",
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
            rejection
            for rejection in prior.rejections
            if rejection.candidate_id not in bound_ids
        ),
    )
