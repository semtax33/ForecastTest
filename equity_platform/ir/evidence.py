from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .authority import AuthorityLevel
from .fact import SourceRef


class ClaimType(StrEnum):
    GUIDANCE = "GUIDANCE"
    CAUSAL_MECHANISM = "CAUSAL_MECHANISM"
    OPERATIONAL_EVENT = "OPERATIONAL_EVENT"
    COST_PRESSURE = "COST_PRESSURE"
    PRICE_ACTION = "PRICE_ACTION"
    CAPITAL_ALLOCATION = "CAPITAL_ALLOCATION"
    COMPETITIVE_ADVANTAGE = "COMPETITIVE_ADVANTAGE"
    RISK = "RISK"
    ACCOUNTING_SEMANTICS = "ACCOUNTING_SEMANTICS"
    MANAGEMENT_INTENT = "MANAGEMENT_INTENT"
    CUSTOMER_DEMAND = "CUSTOMER_DEMAND"
    SUPPLY_CONSTRAINT = "SUPPLY_CONSTRAINT"
    PROGRAM_EVENT = "PROGRAM_EVENT"
    THESIS_EVIDENCE = "THESIS_EVIDENCE"


class ClaimStatus(StrEnum):
    PROPOSED = "PROPOSED"
    VERIFIED = "VERIFIED"
    CORROBORATED = "CORROBORATED"
    CONTRADICTED = "CONTRADICTED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    RESOLVED = "RESOLVED"
    REJECTED_UNSUPPORTED = "REJECTED_UNSUPPORTED"


class ExtractionMethod(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    INLINE_XBRL = "INLINE_XBRL"
    REGEX = "REGEX"
    SPAN_RULE = "SPAN_RULE"
    DEPENDENCY_RULE = "DEPENDENCY_RULE"
    CONTEXT_RULE = "CONTEXT_RULE"
    LEARNED_IE = "LEARNED_IE"
    LLM = "LLM"
    HUMAN = "HUMAN"


@dataclass(frozen=True)
class SourceSpan:
    section: str | None
    char_start: int
    char_end: int
    literal: str

    def __post_init__(self) -> None:
        if self.char_start < 0 or self.char_end <= self.char_start or not self.literal:
            raise ValueError("Evidence claims require a non-empty, ordered source span")


@dataclass(frozen=True)
class EvidenceClaimIR:
    claim_id: str
    entity: str
    scope: str
    period: str | None
    claim_type: ClaimType
    subject: str
    predicate: str
    direction: str | None
    source: SourceRef
    source_span: SourceSpan
    status: ClaimStatus
    authority: AuthorityLevel
    extraction_method: ExtractionMethod = ExtractionMethod.DETERMINISTIC
    verified_by: str | None = None

    def __post_init__(self) -> None:
        if self.authority >= AuthorityLevel.VALUATION_INPUT:
            raise ValueError("Narrative claims cannot directly receive valuation authority")
        if (
            self.extraction_method is ExtractionMethod.LLM
            and self.status is not ClaimStatus.PROPOSED
            and not self.verified_by
        ):
            raise ValueError("LLM claims need an explicit verifier before lifecycle promotion")
