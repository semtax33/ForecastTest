from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v283.router import route_document_blocks_v283


_TABLE = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _has(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    numeric = sum(token.like_num for token in tokens)
    if route.route in _TABLE:
        results_bullet = (
            _has(backend, text, ("total revenue was", "adjusted ebitda"))
            and _has(backend, text, ("capital expenditures", "compared to"))
        )
        press_release_lead = (
            _has(backend, text, ("financial news release", "reports second quarter results"))
            and _has(backend, text, ("announced financial results", "revenue was"))
        )
        if results_bullet or press_release_lead:
            reason = "V284_SEMANTIC_RESULTS_BULLET" if results_bullet else "V284_SEMANTIC_PRESS_RELEASE_LEAD"
            return replace(route, route=BlockRoute.PROSE, reasons=route.reasons + (reason,))
    else:
        statement_grid = (
            _has(backend, text, ("condensed consolidated statements of income",))
            and _has(backend, text, ("three months ended", "six months ended"))
            and numeric >= 12
        )
        if statement_grid:
            return replace(
                route,
                route=BlockRoute.FLATTENED_TABLE,
                reasons=route.reasons + ("V284_SEMANTIC_FINANCIAL_STATEMENT_GRID",),
            )
    return route


def route_document_blocks_v284(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v283(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v283(document))
