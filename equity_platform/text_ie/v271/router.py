from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v270.router import route_document_blocks_v270


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    if route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}:
        return route
    tokens = tuple(token for token in backend.parse(route.text) if not token.is_space)
    numeric_count = sum(token.like_num for token in tokens)
    lexical_count = sum(token.is_alpha for token in tokens)
    short_result_bullet = (
        "•" in route.text
        and lexical_count <= 24
        and numeric_count <= 3
        and backend.phrase_mentions(route.text, ("increased", "decreased", "grew", "reached"))
    )
    narrative_cues = backend.phrase_mentions(
        route.text,
        ("business highlights", "reflected by", "while returning capital"),
    )
    narrative_continuation = (
        lexical_count >= 12
        and numeric_count <= 5
        and numeric_count / max(lexical_count, 1) < 0.15
        and len(narrative_cues) >= 2
    )
    if short_result_bullet or narrative_continuation:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V271_SPACY_PROSE_RECOVERY",),
        )
    return route


def route_document_blocks_v271(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v270(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v270(document))
