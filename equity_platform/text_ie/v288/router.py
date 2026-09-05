from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v287.router import route_document_blocks_v287


_TABLE = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _has(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    numeric = sum(token.like_num for token in backend.parse(text) if not token.is_space)
    if route.route in _TABLE:
        release_headline = (
            _has(backend, text, ("reports financial results",))
            and _has(backend, text, ("net revenues of",))
            and _has(backend, text, ("company to hold a conference call",))
        )
        if release_headline:
            return replace(
                route,
                route=BlockRoute.PROSE,
                reasons=route.reasons + ("V288_SEMANTIC_RELEASE_HEADLINE",),
            )
    else:
        price_grid = (
            _has(backend, text, ("coal sales realization",))
            and _has(backend, text, ("per ton",))
            and _has(backend, text, ("three months ended",))
            and numeric >= 4
        )
        segment_grid = (
            _has(backend, text, ("ebitda projects",))
            and _has(backend, text, ("energy assets",))
            and _has(backend, text, ("o&m",))
            and _has(backend, text, ("total",))
            and numeric >= 12
        )
        header_fragment = (
            _has(backend, text, ("second quarter financial results",))
            and _has(backend, text, ("in thousands",))
            and _has(backend, text, ("revenue",))
            and _has(backend, text, ("net income", "net income (loss)"))
            and numeric >= 2
        )
        if price_grid or segment_grid or header_fragment:
            reason = (
                "V288_SEMANTIC_PRICE_GRID"
                if price_grid
                else "V288_SEMANTIC_SEGMENT_GRID"
                if segment_grid
                else "V288_SEMANTIC_HEADER_FRAGMENT"
            )
            return replace(
                route,
                route=BlockRoute.FLATTENED_TABLE,
                reasons=route.reasons + (reason,),
            )
    return route


def route_document_blocks_v288(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v287(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v287(document))
