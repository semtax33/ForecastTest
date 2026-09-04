from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..model import KPIFrame, QuantityMention, TextBlock, TextExtractionResult
from ..v24.model import RecallCandidate


class Role(StrEnum):
    LEVEL = "LEVEL"
    DELTA = "DELTA"


@dataclass(frozen=True)
class ClauseSpan:
    block: TextBlock
    char_start: int
    char_end: int
    text: str


@dataclass(frozen=True)
class TypedRoleCandidate:
    candidate: RecallCandidate
    clause: ClauseSpan
    role: Role
    quantity: QuantityMention
    trigger: str
    trigger_start: int
    direction: int
    eligible: bool
    eligibility_reason: str
    score: float


@dataclass(frozen=True)
class CanonicalBinding:
    candidate: RecallCandidate
    clause: ClauseSpan
    level: QuantityMention | None
    delta: QuantityMention | None
    direction: int
    score: float
    ambiguity_margin: float
    status: str
    reason: str


@dataclass(frozen=True)
class V25ExtractionResult:
    extraction: TextExtractionResult
    candidates: tuple[RecallCandidate, ...]
    role_candidates: tuple[TypedRoleCandidate, ...]
    bindings: tuple[CanonicalBinding, ...]
    table_routes: tuple[object, ...]
    suppressed_duplicate_count: int
    conflict_count: int
