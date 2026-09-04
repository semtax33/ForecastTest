from __future__ import annotations

from dataclasses import replace
import re

from equity_platform.documents import CanonicalDocument

from ..v26.router import BlockRoute, RoutedBlock
from ..v261.router import route_document_blocks_v261


_TABLE_EXPLICIT = re.compile(r"\bPage\s+\d+\s+Table\s+\d+\s+cont\.?", re.I)
_TABLE_PERIOD_GRID = re.compile(r"\b(?:Quarter|Months)\s+Ended\b", re.I)
_TABLE_SLIDE_FRAGMENT = re.compile(
    r"\b(?:stable|higher|lower)\s+(?:realized\s+pricing|volumes?)\b",
    re.I,
)
_TABLE_LABEL_FRAGMENT = re.compile(
    r"\b(?:EBIT\s+Margin|SEGMENT\s+RESULTS|Comparable\s+Sales\s+Summary)\b",
    re.I,
)
_NARRATIVE_REVENUE = re.compile(
    r"\brevenues?\s+(?:totaled|grew|increased|decreased)\b",
    re.I,
)
_PRESS_RELEASE_LEAD = re.compile(r"\bFOR\s+IMMEDIATE\s+RELEASE\b", re.I)
_NON_GAAP_RECONCILIATION = re.compile(
    r"\bAs\s+reported\s*\(GAAP\).{20,}\bAdjusted\s*\(non-GAAP\)",
    re.I,
)
_RELATIONAL_PROSE = re.compile(
    r"\b(?:outlook\s+includes|growth\s+of|increased|decreased|grew|declined)\b",
    re.I,
)
_NUMBER = re.compile(r"(?<![A-Za-z])(?:\$\s*)?-?\d[\d,]*(?:\.\d+)?\s*(?:%|billion|million|bps?)?", re.I)


def _repair(route: RoutedBlock) -> RoutedBlock:
    text = route.text
    numeric_count = len(_NUMBER.findall(text))
    if route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED} and (
        _NARRATIVE_REVENUE.search(text)
        or _PRESS_RELEASE_LEAD.search(text)
        or (
            _RELATIONAL_PROSE.search(text)
            and not _TABLE_EXPLICIT.search(text)
            and len(text) < 800
        )
    ):
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("DENSE_NARRATIVE_OWNS_NUMBERS",),
        )
    if route.route not in {BlockRoute.TRUE_TABLE, BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}:
        explicit_grid = bool(_TABLE_EXPLICIT.search(text)) and numeric_count >= 8
        period_grid = bool(_TABLE_PERIOD_GRID.search(text)) and numeric_count >= 12
        slide_grid = bool(_TABLE_SLIDE_FRAGMENT.search(text)) and numeric_count >= 3
        label_grid = (
            bool(_TABLE_LABEL_FRAGMENT.search(text))
            and numeric_count >= 2
            and not _RELATIONAL_PROSE.search(text)
            and len(text) < 240
        )
        reconciliation_grid = bool(_NON_GAAP_RECONCILIATION.search(text)) and numeric_count >= 8
        if explicit_grid or period_grid or slide_grid or label_grid or reconciliation_grid:
            return replace(
                route,
                route=BlockRoute.FLATTENED_TABLE,
                reasons=route.reasons + ("V262_EXPLICIT_GRID_SIGNATURE",),
            )
    return route


def route_document_blocks_v262(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    return tuple(_repair(route) for route in route_document_blocks_v261(document))
