from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v277.router import route_document_blocks_v277


_TABLE_ROUTES = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _phrase_count(
    backend: SpacySemanticBackend,
    text: str,
    phrases: tuple[str, ...],
) -> int:
    return len(backend.phrase_mentions(text, phrases))


def _is_truncated_prose(tokens: tuple[object, ...]) -> bool:
    return (
        len(tokens) >= 2
        and (
            tokens[0].lower_ == "s."
            and tokens[1].text == ","
            or len(tokens) >= 3
            and tokens[0].lower_ == "s"
            and tokens[1].text == "."
            and tokens[2].text == ","
        )
    )


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    folded = text.casefold()
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    numeric = sum(token.like_num for token in tokens)
    alpha = sum(token.is_alpha for token in tokens)
    sentence_marks = sum(token.text in {".", ";", "?", "!"} for token in tokens)

    semantic_bullets = "highlights" in folded and text.count("➢") >= 2
    truncated_prose = _is_truncated_prose(tokens) and _phrase_count(
        backend,
        text,
        (
            "total revenue",
            "backlog",
            "customer demand",
            "proposal activity",
        ),
    )
    if semantic_bullets or truncated_prose:
        return replace(
            route,
            route=BlockRoute.LIST_BULLET if semantic_bullets else BlockRoute.PROSE,
            reasons=route.reasons
            + (
                "V278_SEMANTIC_BULLET_PROSE"
                if semantic_bullets
                else "V278_TRUNCATED_SENTENCE_PROSE",
            ),
        )

    summary_grid = (
        _phrase_count(
            backend,
            text,
            (
                "operating results summary",
                "operating results forecast",
                "supplemental non-gaap disclosures",
            ),
        )
        >= 2
        and _phrase_count(backend, text, ("dollars in millions", "in millions"))
        and numeric >= 6
    )
    statement_rows = _phrase_count(
        backend,
        text,
        (
            "net income",
            "depreciation and amortization",
            "interest expense",
            "provision for income taxes",
            "adjusted ebitda",
            "cash provided by operating activities",
            "capital expenditures",
            "free cash flow",
        ),
    )
    repeated_financial_rows = statement_rows >= 3 and numeric >= 12
    period_row_grid = (
        _phrase_count(
            backend,
            text,
            ("six months ended", "three months ended", "in millions of dollars"),
        )
        >= 2
        and statement_rows >= 2
        and numeric >= 8
    )
    compact_comparison_grid = (
        _phrase_count(backend, text, ("operating income",))
        and ("reported vs" in folded or "reported versus" in folded)
        and numeric >= 4
        and alpha <= 12
    )
    dense_numeric_grid = numeric >= 16 and sentence_marks <= 1 and numeric >= alpha / 2
    if (
        summary_grid
        or repeated_financial_rows
        or period_row_grid
        or compact_comparison_grid
        or dense_numeric_grid
    ):
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V278_SPACY_FINANCIAL_GRID",),
        )
    return route


def route_document_blocks_v278(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v277(document)
    return tuple(
        _repair(route, backend) for route in route_document_blocks_v277(document)
    )
