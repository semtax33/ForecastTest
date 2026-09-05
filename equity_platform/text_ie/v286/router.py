from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v285.router import route_document_blocks_v285


_TABLE = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _has(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    numeric = sum(token.like_num for token in backend.parse(text) if not token.is_space)
    if route.route in _TABLE:
        release_headline = _has(backend, text, ("announces record revenue",)) and _has(backend, text, ("raises full-year", "guidance levels"))
        shares_outlook = _has(backend, text, ("weighted-average diluted shares outstanding",)) and _has(backend, text, ("outlook", "reconciliation of gaap to non-gaap outlook")) and numeric <= 8
        if release_headline or shares_outlook:
            reason = "V286_SEMANTIC_RELEASE_HEADLINE" if release_headline else "V286_SEMANTIC_SHARES_OUTLOOK"
            return replace(route, route=BlockRoute.PROSE, reasons=route.reasons + (reason,))
    else:
        balance_grid = _has(backend, text, ("condensed consolidated balance sheets",)) and _has(backend, text, ("current assets", "total liabilities")) and numeric >= 12
        cash_reconciliation = _has(backend, text, ("reconciliation of net cash provided by operating activities",)) and _has(backend, text, ("capital expenditures", "free cash flow")) and numeric >= 6
        if balance_grid or cash_reconciliation:
            reason = "V286_SEMANTIC_BALANCE_GRID" if balance_grid else "V286_SEMANTIC_CASH_RECONCILIATION"
            return replace(route, route=BlockRoute.FLATTENED_TABLE, reasons=route.reasons + (reason,))
    return route


def route_document_blocks_v286(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v285(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v285(document))
