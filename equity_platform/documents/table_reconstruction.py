from __future__ import annotations

from dataclasses import dataclass
import re

from equity_platform.text_ie.model import TextBlock
from equity_platform.text_ie.ontology import find_concepts
from equity_platform.text_ie.quantities import extract_quantities


_PERIOD_TOKEN = re.compile(
    r"\b(?:[1-4]Q\s?\d{2,4}|Q[1-4][ -]?\d{2,4}|YTD|year[- ]to[- ]date|"
    r"three months ended|six months ended|year ended|\d{4})\b",
    re.IGNORECASE,
)
_TABLE_UNIT = re.compile(
    r"\b(?:dollars? in (?:millions|thousands)|millions of dollars|"
    r"in millions|except per share|unaudited)\b",
    re.IGNORECASE,
)
_TABLE_TITLE = re.compile(
    r"\b(?:financial results|consolidated statements?|balance sheets?|"
    r"cash flows?|reconciliation|operating highlights|earnings release tables|"
    r"cash capital expenditures)\b",
    re.IGNORECASE,
)
_NUMERIC_CELL = re.compile(r"(?<![A-Za-z])[-(]?\d[\d,.]*(?:\))?")


@dataclass(frozen=True)
class TableReconstructionCandidate:
    sentence_index: int
    char_start: int
    char_end: int
    source_literal: str
    period_headers: tuple[str, ...]
    metric_labels: tuple[str, ...]
    numeric_cells: int
    reasons: tuple[str, ...]


def reconstruct_flattened_table(block: TextBlock) -> TableReconstructionCandidate | None:
    """Recognize a flattened table before sentence-level semantic extraction.

    This stage deliberately does not emit facts.  It preserves the exact block,
    headers, metric labels, and numeric-cell count for the dedicated table DSL.
    """

    quantities = extract_quantities(block.text)
    numeric_cells = len(_NUMERIC_CELL.findall(block.text))
    periods = tuple(dict.fromkeys(match.group(0) for match in _PERIOD_TOKEN.finditer(block.text)))
    has_units = _TABLE_UNIT.search(block.text) is not None
    has_title = _TABLE_TITLE.search(block.text) is not None
    concepts = tuple(dict.fromkeys(item.concept for item in find_concepts(block.text)))
    reasons: list[str] = []
    if numeric_cells >= 12:
        reasons.append("NUMERIC_CELL_DENSITY")
    if len(periods) >= 2:
        reasons.append("MULTI_PERIOD_HEADER")
    if has_units:
        reasons.append("TABLE_UNIT_HEADER")
    if has_title:
        reasons.append("TABLE_TITLE")
    is_table = (
        numeric_cells >= 12
        and len(periods) >= 2
        and (has_units or has_title)
    ) or (
        numeric_cells >= 20 and has_units and has_title
    )
    if not is_table:
        return None
    return TableReconstructionCandidate(
        sentence_index=block.sentence_index,
        char_start=block.char_start,
        char_end=block.char_end,
        source_literal=block.text,
        period_headers=periods,
        metric_labels=concepts,
        numeric_cells=numeric_cells,
        reasons=tuple(reasons),
    )
