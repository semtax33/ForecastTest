from __future__ import annotations

from dataclasses import dataclass

from .causal import CausalEdgeIR
from .economic import EconomicGraphIR
from .evidence import EvidenceClaimIR
from .fact import FactIR
from .scenario import ExpectationsGapIR, ScenarioIR
from .sensor import SensorIR


@dataclass(frozen=True)
class ResearchGraphIR:
    facts: tuple[FactIR, ...]
    sensors: tuple[SensorIR, ...]
    evidence_claims: tuple[EvidenceClaimIR, ...]
    causal_edges: tuple[CausalEdgeIR, ...]
    economic_graph: EconomicGraphIR
    scenarios: tuple[ScenarioIR, ...] = ()
    expectations_gaps: tuple[ExpectationsGapIR, ...] = ()

    def validate(self) -> None:
        self.economic_graph.validate()
        claim_ids = {claim.claim_id for claim in self.evidence_claims}
        if len(claim_ids) != len(self.evidence_claims):
            raise ValueError("Evidence claim ids must be unique")
        for edge in self.causal_edges:
            unknown = (
                set(edge.supporting_evidence) | set(edge.contradicting_evidence)
            ) - claim_ids
            if unknown:
                raise ValueError(f"Causal edge {edge.edge_id} has unknown evidence: {unknown}")
        scenario_ids = {scenario.scenario_id for scenario in self.scenarios}
        if len(scenario_ids) != len(self.scenarios):
            raise ValueError("Scenario ids must be unique")
        node_ids = {node.node_id for node in self.economic_graph.nodes}
        for scenario in self.scenarios:
            unknown_nodes = set(scenario.assumption_nodes) - node_ids
            unknown_claims = set(scenario.evidence_claims) - claim_ids
            if unknown_nodes or unknown_claims:
                raise ValueError(
                    f"Scenario {scenario.scenario_id} has unknown references: "
                    f"nodes={unknown_nodes}, claims={unknown_claims}"
                )
        for gap in self.expectations_gaps:
            unknown = {gap.model_node, gap.market_implied_node} - node_ids
            if unknown:
                raise ValueError(f"Expectations gap {gap.gap_id} has unknown nodes: {unknown}")
