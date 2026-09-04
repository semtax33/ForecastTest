from __future__ import annotations

from dataclasses import dataclass
import re

from .model import ConceptMention, FactTier, KPIFrame, QuantityMention, SemanticFrame, TextBlock
from .ontology import definition_for


@dataclass(frozen=True)
class ContextValidationDecision:
    accepted: bool
    reason: str
    failure_class: str
    tier: FactTier
    metric_span: tuple[int, int] | None = None
    value_span: tuple[int, int] | None = None


class ContextBindingError(ValueError):
    def __init__(self, decision: ContextValidationDecision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


_SENTENCE_BOUNDARY = re.compile(r"(?:[.!?][\"”']?\s+(?=[A-Z])|[•]\s*)")
_INTERVENING_VALUE_OWNER = re.compile(
    r"\b(?:net income|operating income|operating profit|turnaround costs?|"
    r"dividends?|repurchases?|free cash flow|earnings per share|eps|"
    r"capital expenditures?|cash flow|debt balance)\b",
    re.IGNORECASE,
)
_SAFE_VALUE_BEFORE_METRIC = re.compile(
    r"^\s*(?:of|in)\s+(?:(?:annual|quarterly|pro\s+forma|total|segment)\s+){0,3}$",
    re.IGNORECASE,
)
_SAFE_VALUE_PREFIX = re.compile(
    r"\b(?:generated|generates|approach(?:es|ed)?|had|has|reported|reached|"
    r"expect(?:s|ed)?|forecast(?:s|ed)?|project(?:s|ed)?|will|represented|"
    r"accounted\s+for|comprised|made\s+up)\s+"
    r"(?:approximately\s+|about\s+|roughly\s+)?$",
    re.IGNORECASE,
)


def _base_concept(concept: str) -> str:
    base = concept.removeprefix("PRIOR_YEAR_")
    for suffix in ("_NOT_EXPECTED", "_GUIDANCE", "_CHANGE"):
        base = base.removesuffix(suffix)
    return base


def validate_context_binding(
    frame: KPIFrame,
    block: TextBlock,
    mentions: tuple[ConceptMention, ...],
    value: QuantityMention | None,
    *,
    inherited: bool,
) -> ContextValidationDecision:
    """Validate that a candidate value is locally predicated on its KPI.

    The validator is deliberately issuer-agnostic.  It rejects cross-sentence,
    backwards, distant, and intervening-subject bindings that created the V2.1
    blind false positives.
    """

    base = _base_concept(frame.concept)
    tier = definition_for(base).tier
    if value is None:
        return ContextValidationDecision(True, "QUALITATIVE_FRAME", "NONE", tier)
    if inherited:
        allowed = frame.frame in {SemanticFrame.NOT_EXPECTED, SemanticFrame.COMPOSITION}
        return ContextValidationDecision(
            allowed,
            "BOUNDED_CONTEXT_ANTECEDENT" if allowed else "UNSAFE_INHERITED_NUMERIC_BINDING",
            "NONE" if allowed else "COREFERENCE_ERROR",
            tier,
            value_span=(value.char_start, value.char_end),
        )
    candidates = tuple(mention for mention in mentions if mention.concept == base)
    if not candidates:
        return ContextValidationDecision(
            False,
            "NO_DIRECT_METRIC_SPAN_FOR_NUMERIC_FRAME",
            "METRIC_ALIAS_ERROR",
            tier,
            value_span=(value.char_start, value.char_end),
        )
    preceding = tuple(item for item in candidates if item.char_end <= value.char_start)
    if not preceding:
        nearest = min(candidates, key=lambda item: abs(item.char_start - value.char_start))
        bridge = block.text[value.char_end : nearest.char_start]
        prefix = block.text[max(0, value.char_start - 96) : value.char_start]
        safe_reverse = (
            value.char_end <= nearest.char_start
            and len(bridge) <= 72
            and _SAFE_VALUE_BEFORE_METRIC.fullmatch(bridge) is not None
            and _SAFE_VALUE_PREFIX.search(prefix) is not None
            and _SENTENCE_BOUNDARY.search(bridge) is None
        )
        if safe_reverse:
            return ContextValidationDecision(
                True,
                "BOUNDED_VALUE_BEFORE_METRIC_BINDING",
                "NONE",
                tier,
                metric_span=(nearest.char_start, nearest.char_end),
                value_span=(value.char_start, value.char_end),
            )
        return ContextValidationDecision(
            False,
            "VALUE_PRECEDES_METRIC",
            "RELATION_ERROR",
            tier,
            metric_span=(nearest.char_start, nearest.char_end),
            value_span=(value.char_start, value.char_end),
        )
    metric = max(preceding, key=lambda item: item.char_end)
    between = block.text[metric.char_end : value.char_start]
    if len(between) > 240:
        return ContextValidationDecision(
            False,
            "METRIC_VALUE_DISTANCE_EXCEEDS_240_CHARS",
            "DOCUMENT_CONTEXT_ERROR",
            tier,
            (metric.char_start, metric.char_end),
            (value.char_start, value.char_end),
        )
    if _SENTENCE_BOUNDARY.search(between):
        return ContextValidationDecision(
            False,
            "METRIC_AND_VALUE_CROSS_SENTENCE_BOUNDARY",
            "DOCUMENT_CONTEXT_ERROR",
            tier,
            (metric.char_start, metric.char_end),
            (value.char_start, value.char_end),
        )
    other_mentions = tuple(
        item
        for item in mentions
        if item.concept != base
        and metric.char_end <= item.char_start < value.char_start
    )
    if other_mentions:
        return ContextValidationDecision(
            False,
            "INTERVENING_KPI_SUBJECT",
            "RELATION_ERROR",
            tier,
            (metric.char_start, metric.char_end),
            (value.char_start, value.char_end),
        )
    owner = _INTERVENING_VALUE_OWNER.search(between)
    if owner is not None:
        return ContextValidationDecision(
            False,
            f"INTERVENING_VALUE_OWNER:{owner.group(0).upper()}",
            "RELATION_ERROR",
            tier,
            (metric.char_start, metric.char_end),
            (value.char_start, value.char_end),
        )
    return ContextValidationDecision(
        True,
        "LOCAL_METRIC_VALUE_BINDING",
        "NONE",
        tier,
        (metric.char_start, metric.char_end),
        (value.char_start, value.char_end),
    )
