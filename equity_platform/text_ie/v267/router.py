from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v266.router import route_document_blocks_v266


_NARRATIVE_NOTE_CUES = (
    "table below",
    "the company defines",
    "guidance does not include",
)
_PERIOD_GRID_CUES = (
    "quarters ended",
    "six months ended",
)
_SHARE_GRID_CUES = (
    "weighted-average common shares outstanding",
    "basic",
    "diluted",
)
_PRODUCT_ROW_CUES = (
    "growth primarily due",
    "growth primarily driven",
)
_DENSE_GRID_CUES = (
    "cost of sales",
    "tax rate",
    "net loss",
)


def _count(
    backend: SpacySemanticBackend,
    text: str,
    phrases: tuple[str, ...],
) -> int:
    return len(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    doc = backend.parse(text)
    numeric_tokens = sum(token.like_num for token in doc)
    year_tokens = sum(
        token.like_num and len(token.text) == 4 and token.text.startswith("20")
        for token in doc
    )
    sentence_end_tokens = sum(token.text in {".", ";"} for token in doc)

    if (
        _count(backend, text, ("table below",))
        and _count(backend, text, _NARRATIVE_NOTE_CUES) >= 2
        and sentence_end_tokens >= 2
    ):
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V267_SEMANTIC_NARRATIVE_NOTES",),
        )

    period_grid = (
        _count(backend, text, _PERIOD_GRID_CUES) >= 2
        and year_tokens >= 4
        and numeric_tokens >= 8
    )
    share_grid = (
        _count(backend, text, _SHARE_GRID_CUES) >= 3
        and numeric_tokens >= 12
    )
    product_row = (
        _count(backend, text, _PRODUCT_ROW_CUES) >= 1
        and numeric_tokens >= 4
        and sentence_end_tokens <= 1
    )
    dense_grid = (
        _count(backend, text, _DENSE_GRID_CUES) >= 2
        and numeric_tokens >= 20
        and sentence_end_tokens <= 2
    )
    if period_grid or share_grid or product_row or dense_grid:
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V267_SEMANTIC_ROW_OR_PERIOD_GRID",),
        )
    return route


def route_document_blocks_v267(
    document: CanonicalDocument,
) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v266(document)
    return tuple(
        _repair(route, backend) for route in route_document_blocks_v266(document)
    )
