from __future__ import annotations

from equity_platform.text_ie.semantic_challenger import (
    SemanticChallengerUnavailableError,
    SemanticPairRequest,
    SemanticScore,
    SemanticTask,
)
from equity_platform.text_ie.semantic_engine import HybridSemanticEngine


class _HighConfidenceChallenger:
    name = "TEST_CHALLENGER"
    device = "cuda"

    def score(self, requests):
        request = requests[0]
        common = {
            "request_id": request.request_id,
            "source_sha256": request.source_sha256,
            "metric_char_start": request.metric_char_start,
            "metric_char_end": request.metric_char_end,
            "quantity_char_start": request.quantity_char_start,
            "quantity_char_end": request.quantity_char_end,
            "model_id": "test/checkpoint",
            "device": self.device,
        }
        return (
            SemanticScore(task=SemanticTask.CONCEPT, label="REVENUE", confidence=0.999, **common),
            SemanticScore(task=SemanticTask.BINDING, label="BELONGS_TO", confidence=0.999, **common),
            SemanticScore(task=SemanticTask.ROLE, label="DELTA", confidence=0.999, **common),
        )


class _UnavailableChallenger:
    name = "UNAVAILABLE_TEST_CHALLENGER"
    device = "cuda:pending"

    def score(self, requests):
        raise SemanticChallengerUnavailableError("checkpoint is offline")


def test_hybrid_engine_accepts_scores_but_never_emits_facts() -> None:
    text = "Revenue increased by 10%."
    request = SemanticPairRequest(
        request_id="pair-1",
        source_sha256="a" * 64,
        context=text,
        metric_char_start=0,
        metric_char_end=7,
        quantity_char_start=21,
        quantity_char_end=24,
    )
    assert request.metric_marked_context == "[METRIC]Revenue[/METRIC] increased by 10%."

    result = HybridSemanticEngine(_HighConfidenceChallenger()).challenge((request,))

    assert {(item.task, item.label) for item in result.accepted_scores} == {
        (SemanticTask.CONCEPT, "REVENUE"),
        (SemanticTask.BINDING, "BELONGS_TO"),
        (SemanticTask.ROLE, "DELTA"),
    }
    assert result.rejections == ()
    assert result.research_facts == ()
    assert result.status == "SCORED"


def test_hybrid_engine_abstains_when_challenger_is_unavailable() -> None:
    text = "Revenue was $10 million."
    request = SemanticPairRequest(
        request_id="pair-1",
        source_sha256="a" * 64,
        context=text,
        metric_char_start=0,
        metric_char_end=7,
        quantity_char_start=12,
        quantity_char_end=23,
    )

    result = HybridSemanticEngine(_UnavailableChallenger()).challenge((request,))

    assert result.status == "CHALLENGER_UNAVAILABLE"
    assert result.diagnostic == "checkpoint is offline"
    assert result.accepted_scores == ()
    assert result.research_facts == ()
