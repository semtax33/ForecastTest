from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v272.router import route_document_blocks_v272
from .semantics import semantic_quantities_v273


_TABLE_ROUTES = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _count(
    backend: SpacySemanticBackend,
    text: str,
    phrases: tuple[str, ...],
) -> int:
    return len(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    quantities = semantic_quantities_v273(text, backend)
    money_count = sum(item.kind.value == "MONEY" for item in quantities)
    percent_count = sum(item.kind.value == "PERCENT" for item in quantities)
    bps_count = sum(item.kind.value == "BASIS_POINTS" for item in quantities)

    repeated_revenue_prose = (
        route.route in _TABLE_ROUTES
        and _count(backend, text, ("revenue", "revenues")) >= 3
        and _count(backend, text, ("constant currency",)) >= 2
        and _count(backend, text, ("up",)) >= 3
        and money_count >= 3
    )
    repeated_margin_prose = (
        route.route in _TABLE_ROUTES
        and _count(backend, text, ("operating margin",)) >= 2
        and _count(backend, text, ("contracted", "expanded")) >= 2
        and bps_count >= 2
        and percent_count >= 2
    )
    orphan_header = (
        route.route in _TABLE_ROUTES
        and "$" not in text
        and "%" not in text
        and money_count == 0
        and percent_count == 0
        and _count(backend, text, ("revenues",)) >= 1
        and _count(backend, text, ("earnings from operations",)) >= 1
    )
    if repeated_revenue_prose or repeated_margin_prose or orphan_header:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V273_SPACY_SEMANTIC_PROSE",),
        )

    supplemental_grid = (
        _count(backend, text, ("revenues by business",)) >= 1
        and _count(backend, text, ("supplemental financial information",)) >= 1
        and _count(backend, text, ("in millions",)) >= 1
        and sum(token.like_num for token in backend.parse(text)) >= 3
    )
    revision_grid = (
        _count(backend, text, ("as of",)) >= 2
        and _count(backend, text, ("unchanged",)) >= 2
        and _count(backend, text, ("net sales",)) >= 1
        and _count(backend, text, ("operating income",)) >= 1
        and percent_count >= 4
    )
    if supplemental_grid or revision_grid:
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V273_SPACY_SEMANTIC_GRID",),
        )
    return route


def route_document_blocks_v273(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v272(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v272(document))
