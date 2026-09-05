from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v284.router import route_document_blocks_v284


_TABLE = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _has(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    if route.route in _TABLE:
        segment_highlight = (
            _has(backend, route.text, ("adjusted segment ebitda",))
            and _has(backend, route.text, ("margin expanded",))
            and _has(backend, route.text, ("driven by",))
        )
        result_highlight = (
            _has(backend, route.text, ("highlights", "revenue of"))
            and _has(backend, route.text, ("gross margin of",))
            and _has(backend, route.text, ("operating margin of",))
        )
        if segment_highlight or result_highlight:
            reason = "V285_SEMANTIC_SEGMENT_HIGHLIGHT" if segment_highlight else "V285_SEMANTIC_RESULT_HIGHLIGHT"
            return replace(route, route=BlockRoute.PROSE, reasons=route.reasons + (reason,))
    return route


def route_document_blocks_v285(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v284(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v284(document))
