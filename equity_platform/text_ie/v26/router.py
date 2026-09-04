from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from equity_platform.documents import CanonicalDocument

from ..document import document_text_blocks
from ..v24 import extract_candidate_quantities, metric_anchors


class BlockRoute(StrEnum):
    TRUE_TABLE = "TRUE_TABLE"
    FLATTENED_TABLE = "FLATTENED_TABLE"
    PROSE = "PROSE"
    LIST_BULLET = "LIST_BULLET"
    MIXED = "MIXED"


@dataclass(frozen=True)
class RoutedBlock:
    route: BlockRoute
    sentence_index: int | None
    char_start: int | None
    char_end: int | None
    text: str
    reasons: tuple[str, ...]
    source_table_index: int | None = None


_PERIOD = re.compile(r"\b(?:20\d{2}|Q[1-4]|FY\s*\d{2,4}|three months ended|six months ended|year ended)\b", re.I)
_COLUMN = re.compile(r"\b(?:change|gaap|non-gaap|adjusted|reported|constant currency|quarter ended|year ended)\b", re.I)
_ROW = re.compile(r"\b(?:revenues?|net sales|operating income|operating margin|gross margin|cash|debt|cap(?:ital )?expenditures?)\b", re.I)
_NUMERIC_CELL = re.compile(r"(?<![A-Za-z])(?:\$\s*)?[-(]?\d[\d,.]*(?:\)|\s*%)?")


def _text_route(block: object) -> RoutedBlock:
    text = block.text
    quantities = extract_candidate_quantities(text)
    numeric_cells = len(_NUMERIC_CELL.findall(text))
    periods = len(_PERIOD.findall(text))
    columns = len(_COLUMN.findall(text))
    rows = len(_ROW.findall(text))
    bullets = len(re.findall(r"[•◦▪]", text))
    # SEC/IR flattened statements often contain dot leaders, not sentences.
    punctuation_text = re.sub(r"\.{2,}", "", text)
    sentence_marks = len(re.findall(r"(?<!\d)[.!?](?!\d)", punctuation_text))
    token_count = max(1, len(text.split()))
    low_punctuation = sentence_marks <= 1 or sentence_marks / token_count < 0.015
    explicit_table = re.search(r"\b(?:table below|following table)\b", text, re.I) is not None
    structural_grid = (
        len(quantities) >= 6
        and rows >= 1
        and (periods >= 2 or columns >= 2)
    ) or (
        numeric_cells >= 10 and rows >= 1
    ) or (
        explicit_table and len(quantities) >= 6
    )
    grid = structural_grid and (low_punctuation or numeric_cells >= 16 or explicit_table)
    prose = sentence_marks >= 1 and token_count >= 18
    if grid and prose:
        route = BlockRoute.MIXED
    elif grid:
        route = BlockRoute.FLATTENED_TABLE
    elif bullets >= 2:
        route = BlockRoute.LIST_BULLET
    else:
        route = BlockRoute.PROSE
    reasons = []
    if grid:
        reasons.append("REPEATED_TYPED_NUMERIC_COLUMNS")
    if explicit_table:
        reasons.append("EXPLICIT_TABLE_ANCESTOR_TEXT")
    if periods >= 2:
        reasons.append("MULTI_PERIOD_HEADER")
    if low_punctuation:
        reasons.append("LOW_SENTENCE_PUNCTUATION")
    if bullets >= 2:
        reasons.append("BULLET_MARKERS")
    return RoutedBlock(route, block.sentence_index, block.char_start, block.char_end, text, tuple(reasons))


def route_document_blocks(document: CanonicalDocument) -> tuple[RoutedBlock, ...]:
    """Route DOM tables and text blocks before semantic extraction."""

    routes = [
        RoutedBlock(
            route=BlockRoute.TRUE_TABLE,
            sentence_index=None,
            char_start=None,
            char_end=None,
            text=" | ".join(" | ".join(row) for row in table.cells),
            reasons=("DOM_TABLE_ANCESTRY",),
            source_table_index=table.source_table_index,
        )
        for table in document.tables
    ]
    routes.extend(_text_route(block) for block in document_text_blocks(document))
    return tuple(routes)
