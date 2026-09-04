from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..model import KPIFrame, QuantityMention, SemanticFrame, TextBlock, TextExtractionResult


class CandidateOrigin(StrEnum):
    TOKEN_WINDOW = "TOKEN_WINDOW"
    SENTENCE_WINDOW = "SENTENCE_WINDOW"
    PUNCTUATION_PATTERN = "PUNCTUATION_PATTERN"
    HEADING_INHERITANCE = "HEADING_INHERITANCE"
    INLINE_XBRL = "INLINE_XBRL"
    DEPENDENCY = "DEPENDENCY"


@dataclass(frozen=True)
class MetricAnchor:
    concept: str
    alias: str
    char_start: int
    char_end: int
    inherited_from: str | None = None


@dataclass(frozen=True)
class RecallCandidate:
    candidate_id: str
    block: TextBlock
    metric: MetricAnchor
    quantities: tuple[QuantityMention, ...]
    origins: tuple[CandidateOrigin, ...]
    rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class BoundFrameCandidate:
    candidate_id: str
    block: TextBlock
    metric: MetricAnchor
    frame: SemanticFrame
    output_concept: str
    value: QuantityMention | None
    lower_value: float | None
    upper_value: float | None
    relation_evidence: str
    relation_start: int
    relation_end: int
    origins: tuple[CandidateOrigin, ...]
    rule_id: str
    relation_group: str | None = None
    proposed_by_llm: bool = False


@dataclass(frozen=True)
class VerificationDecision:
    candidate: BoundFrameCandidate
    accepted: bool
    reason: str
    failure_class: str
    frame: KPIFrame | None = None


@dataclass(frozen=True)
class HighRecallExtractionResult:
    extraction: TextExtractionResult
    candidates: tuple[RecallCandidate, ...]
    bindings: tuple[BoundFrameCandidate, ...]
    verification: tuple[VerificationDecision, ...]
    table_routes: tuple[object, ...]
