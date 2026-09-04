from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v265.router import route_document_blocks_v265


_NARRATIVE_CUES = (
    "business segment results",
    "sales for",
)
_RECONCILIATION_CUES = (
    "reconciliation of net income",
    "reconciliation of gaap to non-gaap",
)
_DURATION_CUES = (
    "three months ended",
    "six months ended",
)
_COLUMN_CUES = (
    "$ in millions",
    "% change",
)
_COLUMN_ROWS = (
    "net sales",
    "operating profit",
    "operating margin",
)
_MIDPOINT_CUES = (
    "mid-point",
    "midpoint",
)
_REGIONAL_GRID_CUES = (
    "regional sales results",
    "adjusted operational",
    "reported operational",
)


def _phrase_count(
    backend: SpacySemanticBackend,
    text: str,
    vocabulary: tuple[str, ...],
) -> int:
    return len(backend.phrase_mentions(text, vocabulary))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    doc = backend.parse(text)
    numeric_tokens = sum(token.like_num for token in doc)
    sentence_end_tokens = sum(token.text in {".", ";"} for token in doc)
    year_tokens = sum(
        token.like_num and len(token.text) == 4 and token.text.startswith("20")
        for token in doc
    )

    if all(_phrase_count(backend, text, (cue,)) for cue in _NARRATIVE_CUES):
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V266_SEMANTIC_NARRATIVE_SENTENCE",),
        )

    reconciliation = _phrase_count(backend, text, _RECONCILIATION_CUES) > 0
    duration_headers = _phrase_count(backend, text, _DURATION_CUES)
    column_cues = _phrase_count(backend, text, _COLUMN_CUES)
    column_rows = _phrase_count(backend, text, _COLUMN_ROWS)
    midpoint_count = _phrase_count(backend, text, _MIDPOINT_CUES)
    regional_grid = _phrase_count(backend, text, _REGIONAL_GRID_CUES) >= 2

    is_grid = any(
        (
            reconciliation and duration_headers >= 2 and year_tokens >= 2,
            reconciliation and numeric_tokens >= 2,
            column_cues >= 2 and column_rows >= 2 and year_tokens >= 2,
            midpoint_count >= 2 and numeric_tokens >= 6 and sentence_end_tokens == 0,
            regional_grid and year_tokens >= 2,
        )
    )
    if is_grid:
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V266_SEMANTIC_FINANCIAL_GRID",),
        )
    return route


def route_document_blocks_v266(
    document: CanonicalDocument,
) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v265(document)
    return tuple(
        _repair(route, backend) for route in route_document_blocks_v265(document)
    )
