from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v268.router import route_document_blocks_v268


def _count(
    backend: SpacySemanticBackend,
    text: str,
    phrases: tuple[str, ...],
) -> int:
    return len(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    doc = backend.parse(text)
    tokens = tuple(token for token in doc if not token.is_space)
    numeric_tokens = sum(token.like_num for token in tokens)
    sentence_count = sum(bool(token.is_sent_start) for token in tokens)

    direct_causal_kpi = (
        _count(backend, text, ("sales increased", "sales decreased"))
        and _count(backend, text, ("year-over-year", "year over year"))
        and _count(backend, text, ("driven by",))
        and numeric_tokens <= 8
        and sentence_count <= 2
    )
    explanatory_note = (
        _count(backend, text, ("analysis notes", "earnings analysis notes"))
        and _count(backend, text, ("associated with", "respectively")) >= 2
        and sentence_count >= 2
    )
    if direct_causal_kpi or explanatory_note:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons
            + (
                "V269_DIRECT_CAUSAL_PROSE"
                if direct_causal_kpi
                else "V269_EXPLANATORY_NOTE_PROSE",
            ),
        )

    short_reconciliation_grid = (
        _count(
            backend,
            text,
            ("total operating expenses", "operating income as % of product sales"),
        )
        >= 2
        and numeric_tokens >= 8
        and sentence_count <= 2
    )
    embedded_financial_highlights = (
        _count(backend, text, ("financial highlights", "dollars in millions")) >= 2
        and _count(backend, text, ("net revenue", "adjusted ebitda")) >= 2
        and numeric_tokens >= 20
    )
    operating_statistics_grid = (
        _count(
            backend,
            text,
            ("quarterly operating statistics", "average daily volume", "product line"),
        )
        >= 3
        and numeric_tokens >= 12
    )
    quarter_revenue_grid = (
        _count(
            backend,
            text,
            ("segment revenues", "recurring revenues", "transaction revenues"),
        )
        >= 3
        and numeric_tokens >= 12
    )
    if (
        short_reconciliation_grid
        or embedded_financial_highlights
        or operating_statistics_grid
        or quarter_revenue_grid
    ):
        return replace(
            route,
            route=(
                BlockRoute.MIXED
                if embedded_financial_highlights or quarter_revenue_grid
                else BlockRoute.FLATTENED_TABLE
            ),
            reasons=route.reasons + ("V269_SPACY_STRUCTURED_GRID",),
        )
    return route


def route_document_blocks_v269(
    document: CanonicalDocument,
) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v268(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v268(document))
