from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v288.router import route_document_blocks_v288


_TABLE = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _has(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    numeric = sum(token.like_num for token in backend.parse(text) if not token.is_space)
    if route.route in _TABLE:
        kpi_headline = (
            _has(backend, text, ("document exhibit 99.1", "exhibit 99.1"))
            and _has(backend, text, ("reports",))
            and _has(backend, text, ("revenues of", "revenue of"))
            and _has(backend, text, ("adjusted ebitda of",))
            and _has(backend, text, ("announced results", "reports third quarter", "reports second quarter"))
            and not _has(backend, text, ("three months ended", "six months ended", "in thousands"))
        )
        if kpi_headline:
            return replace(route, route=BlockRoute.PROSE, reasons=route.reasons + ("V289_MULTI_KPI_RELEASE_HEADLINE",))
        prose_balance_assertion = (
            len(text) < 260
            and numeric <= 8
            and _has(backend, text, ("cash", "cash and cash equivalents", "cash balance"))
            and (
                _has(backend, text, ("was", "were"))
                or (
                    _has(backend, text, ("expects", "expected"))
                    and _has(backend, text, ("grow", "growth", "increase"))
                )
            )
            and not _has(backend, text, ("three months ended", "six months ended", "in thousands", "assets current assets"))
        )
        if prose_balance_assertion:
            return replace(route, route=BlockRoute.PROSE, reasons=route.reasons + ("V289_SHORT_BALANCE_ASSERTION",))
    else:
        revenue_header = (
            _has(backend, text, ("financial performance comparisons",))
            and _has(backend, text, ("revenues", "revenue"))
            and _has(backend, text, ("% change", "change"))
            and _has(backend, text, ("product revenue",))
            and numeric >= 4
        )
        if revenue_header:
            return replace(route, route=BlockRoute.FLATTENED_TABLE, reasons=route.reasons + ("V289_REVENUE_HEADER_FRAGMENT",))
    return route


def route_document_blocks_v289(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v288(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v288(document))
