from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v281.router import route_document_blocks_v281


_TABLE = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _has(backend: SpacySemanticBackend, text: str, phrase: str) -> bool:
    return bool(backend.phrase_mentions(text, (phrase,)))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    numeric = sum(token.like_num for token in tokens)
    highlights = (
        _has(backend, text, "highlights")
        and _has(backend, text, "adjusted ebitda")
        and _has(backend, text, "capital expenditures")
        and _has(backend, text, "volumes")
    )
    if route.route in _TABLE and highlights:
        return replace(route, route=BlockRoute.PROSE, reasons=route.reasons + ("V282_SEMANTIC_HIGHLIGHTS",))
    if route.route not in _TABLE:
        development_grid = (
            _has(backend, text, "development pipeline summary")
            and _has(backend, text, "lots for future delivery")
            and numeric >= 8
        )
        net_debt_grid = (
            _has(backend, text, "reconciliation of net debt")
            and _has(backend, text, "cash and cash equivalents")
            and _has(backend, text, "long-term debt")
            and _has(backend, text, "net debt")
            and numeric >= 8
        )
        if development_grid or net_debt_grid:
            return replace(route, route=BlockRoute.FLATTENED_TABLE, reasons=route.reasons + ("V282_SEMANTIC_UPPER_GRID",))
    return route


def route_document_blocks_v282(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v281(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v281(document))
