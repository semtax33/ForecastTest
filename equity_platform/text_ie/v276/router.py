from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v275.router import route_document_blocks_v275
from .semantics import semantic_quantities_v276


_TABLE_ROUTES = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    if route.route not in _TABLE_ROUTES:
        return route
    text = route.text
    folded = text.casefold()
    tokens = tuple(backend.parse(text))
    quantities = semantic_quantities_v276(text, backend)
    alpha = sum(token.is_alpha for token in tokens)
    numeric_tokens = sum(token.like_num for token in tokens)
    money = sum(item.kind.value == "MONEY" for item in quantities)
    percent = sum(item.kind.value == "PERCENT" for item in quantities)
    revpar_prose = "revpar" in folded and percent >= 1 and alpha >= 10
    contacts = (
        "contacts:" in folded
        and "media:" in folded
        and "investors:" in folded
        and money == 0
        and percent == 0
    )
    activity_prose = (
        any(token.lemma_.casefold() == "participate" for token in tokens)
        and any(token.lemma_.casefold() == "transaction" for token in tokens)
        and alpha >= 10
    )
    explanatory_prose = alpha >= 50 and numeric_tokens <= 30 and percent == 0
    if revpar_prose or contacts or activity_prose or explanatory_prose:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V276_SPACY_SEMANTIC_PROSE",),
        )
    return route


def route_document_blocks_v276(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v275(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v275(document))
