from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .authority import AuthorityLevel
from .fact import EvidenceStatus, FactOrigin, LineageRef, RelationType


class RoicKind(StrEnum):
    REPORTED = "REPORTED"
    INCREMENTAL = "INCREMENTAL"
    THROUGH_CYCLE = "THROUGH_CYCLE"
    FORWARD = "FORWARD"
    TERMINAL = "TERMINAL"
    MARKET_IMPLIED = "MARKET_IMPLIED"


@dataclass(frozen=True)
class EconomicNodeIR:
    node_id: str
    entity: str
    concept: str
    scope: str
    period: str
    unit: str
    value: float | None
    origin: FactOrigin
    relation: RelationType
    evidence: EvidenceStatus
    authority: AuthorityLevel
    lineage: tuple[LineageRef, ...] = ()
    roic_kind: RoicKind | None = None

    def __post_init__(self) -> None:
        if self.concept == "ROIC" and self.roic_kind is None:
            raise ValueError("ROIC nodes require an explicit RoicKind")
        if self.concept != "ROIC" and self.roic_kind is not None:
            raise ValueError("RoicKind is only valid for ROIC nodes")


@dataclass(frozen=True)
class EconomicEdgeIR:
    edge_id: str
    inputs: tuple[str, ...]
    output: str
    relation: RelationType
    formula_id: str | None = None

    def __post_init__(self) -> None:
        if not self.inputs or not self.output:
            raise ValueError("Economic edges require inputs and an output")
        if self.relation in {RelationType.IDENTITY, RelationType.ACCOUNTING}:
            if not self.formula_id:
                raise ValueError("Identity/accounting edges require a formula_id")


@dataclass(frozen=True)
class EconomicGraphIR:
    nodes: tuple[EconomicNodeIR, ...]
    edges: tuple[EconomicEdgeIR, ...]

    def validate(self) -> None:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("EconomicGraphIR node ids must be unique")
        known = set(node_ids)
        for edge in self.edges:
            missing = (set(edge.inputs) | {edge.output}) - known
            if missing:
                raise ValueError(f"Economic edge {edge.edge_id} has unknown nodes: {missing}")
