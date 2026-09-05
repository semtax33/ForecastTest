from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v289.router import route_document_blocks_v289


_TABLE = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _has(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    doc = backend.parse(text)
    numeric = sum(token.like_num for token in doc if not token.is_space)
    folded = text.casefold()
    statement_markers = (
        "consolidated statement", "condensed consolidated", "financial tables", "segment data",
        "balance sheets", "reconciliation of", "statements of cash flows",
    )
    if route.route in _TABLE:
        narrative = (
            len(text) < 700
            and numeric <= 14
            and _has(backend, text, ("was", "were", "increased", "decreased"))
            and not _has(backend, text, statement_markers)
            and "(in thousands" not in folded
        )
        if narrative:
            return replace(route, route=BlockRoute.PROSE, reasons=route.reasons + ("V290_FINITE_VERB_NARRATIVE",))
    else:
        dense_statement = (
            numeric >= 12
            and _has(backend, text, statement_markers)
            and _has(backend, text, ("three months ended", "six months ended", "unaudited"))
        )
        header_fragment = (
            _has(backend, text, ("financial measures for the periods presented", "financial measures for periods presented"))
            and _has(backend, text, ("net sales",))
            and _has(backend, text, ("percentage growth", "% change"))
            and _has(backend, text, ("organic", "constant currency", "acquisition"))
        )
        if dense_statement or header_fragment:
            reason = "V290_DENSE_STATEMENT" if dense_statement else "V290_HEADER_FRAGMENT"
            return replace(route, route=BlockRoute.FLATTENED_TABLE, reasons=route.reasons + (reason,))
    return route


def route_document_blocks_v290(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v289(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v289(document))
