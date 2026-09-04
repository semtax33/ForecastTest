from __future__ import annotations

from dataclasses import dataclass
import re

from .model import TextBlock


@dataclass(frozen=True)
class CandidateDecision:
    accepted: bool
    reason: str


def narrative_candidate(block: TextBlock) -> CandidateDecision:
    """Keep prose-like blocks; dense tables belong to the table DSL."""

    if len(block.text) > 1_500:
        return CandidateDecision(False, "BLOCK_TOO_LONG_FOR_SENTENCE_IE")
    if block.text.count("$") >= 8 or block.text.count("%") >= 8:
        return CandidateDecision(False, "TABLE_LIKE_NUMERIC_DENSITY")
    folded = block.text.casefold()
    table_markers = sum(
        marker in folded
        for marker in (
            "three months ended",
            "six months ended",
            "quarters ended",
            "in millions",
            "unaudited",
            "$ change % change",
        )
    )
    numeric_tokens = sum(char.isdigit() for char in block.text)
    numeric_groups = len(re.findall(r"(?<![A-Za-z])[-(]?\d[\d,.]*(?:\))?", block.text))
    if (
        numeric_groups >= 12
        and numeric_tokens > 30
        and any(
            marker in folded
            for marker in (
                "financial results summary",
                "in millions of dollars",
                "in millions, except",
                "earnings per share",
                "cash flow from operations",
            )
        )
    ):
        return CandidateDecision(False, "TABULAR_HEADER_AND_NUMERIC_DENSITY")
    if table_markers >= 2 and numeric_tokens > 30:
        return CandidateDecision(False, "FINANCIAL_TABLE_MARKERS")
    if len(block.text.split()) > 180 and sum(char.isdigit() for char in block.text) > 80:
        return CandidateDecision(False, "TABLE_LIKE_TOKEN_DENSITY")
    return CandidateDecision(True, "NARRATIVE_CANDIDATE")
