import pytest

from equity_platform.text_ie.llm import (
    LLMFallbackPolicy,
    LLMFallbackSignals,
    LLMFallbackTier,
)


def test_easy_high_confidence_clause_does_not_call_an_llm() -> None:
    decision = LLMFallbackPolicy().route(LLMFallbackSignals(
        binding_confidence=0.99,
        role_confidence=0.99,
    ))

    assert decision.tier is LLMFallbackTier.NONE
    assert decision.reasons == ()


def test_low_confidence_or_unknown_kpi_routes_to_fast_structured_fallback() -> None:
    decision = LLMFallbackPolicy().route(LLMFallbackSignals(
        unknown_kpi=True,
        binding_confidence=0.70,
        role_confidence=0.95,
    ))

    assert decision.tier is LLMFallbackTier.FAST_STRUCTURED
    assert set(decision.reasons) == {"UNKNOWN_KPI", "LOW_BINDING_CONFIDENCE"}
    assert decision.provider is None
    assert decision.model_id is None


def test_cross_sentence_or_complex_guidance_routes_to_deep_reasoning() -> None:
    decision = LLMFallbackPolicy().route(LLMFallbackSignals(
        binding_confidence=0.95,
        role_confidence=0.95,
        complex_guidance=True,
        cross_sentence_relation=True,
    ))

    assert decision.tier is LLMFallbackTier.DEEP_REASONING
    assert set(decision.reasons) == {"COMPLEX_GUIDANCE", "CROSS_SENTENCE_RELATION"}


def test_fallback_confidence_is_validated() -> None:
    with pytest.raises(ValueError, match="confidence"):
        LLMFallbackSignals(binding_confidence=1.1, role_confidence=0.9)
