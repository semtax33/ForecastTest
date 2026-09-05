from __future__ import annotations

from dataclasses import dataclass, field

from .ontology import definition_for
from .role_graph import SemanticRole
from .semantic_challenger import (
    SemanticChallenger,
    SemanticChallengerUnavailableError,
    SemanticPairRequest,
    SemanticScore,
    SemanticTask,
)


_BINDING_LABELS = {"BELONGS_TO", "NOT_RELATED"}
_ROLE_LABELS = {role.value for role in SemanticRole}


@dataclass(frozen=True)
class SemanticScoreRejection:
    request_id: str
    task: SemanticTask
    reason: str
    score: SemanticScore


@dataclass(frozen=True)
class HybridSemanticResult:
    accepted_scores: tuple[SemanticScore, ...]
    rejections: tuple[SemanticScoreRejection, ...]
    challenger_name: str
    device: str
    status: str = "SCORED"
    diagnostic: str | None = None
    research_facts: tuple[()] = field(default=(), init=False)


class HybridSemanticEngine:
    """Validate learned semantic scores without materializing KPI frames."""

    def __init__(
        self,
        challenger: SemanticChallenger,
        *,
        minimum_confidence: float = 0.99,
    ) -> None:
        if not 0.0 < minimum_confidence <= 1.0:
            raise ValueError("minimum confidence must be in (0, 1]")
        self._challenger = challenger
        self._minimum_confidence = minimum_confidence

    @staticmethod
    def _label_allowed(score: SemanticScore) -> bool:
        if score.task is SemanticTask.BINDING:
            return score.label in _BINDING_LABELS
        if score.task is SemanticTask.ROLE:
            return score.label in _ROLE_LABELS
        try:
            definition_for(score.label)
            return True
        except KeyError:
            return False

    def challenge(
        self,
        requests: tuple[SemanticPairRequest, ...],
    ) -> HybridSemanticResult:
        by_id = {request.request_id: request for request in requests}
        if len(by_id) != len(requests):
            raise ValueError("semantic request ids must be unique")
        accepted = []
        rejected = []
        seen = set()
        try:
            challenger_scores = self._challenger.score(requests)
        except SemanticChallengerUnavailableError as exc:
            return HybridSemanticResult(
                accepted_scores=(),
                rejections=(),
                challenger_name=self._challenger.name,
                device=self._challenger.device,
                status="CHALLENGER_UNAVAILABLE",
                diagnostic=str(exc),
            )
        for score in challenger_scores:
            request = by_id.get(score.request_id)
            reason = None
            signature = (score.request_id, score.task)
            if request is None:
                reason = "UNKNOWN_REQUEST"
            elif signature in seen:
                reason = "DUPLICATE_TASK_SCORE"
            elif (
                score.source_sha256 != request.source_sha256
                or score.metric_char_start != request.metric_char_start
                or score.metric_char_end != request.metric_char_end
                or score.quantity_char_start != request.quantity_char_start
                or score.quantity_char_end != request.quantity_char_end
            ):
                reason = "SOURCE_SPAN_MISMATCH"
            elif score.confidence < self._minimum_confidence:
                reason = "LOW_CONFIDENCE"
            elif not self._label_allowed(score):
                reason = "UNSUPPORTED_LABEL"
            if reason is None:
                accepted.append(score)
                seen.add(signature)
            else:
                rejected.append(SemanticScoreRejection(
                    request_id=score.request_id,
                    task=score.task,
                    reason=reason,
                    score=score,
                ))
        return HybridSemanticResult(
            accepted_scores=tuple(accepted),
            rejections=tuple(rejected),
            challenger_name=self._challenger.name,
            device=self._challenger.device,
        )


__all__ = [
    "HybridSemanticEngine",
    "HybridSemanticResult",
    "SemanticScoreRejection",
]
