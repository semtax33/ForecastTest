from __future__ import annotations

from dataclasses import replace
import re

from equity_platform.documents import CanonicalDocument

from ..v24 import extract_candidate_quantities, metric_anchors
from ..v26.router import BlockRoute, RoutedBlock, route_document_blocks


_BULLET = re.compile(r"[●◌◦▪·]")
_RELATION = re.compile(r"\b(?:increase|increased|decrease|decreased|compared|up|down)\b", re.I)
_FALSE_GRID_DOMAIN = re.compile(
    r"\b(?:entered into an? (?:umbrella|sales|purchase)|Internal Revenue Code|"
    r"founder shares|public warrants|registration statement)\b",
    re.I,
)


def _repair(route: RoutedBlock, heading: str | None) -> RoutedBlock:
    text = route.text
    bullets = len(_BULLET.findall(text))
    anchors = metric_anchors(text, heading)
    quantities = extract_candidate_quantities(text)
    if route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}:
        if bullets >= 2 and anchors and _RELATION.search(text):
            return replace(route, route=BlockRoute.LIST_BULLET, reasons=route.reasons + ("KPI_BULLET_PRECEDENCE",))
        if _FALSE_GRID_DOMAIN.search(text):
            return replace(route, route=BlockRoute.PROSE, reasons=route.reasons + ("NON_OPERATING_DENSE_PROSE",))
        if (
            re.search(r"\bcapital expenditures\b", text, re.I)
            and re.search(r"\bpurchase of\b", text, re.I)
            and sum(item.unit == "USD" for item in quantities) == 1
        ):
            return replace(route, route=BlockRoute.PROSE, reasons=route.reasons + ("SINGLE_FINANCIAL_VALUE_WITH_ITEM_COUNTS",))
    if (
        route.route is BlockRoute.PROSE
        and re.search(r"\bSales by Product\b", text, re.I)
        and re.search(r"\bBacklog\b", text, re.I)
        and sum(item.unit == "USD" for item in quantities) >= 4
    ):
        return replace(route, route=BlockRoute.FLATTENED_TABLE, reasons=route.reasons + ("SLIDE_GRID_WITH_YEAR_SERIES",))
    return route


def route_document_blocks_v261(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    headings = {
        sentence.char_start: sentence.heading for sentence in document.sentences
    }
    return tuple(
        route if route.char_start is None else _repair(route, headings.get(route.char_start))
        for route in route_document_blocks(document)
    )
