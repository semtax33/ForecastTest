from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v274.router import route_document_blocks_v274
from .semantics import semantic_quantities_v275


_TABLE_ROUTES = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _count(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> int:
    return len(backend.phrase_mentions(text, phrases))


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    quantities = semantic_quantities_v275(text, backend)
    money = sum(item.kind.value == "MONEY" for item in quantities)
    percent = sum(item.kind.value == "PERCENT" for item in quantities)
    tokens = tuple(backend.parse(text))
    alpha = sum(token.is_alpha for token in tokens)
    numeric_tokens = sum(token.like_num for token in tokens)
    has_sales = any(token.lemma_.casefold() == "sale" for token in tokens)
    has_yoy = any(token.lower_.startswith("yoy") for token in tokens)
    has_reported = any(token.lemma_.casefold() == "report" for token in tokens)
    has_revenue = any(token.lemma_.casefold() == "revenue" for token in tokens)
    has_increase = any(token.lemma_.casefold() == "increase" for token in tokens)
    folded = text.casefold()

    earnings_release_prose = (
        route.route in _TABLE_ROUTES
        and has_reported
        and has_revenue
        and has_increase
        and money >= 1
        and percent >= 1
        and alpha >= 15
        and numeric_tokens <= 30
    )
    long_risk_prose = (
        route.route in _TABLE_ROUTES
        and alpha >= 50
        and money == 0
        and percent <= 1
        and text.count(";") >= 4
    )
    if earnings_release_prose or long_risk_prose:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V275_SPACY_SEMANTIC_PROSE",),
        )

    compact_numeric_grid = alpha <= 10 and numeric_tokens >= 6
    product_sales_grid = (
        (has_sales or "net sales" in folded)
        and (has_yoy or "yoy" in folded)
        and "ex-fx" in folded
        and money >= 3
        and percent >= 6
        and numeric_tokens >= 10
        and alpha <= 80
    )
    if compact_numeric_grid or product_sales_grid:
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V275_SPACY_SEMANTIC_GRID",),
        )
    return route


def route_document_blocks_v275(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v274(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v274(document))
