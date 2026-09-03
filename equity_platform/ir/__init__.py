"""Canonical, sector-neutral intermediate representations."""

from .authority import (
    AuthorityLevel,
    AuthorityViolation,
    DataAuthority,
    DriverRole,
    ForecastAuthority,
    require_authority,
)
from .causal import (
    CausalEdgeIR,
    Direction,
    Falsifier,
    IdentificationStatus,
    LagSpec,
    MagnitudeSpec,
)
from .economic import EconomicEdgeIR, EconomicGraphIR, EconomicNodeIR, RoicKind
from .bundle import ResearchGraphIR
from .evidence import (
    ClaimStatus,
    ClaimType,
    EvidenceClaimIR,
    ExtractionMethod,
    SourceSpan,
)
from .fact import (
    EvidenceStatus,
    FactIR,
    FactOrigin,
    LineageRef,
    RelationType,
    SourceRef,
)
from .scenario import (
    ExpectationsGapIR,
    IdentificationState,
    ScenarioClass,
    ScenarioIR,
)
from .sensor import SensorIR, SensorTransform

__all__ = [
    "AuthorityLevel",
    "AuthorityViolation",
    "DataAuthority",
    "DriverRole",
    "ForecastAuthority",
    "require_authority",
    "CausalEdgeIR",
    "Direction",
    "Falsifier",
    "IdentificationStatus",
    "LagSpec",
    "MagnitudeSpec",
    "EconomicEdgeIR",
    "EconomicGraphIR",
    "EconomicNodeIR",
    "RoicKind",
    "ResearchGraphIR",
    "ClaimStatus",
    "ClaimType",
    "EvidenceClaimIR",
    "ExtractionMethod",
    "SourceSpan",
    "EvidenceStatus",
    "FactIR",
    "FactOrigin",
    "LineageRef",
    "RelationType",
    "SourceRef",
    "SensorIR",
    "SensorTransform",
    "ScenarioClass",
    "ScenarioIR",
    "IdentificationState",
    "ExpectationsGapIR",
]
