from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v282.router import route_document_blocks_v282


_TABLE = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _has(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    numeric = sum(token.like_num for token in tokens)
    if route.route in _TABLE:
        press_release_lead = _has(
            backend,
            text,
            ("today announced", "today reported"),
        ) and _has(
            backend,
            text,
            ("reports second quarter results", "financial results", "organic sales"),
        )
        if press_release_lead:
            return replace(
                route,
                route=BlockRoute.PROSE,
                reasons=route.reasons + ("V283_SEMANTIC_PRESS_RELEASE_LEAD",),
            )
    else:
        income_share_grid = (
            _has(backend, text, ("weighted average number of common",))
            and (
                _has(
                    backend,
                    text,
                    ("diluted earnings per common share", "diluted earnings per share"),
                )
                or _has(
                    backend,
                    text,
                    ("common and common equivalent shares outstanding",),
                )
            )
            and numeric >= 6
        )
        projected_ffo_grid = (
            _has(backend, text, ("projected eps",))
            and _has(backend, text, ("projected ffo per share",))
            and _has(backend, text, ("low high",))
            and numeric >= 8
        )
        if income_share_grid or projected_ffo_grid:
            return replace(
                route,
                route=BlockRoute.FLATTENED_TABLE,
                reasons=route.reasons + ("V283_SEMANTIC_FINANCIAL_GRID",),
            )
    return route


def route_document_blocks_v283(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v282(document)
    return tuple(
        _repair(route, backend)
        for route in route_document_blocks_v282(document)
    )
