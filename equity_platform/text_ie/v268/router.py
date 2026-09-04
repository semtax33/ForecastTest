from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..v26.router import BlockRoute, RoutedBlock
from ..v267.router import route_document_blocks_v267


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
    first_two = tuple(token.lower_ for token in tokens[:2])

    causal_prose = (
        _count(backend, text, ("the increase was primarily due to",))
        and numeric_tokens <= 5
        and sentence_count <= 2
    )
    if causal_prose:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V268_CAUSAL_PROSE_SENTENCE",),
        )

    truncated_geography_grid = (
        first_two == ("s.",) or first_two[:1] == ("s.",)
    ) and numeric_tokens >= 2
    # spaCy normally splits the prefix into ``S`` and ``.``.
    truncated_geography_grid = truncated_geography_grid or (
        len(tokens) >= 2
        and tokens[0].lower_ == "s"
        and tokens[1].text == "."
        and numeric_tokens >= 2
    )
    organic_bridge_grid = (
        _count(backend, text, ("organic revenue growth",)) >= 2
        and _count(backend, text, ("three months ended", "six months ended"))
        and numeric_tokens >= 5
    )
    reconciliation_grid = (
        tokens
        and tokens[0].lower_ in {"end", "ended"}
        and _count(
            backend,
            text,
            ("consolidated net income", "consolidated adjusted ebitda"),
        )
        >= 2
        and numeric_tokens >= 8
    )
    if truncated_geography_grid or organic_bridge_grid or reconciliation_grid:
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V268_SPACY_FLATTENED_GRID",),
        )
    return route


def route_document_blocks_v268(
    document: CanonicalDocument,
) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v267(document)
    return tuple(
        _repair(route, backend) for route in route_document_blocks_v267(document)
    )
