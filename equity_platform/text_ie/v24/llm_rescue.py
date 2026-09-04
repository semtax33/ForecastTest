from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from ..model import SemanticFrame, TextBlock
from .model import BoundFrameCandidate, RecallCandidate


@dataclass(frozen=True)
class LLMRoleProposal:
    candidate_id: str
    concept: str
    frame: SemanticFrame
    metric_literal: str
    value_literal: str | None
    relation_literal: str


class AbstentionRescueBackend(Protocol):
    def propose(
        self,
        block: TextBlock,
        candidates: tuple[RecallCandidate, ...],
    ) -> tuple[LLMRoleProposal, ...]: ...


def ground_llm_proposals(
    proposals: tuple[LLMRoleProposal, ...],
    candidates: tuple[RecallCandidate, ...],
) -> tuple[BoundFrameCandidate, ...]:
    """Ground LLM role proposals in existing deterministic candidates only."""

    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    grounded: list[BoundFrameCandidate] = []
    for proposal in proposals:
        candidate = by_id.get(proposal.candidate_id)
        if candidate is None or candidate.metric.concept != proposal.concept:
            continue
        text = candidate.block.text
        if candidate.metric.alias != proposal.metric_literal:
            continue
        relation_start = text.find(proposal.relation_literal)
        if relation_start < 0:
            continue
        value = None
        if proposal.value_literal is not None:
            matches = [
                quantity
                for quantity in candidate.quantities
                if quantity.raw == proposal.value_literal
            ]
            if len(matches) != 1:
                continue
            value = matches[0]
        output_concept = proposal.concept
        if proposal.frame is SemanticFrame.CHANGE_BY:
            output_concept += "_CHANGE"
        grounded.append(
            BoundFrameCandidate(
                candidate_id=candidate.candidate_id,
                block=candidate.block,
                metric=candidate.metric,
                frame=proposal.frame,
                output_concept=output_concept,
                value=value,
                lower_value=None,
                upper_value=None,
                relation_evidence=proposal.relation_literal,
                relation_start=relation_start,
                relation_end=relation_start + len(proposal.relation_literal),
                origins=candidate.origins,
                rule_id="v24.llm_abstention_rescue",
                proposed_by_llm=True,
            )
        )
    return tuple(grounded)
