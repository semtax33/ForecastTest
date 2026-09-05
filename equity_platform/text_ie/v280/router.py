from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v279.router import route_document_blocks_v279


_TABLE_ROUTES = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    if route.route not in _TABLE_ROUTES:
        return route
    text = route.text
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    has_sentence_predicate = any(
        token.lemma_.casefold() in {"be", "expect", "note", "report"}
        for token in tokens
    )
    maturity_prose = bool(
        backend.phrase_mentions(text, ("scheduled debt maturities",))
        and backend.phrase_mentions(text, ("respectively",))
        and has_sentence_predicate
    )
    debt_outlook_prose = bool(
        backend.phrase_mentions(text, ("total debt from continuing operations", "total debt"))
        and backend.phrase_mentions(text, ("down from", "up from", "outlook", "company now expects"))
        and has_sentence_predicate
    )
    if maturity_prose or debt_outlook_prose:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V280_SEMANTIC_NUMERIC_PROSE",),
        )
    return route


def route_document_blocks_v280(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v279(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v279(document))
