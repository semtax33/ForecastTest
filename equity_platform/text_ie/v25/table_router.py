from __future__ import annotations

import re

from equity_platform.documents.table_reconstruction import (
    TableReconstructionCandidate,
    reconstruct_flattened_table,
)

from ..model import TextBlock
from ..ontology import find_concepts


_NUMBER = re.compile(r"(?<![A-Za-z])[-(]?(?:\$\s*)?\d[\d,.]*(?:\s*%|\))?")
_PERIOD = re.compile(
    r"\b(?:Q[1-4]|FY\s?\d{2,4}|fiscal\s+20\d{2}|20\d{2}|"
    r"three[- ]month|six[- ]month|year[- ]to[- ]date)\b",
    re.IGNORECASE,
)
_GRID = re.compile(
    r"\b(?:change|as reported|adjusted|non-gaap|gaap|comparable|"
    r"dollars? in (?:millions|billions)|amounts in millions|"
    r"fiscal\s+20\d{2}|quarter ended|year ended)\b",
    re.IGNORECASE,
)
_TITLE = re.compile(
    r"\b(?:statements?|balance sheets?|cash flows?|reconciliation|results|"
    r"revenues?|net sales|operating income|operating margin|segments?)\b",
    re.IGNORECASE,
)


def route_financial_grid(block: TextBlock) -> TableReconstructionCandidate | None:
    existing = reconstruct_flattened_table(block)
    if existing is not None:
        return existing
    numeric = len(_NUMBER.findall(block.text))
    periods = tuple(dict.fromkeys(match.group(0) for match in _PERIOD.finditer(block.text)))
    concepts = tuple(dict.fromkeys(item.concept for item in find_concepts(block.text)))
    grid_cues = len(_GRID.findall(block.text))
    title_cues = len(_TITLE.findall(block.text))
    punctuation = len(re.findall(r"(?<!\d)[.!?](?!\d)", block.text))
    tokens = max(1, len(block.text.split()))
    low_sentence_density = punctuation / tokens < 0.015
    repeated_unchanged = len(re.findall(r"\bunchanged\b", block.text, re.I)) >= 2
    is_grid = (
        numeric >= 8
        and low_sentence_density
        and (len(periods) >= 2 or grid_cues >= 2)
        and (concepts or title_cues >= 2)
    ) or (
        numeric >= 12 and low_sentence_density and title_cues >= 1
    ) or (
        numeric >= 4 and repeated_unchanged and title_cues >= 1
    )
    if not is_grid:
        return None
    reasons = ["V25_LAYOUT_DENSITY"]
    if low_sentence_density:
        reasons.append("LOW_SENTENCE_PUNCTUATION")
    if periods:
        reasons.append("REPEATED_PERIOD_HEADERS")
    if grid_cues:
        reasons.append("COLUMN_HEADER_CUES")
    return TableReconstructionCandidate(
        sentence_index=block.sentence_index,
        char_start=block.char_start,
        char_end=block.char_end,
        source_literal=block.text,
        period_headers=periods,
        metric_labels=concepts,
        numeric_cells=numeric,
        reasons=tuple(reasons),
    )
