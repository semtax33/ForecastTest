from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v280.router import route_document_blocks_v280


_TABLE = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _mentions(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _mentions_all(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> bool:
    return all(_mentions(backend, text, (phrase,)) for phrase in phrases)


def _repair(route: RoutedBlock, backend: SpacySemanticBackend) -> RoutedBlock:
    text = route.text
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    numeric = sum(token.like_num for token in tokens)
    if route.route in _TABLE:
        semantic_sentence = (
            numeric <= 8
            and (
                _mentions(backend, text, ("operating margin",))
                and any(token.lemma_.casefold() == "expand" for token in tokens)
                or _mentions(backend, text, ("adjusted ebitda", "revenue growth"))
                and any(token.lemma_.casefold() in {"increase", "expect"} for token in tokens)
            )
        )
        if semantic_sentence:
            return replace(route, route=BlockRoute.PROSE, reasons=route.reasons + ("V281_SEMANTIC_NUMERIC_SENTENCE",))
    else:
        net_debt_grid = (
            _mentions(backend, text, ("net debt and adjusted net debt",))
            and _mentions_all(backend, text, ("short-term borrowings", "long-term debt", "total debt", "net debt"))
            and numeric >= 10
        )
        corporate_outlook_grid = (
            _mentions_all(backend, text, ("other corporate", "capital expenditures", "depreciation and amortization", "adjusted effective tax rate"))
            and numeric >= 5
        )
        if net_debt_grid or corporate_outlook_grid:
            return replace(route, route=BlockRoute.FLATTENED_TABLE, reasons=route.reasons + ("V281_SEMANTIC_FINANCIAL_GRID",))
    return route


def route_document_blocks_v281(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v280(document)
    return tuple(_repair(route, backend) for route in route_document_blocks_v280(document))
