from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v271.router import route_document_blocks_v271


_RISK_CUES = (
    "risks and uncertainties",
    "risk of",
    "economic conditions",
    "political conditions",
    "regulatory changes",
)


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    if route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}:
        return route
    tokens = tuple(token for token in backend.parse(route.text) if not token.is_space)
    lexical_count = sum(token.is_alpha for token in tokens)
    business_numbers = sum(
        any(character.isdigit() for character in token.text)
        and not (
            len(token.text) == 4
            and token.text.isdigit()
            and 1900 <= int(token.text) <= 2100
        )
        for token in tokens
    )
    risk_enumeration = (
        lexical_count >= 40
        and business_numbers == 0
        and route.text.count(";") >= 3
        and bool(backend.phrase_mentions(route.text, _RISK_CUES))
        and "$" not in route.text
        and "%" not in route.text
    )
    if not risk_enumeration:
        return route
    return replace(
        route,
        route=BlockRoute.PROSE,
        reasons=route.reasons + ("V272_SPACY_RISK_ENUMERATION_PROSE",),
    )


def route_document_blocks_v272(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v271(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v271(document))
