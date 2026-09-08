from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LLMFallbackTier(StrEnum):
    NONE = "NONE"
    FAST_STRUCTURED = "FAST_STRUCTURED"
    DEEP_REASONING = "DEEP_REASONING"


@dataclass(frozen=True)
class LLMFallbackSignals:
    binding_confidence: float
    role_confidence: float
    unknown_kpi: bool = False
    competing_quantities: bool = False
    complex_guidance: bool = False
    cross_sentence_relation: bool = False

    def __post_init__(self) -> None:
        if any(
            not 0.0 <= confidence <= 1.0
            for confidence in (self.binding_confidence, self.role_confidence)
        ):
            raise ValueError("fallback confidence must be within [0, 1]")


@dataclass(frozen=True)
class LLMFallbackDecision:
    tier: LLMFallbackTier
    reasons: tuple[str, ...]
    # Provider/model selection belongs to deployment configuration.  Keeping
    # these unset prevents research policy from coupling to a vendor name.
    provider: str | None = None
    model_id: str | None = None


@dataclass(frozen=True)
class LLMFallbackPolicy:
    binding_threshold: float = 0.90
    role_threshold: float = 0.90

    def __post_init__(self) -> None:
        if any(
            not 0.0 <= threshold <= 1.0
            for threshold in (self.binding_threshold, self.role_threshold)
        ):
            raise ValueError("fallback thresholds must be within [0, 1]")

    def route(self, signals: LLMFallbackSignals) -> LLMFallbackDecision:
        reasons = []
        if signals.unknown_kpi:
            reasons.append("UNKNOWN_KPI")
        if signals.binding_confidence < self.binding_threshold:
            reasons.append("LOW_BINDING_CONFIDENCE")
        if signals.role_confidence < self.role_threshold:
            reasons.append("LOW_ROLE_CONFIDENCE")
        if signals.competing_quantities:
            reasons.append("COMPETING_QUANTITIES")
        if signals.complex_guidance:
            reasons.append("COMPLEX_GUIDANCE")
        if signals.cross_sentence_relation:
            reasons.append("CROSS_SENTENCE_RELATION")
        if signals.complex_guidance or signals.cross_sentence_relation:
            tier = LLMFallbackTier.DEEP_REASONING
        elif reasons:
            tier = LLMFallbackTier.FAST_STRUCTURED
        else:
            tier = LLMFallbackTier.NONE
        return LLMFallbackDecision(tier=tier, reasons=tuple(reasons))


__all__ = [
    "LLMFallbackDecision",
    "LLMFallbackPolicy",
    "LLMFallbackSignals",
    "LLMFallbackTier",
]
