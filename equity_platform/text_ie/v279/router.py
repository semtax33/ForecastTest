from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v278.router import route_document_blocks_v278
from .semantics import semantic_quantities_v279


_TABLE_ROUTES = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _phrase_count(
    backend: SpacySemanticBackend,
    text: str,
    phrases: tuple[str, ...],
) -> int:
    return len(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    folded = text.casefold()
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    numeric = sum(token.like_num for token in tokens)
    typed = semantic_quantities_v279(text, backend)

    header_only_reconciliation = (
        route.route in _TABLE_ROUTES
        and "reconciliation of gaap to non-gaap information" in folded
        and "unaudited" in folded
        and not any(
            item.kind.value in {"MONEY", "PERCENT", "BASIS_POINTS"}
            for item in typed
        )
        and numeric <= 4
    )
    if header_only_reconciliation:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V279_HEADER_ONLY_RECONCILIATION_PROSE",),
        )

    line_item_reconciliation = (
        _phrase_count(backend, text, ("impact of the specified items by line item",))
        and _phrase_count(backend, text, ("as reported", "as adjusted")) >= 2
        and numeric >= 10
    )
    segment_reconciliation = (
        _phrase_count(backend, text, ("reconciliation to consolidated net revenue",))
        and _phrase_count(backend, text, ("reconciliation to consolidated operating income",))
        and numeric >= 8
    )
    if line_item_reconciliation or segment_reconciliation:
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V279_SPACY_RECONCILIATION_GRID",),
        )
    return route


def route_document_blocks_v279(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v278(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v278(document))
