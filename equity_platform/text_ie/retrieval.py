from __future__ import annotations

from dataclasses import dataclass

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
    if table_markers >= 2 and numeric_tokens > 30:
        return CandidateDecision(False, "FINANCIAL_TABLE_MARKERS")
    if len(block.text.split()) > 180 and sum(char.isdigit() for char in block.text) > 80:
        return CandidateDecision(False, "TABLE_LIKE_TOKEN_DENSITY")
    return CandidateDecision(True, "NARRATIVE_CANDIDATE")
