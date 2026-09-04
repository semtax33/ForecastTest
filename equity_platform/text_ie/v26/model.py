from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..model import KPIFrame, QuantityMention, SourceSpan, TextExtractionResult


class EvidenceRoute(StrEnum):
    TEXT_BINDING = "TEXT_BINDING"
    TABLE_BINDING = "TABLE_BINDING"
    XBRL_DIRECT = "XBRL_DIRECT"
    ADJUDICATED_DIRECT = "ADJUDICATED_DIRECT"


@dataclass(frozen=True)
class RouteBindingEvidence:
    route: EvidenceRoute
    frame: KPIFrame
    upstream_candidate_id: str | None
    verifier: str


@dataclass(frozen=True)
class RouteRejection:
    candidate_id: str
    primary_root_cause: str
    secondary_reasons: tuple[str, ...]


@dataclass(frozen=True)
class KPIChange:
    """One canonical economic change event before KPIFrame materialization."""

    candidate_id: str
    concept: str
    level: QuantityMention | None
    delta: QuantityMention | None
    direction: int
    source_span: SourceSpan


@dataclass(frozen=True)
class ComparisonFrame:
    """Ordered current/prior comparison preserved as one semantic object."""

    candidate_id: str
    concept: str
    current_values: tuple[QuantityMention, ...]
    prior_values: tuple[QuantityMention, ...]
    source_span: SourceSpan


@dataclass(frozen=True)
class V26ExtractionResult:
    extraction: TextExtractionResult
    candidates: tuple[object, ...]
    bindings: tuple[RouteBindingEvidence, ...]
    table_routes: tuple[object, ...]
    routed_blocks: tuple[object, ...]
    changes: tuple[KPIChange, ...]
    comparisons: tuple[ComparisonFrame, ...]
    rejections: tuple[RouteRejection, ...]
