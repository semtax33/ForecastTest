from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

from equity_platform.ir import (
    AuthorityLevel,
    EvidenceClaimIR,
    ExtractionMethod,
    FactIR,
    SourceRef,
    SourceSpan,
)


class SemanticFrame(StrEnum):
    ABSOLUTE_VALUE = "ABSOLUTE_VALUE"
    CHANGE_TO = "CHANGE_TO"
    CHANGE_BY = "CHANGE_BY"
    COMPOSITION = "COMPOSITION"
    RANGE_GUIDANCE = "RANGE_GUIDANCE"
    COUNT_ACTIVITY = "COUNT_ACTIVITY"
    RATE = "RATE"
    NOT_EXPECTED = "NOT_EXPECTED"
    CAUSE_EFFECT = "CAUSE_EFFECT"
    COMPARATIVE = "COMPARATIVE"


class PeriodSemantics(StrEnum):
    DOCUMENT_PERIOD = "DOCUMENT_PERIOD"
    END_OF_PERIOD = "END_OF_PERIOD"
    DURATION = "DURATION"
    FORECAST = "FORECAST"


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"
    PROPOSED = "PROPOSED"


class AmbiguityPolicy(StrEnum):
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    SKIP = "SKIP"


class FactTier(StrEnum):
    CRITICAL = "CRITICAL"
    NARRATIVE = "NARRATIVE"


class EmissionStatus(StrEnum):
    AUTO_EMITTED = "AUTO_EMITTED"
    REVIEW = "REVIEW"
    ABSTAINED = "ABSTAINED"


class QuantityKind(StrEnum):
    MONEY = "MONEY"
    PRICE = "PRICE"
    PERCENT = "PERCENT"
    BASIS_POINTS = "BASIS_POINTS"
    COUNT = "COUNT"
    RATE = "RATE"


@dataclass(frozen=True)
class Polarity:
    positive: bool
    cue: str | None = None
    cue_start: int | None = None
    cue_end: int | None = None


@dataclass(frozen=True)
class Qualifier:
    approximation: bool = False
    forward_looking: bool = False
    lower_bound: bool = False
    upper_bound: bool = False
    materiality: bool = False
    cues: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuantityMention:
    kind: QuantityKind
    value: float
    unit: str
    raw: str
    char_start: int
    char_end: int

    def __post_init__(self) -> None:
        if not isfinite(self.value):
            raise ValueError("QuantityMention.value must be finite")
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError("QuantityMention requires an ordered source span")


@dataclass(frozen=True)
class ConceptMention:
    concept: str
    alias: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class TextBlock:
    entity: str
    text: str
    source: SourceRef
    sentence_index: int
    char_start: int
    char_end: int
    document_period: str | None
    section: str | None = None
    subsection: str | None = None
    nearest_heading: str | None = None
    previous_sentence: str | None = None
    next_sentence: str | None = None
    inline_fact_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class KPIFrame:
    concept: str
    entity: str
    scope: str
    period: str
    period_semantics: PeriodSemantics
    frame: SemanticFrame
    value: float | None
    unit: str | None
    change: float | None
    change_unit: str | None
    comparator: str | None
    polarity: Polarity
    qualifier: Qualifier
    source: SourceRef
    source_span: SourceSpan
    extraction_method: ExtractionMethod
    rule_id: str
    rule_version: int
    extraction_confidence: float
    authority: AuthorityLevel
    verification_status: VerificationStatus
    lower_value: float | None = None
    upper_value: float | None = None
    context_trace: dict[str, object] = field(default_factory=dict)
    verified_by: str | None = None
    tier: FactTier = FactTier.CRITICAL
    emission_status: EmissionStatus = EmissionStatus.AUTO_EMITTED

    def __post_init__(self) -> None:
        if not self.concept or not self.entity or not self.scope or not self.period:
            raise ValueError("KPIFrame identity fields must not be blank")
        if not 0.0 <= self.extraction_confidence <= 1.0:
            raise ValueError("extraction_confidence must be between zero and one")
        for value in (self.value, self.change, self.lower_value, self.upper_value):
            if value is not None and not isfinite(value):
                raise ValueError("KPIFrame numeric fields must be finite")
        if self.authority >= AuthorityLevel.TERMINAL_INPUT:
            raise ValueError("Text extraction cannot directly create terminal authority")
        if self.rule_version < 1:
            raise ValueError("KPIFrame requires a positive rule version")


@dataclass(frozen=True)
class ReviewItem:
    sentence_index: int
    rule_id: str
    status: str
    reason: str
    source_span: SourceSpan
    candidates: tuple[str, ...] = ()
    tier: FactTier = FactTier.CRITICAL


@dataclass(frozen=True)
class AbstentionItem:
    sentence_index: int
    rule_id: str
    reason: str
    failure_class: str
    source_span: SourceSpan
    tier: FactTier
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class KPIRelationIR:
    cause: str
    effect: str
    relation_type: str
    direction: str
    source: SourceRef
    source_span: SourceSpan
    rule_id: str
    rule_version: int
    extraction_confidence: float
    authority: AuthorityLevel
    verification_status: VerificationStatus

    def __post_init__(self) -> None:
        if not self.cause or not self.effect or self.cause == self.effect:
            raise ValueError("KPI relations require distinct cause and effect concepts")
        if self.authority >= AuthorityLevel.VALUATION_INPUT:
            raise ValueError("Extracted relations cannot directly receive valuation authority")
        if not 0.0 <= self.extraction_confidence <= 1.0:
            raise ValueError("Relation extraction confidence must be between zero and one")


@dataclass(frozen=True)
class TextExtractionResult:
    frames: tuple[KPIFrame, ...]
    facts: tuple[FactIR, ...]
    evidence_claims: tuple[EvidenceClaimIR, ...]
    relations: tuple[KPIRelationIR, ...]
    reviews: tuple[ReviewItem, ...]
    abstentions: tuple[AbstentionItem, ...]
    backend_name: str
