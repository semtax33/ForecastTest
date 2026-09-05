from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import default_spacy_backend
from ..v26.router import BlockRoute
from ..v26.router import RoutedBlock
from ..v276.router import route_document_blocks_v276


_TABLE_ROUTES = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _repair(route: RoutedBlock) -> RoutedBlock:
    backend = default_spacy_backend()
    if backend is None:
        return route
    folded = route.text.casefold()
    tokens = tuple(token for token in backend.parse(route.text) if not token.is_space)
    numeric = sum(token.like_num for token in tokens)
    table_lemmas = sum(
        token.lemma_.casefold() in {"change", "premium", "ratio", "income"}
        for token in tokens
    )
    period_markers = sum(
        token.text.casefold().startswith(("q1", "q2", "q3", "q4", "6m", "9m"))
        or token.text.isdigit() and len(token.text) == 4
        for token in tokens
    )
    segment_guidance = (
        "segment property revenue" in folded
        and "reflecting midpoint growth rates" in folded
        and "respectively" in folded
    )
    if segment_guidance and route.route in _TABLE_ROUTES:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V277_SEGMENT_GUIDANCE_PROSE",),
        )
    flattened_financial_grid = (
        "in millions" in folded
        and numeric >= 8
        and period_markers >= 2
        and (table_lemmas >= 5 or period_markers >= 4 and table_lemmas >= 3)
    )
    constant_currency_grid = (
        "unaudited" in folded
        and "constant currency" in folded
        and folded.count("fx impact") >= 2
        and numeric >= 5
    )
    if route.route not in _TABLE_ROUTES and (flattened_financial_grid or constant_currency_grid):
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V277_SPACY_FINANCIAL_GRID",),
        )
    return route


def route_document_blocks_v277(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    return tuple(_repair(route) for route in route_document_blocks_v276(document))
