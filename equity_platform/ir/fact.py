from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Mapping

from .authority import AuthorityLevel


class FactOrigin(StrEnum):
    OBSERVED = "OBSERVED"
    FORECAST = "FORECAST"
    ASSUMPTION = "ASSUMPTION"
    MARKET_IMPLIED = "MARKET_IMPLIED"
    DERIVED = "DERIVED"


class RelationType(StrEnum):
    IDENTITY = "IDENTITY"
    ACCOUNTING = "ACCOUNTING"
    STRUCTURAL = "STRUCTURAL"
    STATISTICAL = "STATISTICAL"
    HYPOTHESIS = "HYPOTHESIS"
    MANAGEMENT_CAUSAL_CLAIM = "MANAGEMENT_CAUSAL_CLAIM"
    MARKET_IMPLIED = "MARKET_IMPLIED"


class EvidenceStatus(StrEnum):
    HISTORICAL = "HISTORICAL"
    PIT = "PIT"
    OOS_VALIDATED = "OOS_VALIDATED"
    DIAGNOSTIC = "DIAGNOSTIC"
    PROPOSED = "PROPOSED"


@dataclass(frozen=True)
class SourceRef:
    source_type: str
    uri: str
    local_path: str
    sha256: str
    available_at: str
    location: str | None = None

    def __post_init__(self) -> None:
        if len(self.sha256) != 64:
            raise ValueError("SourceRef.sha256 must be a SHA-256 hex digest")


@dataclass(frozen=True)
class LineageRef:
    rule_id: str
    rule_version: int
    match_trace: Mapping[str, object] = field(default_factory=dict)
    capture_trace: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rule_id or self.rule_version < 1:
            raise ValueError("Lineage requires a rule id and positive version")


@dataclass(frozen=True)
class FactIR:
    entity: str
    metric: str
    scope: str
    period: str
    unit: str
    value: float
    origin: FactOrigin
    relation: RelationType
    evidence: EvidenceStatus
    authority: AuthorityLevel
    source: SourceRef
    lineage: LineageRef

    def __post_init__(self) -> None:
        material = (self.entity, self.metric, self.scope, self.period, self.unit)
        if not all(str(item).strip() for item in material):
            raise ValueError("FactIR identity fields must not be blank")
        if not isfinite(float(self.value)):
            raise ValueError("FactIR.value must be finite")
