from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v269.router import route_document_blocks_v269


def _count(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> int:
    return len(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    numeric_tokens = sum(token.like_num for token in tokens)
    sentence_count = sum(bool(token.is_sent_start) for token in tokens)

    table_footnote = (
        _count(backend, text, ("revenue adjustments", "inorganic revenue")) >= 2
        and _count(backend, text, ("three months ended", "twelve months ended")) >= 2
        and _count(backend, text, ("excludes",))
        and sentence_count >= 2
    )
    if table_footnote:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V270_TABLE_FOOTNOTE_PROSE",),
        )

    compact_financial_grid = (
        _count(
            backend,
            text,
            ("net revenues", "provision for credit losses", "total expenses", "compensation"),
        )
        >= 2
        and _count(backend, text, ("millions",))
        and numeric_tokens >= 4
        and sentence_count <= 4
    )
    business_driver_grid = (
        _count(
            backend,
            text,
            ("key business drivers", "gross dollar volume", "cross-border volume", "switched transactions"),
        )
        >= 3
        and numeric_tokens >= 3
    )
    net_debt_grid = (
        _count(
            backend,
            text,
            ("net debt reconciliation", "total debt", "cash and cash equivalents", "net debt"),
        )
        >= 3
        and numeric_tokens >= 4
    )
    margin_grid = (
        _count(backend, text, ("gaap operating margin", "non-gaap operating margin"))
        >= 2
        and numeric_tokens >= 4
        and sentence_count <= 2
    )
    if compact_financial_grid or business_driver_grid or net_debt_grid or margin_grid:
        return replace(
            route,
            route=(BlockRoute.MIXED if compact_financial_grid else BlockRoute.FLATTENED_TABLE),
            reasons=route.reasons + ("V270_SPACY_COMPACT_GRID",),
        )
    return route


def route_document_blocks_v270(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v269(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v269(document))
