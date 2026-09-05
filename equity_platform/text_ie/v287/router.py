from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v286.router import route_document_blocks_v286


_TABLE = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _has(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    numeric = sum(token.like_num for token in backend.parse(text) if not token.is_space)
    if route.route in _TABLE:
        healthcare_highlights = (
            _has(backend, text, ("health plan membership",))
            and _has(backend, text, ("total revenue was",))
            and _has(backend, text, ("income from operations was",))
        )
        if healthcare_highlights:
            return replace(
                route,
                route=BlockRoute.PROSE,
                reasons=route.reasons + ("V287_SEMANTIC_HEALTHCARE_HIGHLIGHTS",),
            )
    else:
        expectations_grid = (
            _has(backend, text, ("financial expectations",))
            and _has(backend, text, ("previous",))
            and _has(backend, text, ("updated",))
            and _has(backend, text, ("total revenues", "net sales"))
            and numeric >= 8
        )
        cash_flow_grid = (
            _has(backend, text, ("six months ended",))
            and _has(backend, text, ("net cash used in operating activities", "net cash provided by operating activities"))
            and _has(backend, text, ("purchases of property and equipment",))
            and _has(backend, text, ("free cash flow",))
            and numeric >= 6
        )
        if expectations_grid or cash_flow_grid:
            reason = "V287_SEMANTIC_EXPECTATIONS_GRID" if expectations_grid else "V287_SEMANTIC_CASH_FLOW_GRID"
            return replace(
                route,
                route=BlockRoute.FLATTENED_TABLE,
                reasons=route.reasons + (reason,),
            )
    return route


def route_document_blocks_v287(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v286(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v286(document))
