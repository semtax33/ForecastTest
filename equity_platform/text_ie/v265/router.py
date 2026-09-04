from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v263.router import route_document_blocks_v263


_DISCLAIMER_CUES = (
    "not able to reconcile",
    "cannot provide a reconciliation",
    "without unreasonable effort",
    "without unreasonable efforts",
)
_DECLARED_TABLE_CUES = (
    "following table reconciles",
    "guidance reconciliations",
)
_ROW_LABEL_CUES = (
    "earnings per share",
    "weighted average shares outstanding",
    "dividends per share",
    "adjusted net income",
)


def _phrases(
    backend: SpacySemanticBackend,
    text: str,
    vocabulary: tuple[str, ...],
) -> set[str]:
    return {
        text[start:end].casefold()
        for _, start, end in backend.phrase_mentions(text, vocabulary)
    }


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    folded = text.casefold()
    if _phrases(backend, text, _DISCLAIMER_CUES):
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("SEMANTIC_RECONCILIATION_DISCLAIMER",),
        )

    doc = backend.parse(text)
    numeric_tokens = sum(token.like_num for token in doc)
    year_tokens = sum(
        token.like_num
        and len(token.text) == 4
        and token.text.startswith("20")
        for token in doc
    )
    declared_table = bool(_phrases(backend, text, _DECLARED_TABLE_CUES))
    quarter_grid = (
        "second quarter" in folded
        and "year to date" in folded
        and folded.count("change") >= 2
        and year_tokens >= 4
        and numeric_tokens >= 8
    )
    duration_grid = (
        "three months ended" in folded
        and "six months ended" in folded
        and year_tokens >= 4
    )
    segment_grid = (
        "earnings and volume summary by segment" in folded
        and "dollars in millions" in folded
        and "ytd" in folded
    )
    row_labels = _phrases(backend, text, _ROW_LABEL_CUES)
    dense_row_grid = len(row_labels) >= 2 and numeric_tokens >= 8
    if declared_table or quarter_grid or duration_grid or segment_grid or dense_row_grid:
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V265_SEMANTIC_FINANCIAL_GRID",),
        )
    return route


def route_document_blocks_v265(
    document: CanonicalDocument,
) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    return tuple(
        _repair(route, backend) for route in route_document_blocks_v263(document)
    )
