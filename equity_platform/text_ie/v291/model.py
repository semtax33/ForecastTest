from __future__ import annotations

from dataclasses import dataclass

from ..model import ConceptMention, KPIFrame, QuantityMention
from ..v26 import V26ExtractionResult


@dataclass(frozen=True)
class QuantityBindingEdge:
    concept: str
    quantity: QuantityMention
    concept_char_start: int
    concept_char_end: int


@dataclass(frozen=True)
class QuantityRoleEdge:
    concept: str
    role: str
    quantity: QuantityMention
    concept_char_start: int
    concept_char_end: int


@dataclass(frozen=True)
class ClauseSemanticTrace:
    block_char_start: int
    block_char_end: int
    clause_char_start: int
    clause_char_end: int
    candidate_ids: tuple[str, ...]
    concepts: tuple[ConceptMention, ...]
    quantities: tuple[QuantityMention, ...]
    bindings: tuple[QuantityBindingEdge, ...]
    roles: tuple[QuantityRoleEdge, ...]
    unresolved_bindings: tuple[QuantityBindingEdge, ...]
    reduced_frames: tuple[KPIFrame, ...]
    adjudicated: bool
    primary_root_cause: str


@dataclass(frozen=True)
class DocumentSemanticTelemetry:
    clauses: tuple[ClauseSemanticTrace, ...]
    role_inference_stage: str = "PRE_REDUCER"


@dataclass(frozen=True)
class V291ExtractionResult:
    base: V26ExtractionResult
    telemetry: DocumentSemanticTelemetry

    @property
    def extraction(self):
        return self.base.extraction

    @property
    def candidates(self):
        return self.base.candidates

    @property
    def bindings(self):
        return self.base.bindings

    @property
    def table_routes(self):
        return self.base.table_routes

    @property
    def routed_blocks(self):
        return self.base.routed_blocks

    @property
    def changes(self):
        return self.base.changes

    @property
    def comparisons(self):
        return self.base.comparisons

    @property
    def rejections(self):
        return self.base.rejections
