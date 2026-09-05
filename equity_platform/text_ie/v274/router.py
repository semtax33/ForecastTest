from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument

from ..spacy_backend import SpacySemanticBackend, default_spacy_backend
from ..document import document_text_blocks
from ..v26.router import BlockRoute, RoutedBlock
from ..v273.router import route_document_blocks_v273
from .semantics import semantic_quantities_v274
from .context import BoundedSemanticContext, bounded_context


_TABLE_ROUTES = {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def _count(backend: SpacySemanticBackend, text: str, phrases: tuple[str, ...]) -> int:
    return len(backend.phrase_mentions(text, phrases))


def _repair(
    route: RoutedBlock,
    backend: SpacySemanticBackend,
    context: BoundedSemanticContext | None = None,
) -> RoutedBlock:
    text = route.text
    quantities = semantic_quantities_v274(text, backend)
    money_count = sum(item.kind.value == "MONEY" for item in quantities)
    percent_count = sum(item.kind.value == "PERCENT" for item in quantities)

    compact_result = (
        route.route in _TABLE_ROUTES
        and _count(backend, text, ("operating income",)) == 1
        and _count(backend, text, ("operating margin",)) == 1
        and _count(backend, text, ("was",)) >= 1
        and money_count == 1
        and percent_count == 2
    )
    guidance_bullets = (
        route.route in _TABLE_ROUTES
        and _count(backend, text, ("guidance",)) >= 1
        and _count(backend, text, ("revenue",)) >= 1
        and _count(backend, text, ("earnings per share",)) >= 1
        and text.count("◦") >= 2
        and len(text.split()) <= 40
    )
    explanatory_prose = (
        route.route in _TABLE_ROUTES
        and _count(backend, text, ("management provides non-gaap financial measures",)) >= 1
        and money_count == 0
        and percent_count == 0
    )
    if compact_result or guidance_bullets or explanatory_prose:
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("V274_SPACY_SEMANTIC_PROSE",),
        )

    balance_grid = (
        _count(backend, text, ("cash and cash equivalents",)) >= 1
        and _count(backend, text, ("net balance sheet value",)) >= 1
        and _count(backend, text, ("shares outstanding",)) >= 1
        and money_count >= 4
    )
    growth_profile_grid = (
        _count(
            backend,
            text,
            ("strong growth profile", "highlights", "funding agreements", "flow reinsurance"),
        )
        >= 3
        and text.count(":") >= 4
        and percent_count >= 1
    )
    guidance_comparison_grid = (
        _count(backend, text, ("updated", "prior", "guidance", "as of")) >= 5
        and _count(backend, text, ("revenue growth",)) >= 2
        and _count(backend, text, ("adjusted diluted eps",)) >= 1
        and money_count >= 4
    )
    multi_metric_guidance_grid = (
        _count(backend, text, ("guidance",)) >= 1
        and _count(backend, text, ("revenue", "gross merchandise volume", "diluted gaap eps")) >= 3
        and money_count >= 6
        and percent_count >= 4
    )
    milestone_grid = (
        _count(backend, text, ("production capacity milestones",)) >= 1
        and _count(backend, text, ("near full capacity",)) >= 1
        and _count(backend, text, ("installation", "target", "milestones")) >= 3
        and percent_count >= 2
    )
    parent_labeled_grid = bool(
        context
        and context.table_family
        and route.route not in _TABLE_ROUTES
        and money_count + percent_count >= 4
    )
    if (
        balance_grid
        or growth_profile_grid
        or guidance_comparison_grid
        or multi_metric_guidance_grid
        or milestone_grid
        or parent_labeled_grid
    ):
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V274_SPACY_SEMANTIC_GRID",),
        )
    return route


def route_document_blocks_v274(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    backend = default_spacy_backend()
    if backend is None:
        return route_document_blocks_v273(document)
    blocks = {block.char_start: block for block in document_text_blocks(document)}
    return tuple(
        _repair(
            route,
            backend,
            bounded_context(blocks[route.char_start], backend)
            if route.char_start in blocks
            else None,
        )
        for route in route_document_blocks_v273(document)
    )
