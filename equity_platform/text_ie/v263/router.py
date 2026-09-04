from __future__ import annotations

from dataclasses import replace
import re

from equity_platform.documents import CanonicalDocument

from ..v26.router import BlockRoute, RoutedBlock
from ..v262.router import route_document_blocks_v262


_NOT_A_TABLE = re.compile(
    r"\b(?:not able to reconcile|cannot provide a reconciliation|without unreasonable efforts)\b",
    re.I,
)
_EXPLICIT_RECONCILIATION = re.compile(
    r"\b(?:following table reconciles|guidance reconciliations)\b",
    re.I,
)
_PERIOD_GRID = re.compile(
    r"\b(?:YTD\s+20\d{2}\s+YTD\s+20\d{2}|2Q\s+20\d{2}\s+1Q\s+20\d{2}\s+2Q\s+20\d{2})\b",
    re.I,
)
_NUMBER = re.compile(r"(?<![A-Za-z])-?\d[\d,]*(?:\.\d+)?")


def _repair(route: RoutedBlock) -> RoutedBlock:
    text = route.text
    if _NOT_A_TABLE.search(text):
        return replace(
            route,
            route=BlockRoute.PROSE,
            reasons=route.reasons + ("RECONCILIATION_DISCLAIMER_PROSE",),
        )
    if (
        _EXPLICIT_RECONCILIATION.search(text)
        or (_PERIOD_GRID.search(text) and len(_NUMBER.findall(text)) >= 12)
    ):
        return replace(
            route,
            route=BlockRoute.FLATTENED_TABLE,
            reasons=route.reasons + ("V263_DECLARED_FINANCIAL_GRID",),
        )
    return route


def route_document_blocks_v263(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    return tuple(_repair(route) for route in route_document_blocks_v262(document))
