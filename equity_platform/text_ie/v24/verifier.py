from __future__ import annotations

from dataclasses import replace
import re

from equity_platform.documents import CanonicalDocument
from equity_platform.ir import AuthorityLevel, ExtractionMethod, SourceSpan

from ..context import qualifier, resolve_period
from ..model import (
    FactTier,
    KPIFrame,
    PeriodSemantics,
    Polarity,
    QuantityKind,
    SemanticFrame,
    VerificationStatus,
)
from ..ontology import definition_for, resolve_scope
from ..validation import FrameValidationError, validate_kpi_frame
from .candidate_generator import extract_candidate_quantities
from .model import BoundFrameCandidate, VerificationDecision


_BOUNDARY = re.compile(r"(?:[.!?][\"”']?\s+(?=[A-Z$])|[•·])")
_SENSITIVITY = re.compile(r"\b(?:for each|for every|per every)\b", re.IGNORECASE)
_ABSOLUTE_EVIDENCE = re.compile(
    r"\b(?:was|were|is|are|of|at|reached|total(?:ed|s)?|reported|"
    r"ended|with|balance|stood|had|has|invested|generated|generates|expects?|"
    r"forecast|projects?)\b",
    re.IGNORECASE,
)
_CHANGE_EVIDENCE = re.compile(
    r"\b(?:increased|grew|rose|decreased|declined|fell|up|down|"
    r"expansion|contraction|increase|decrease)\b",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"\b(?:decreased|declined|fell|down|contraction|decrease)\b",
    re.IGNORECASE,
)
_FORWARD = re.compile(
    r"\b(?:expects?|expected|guidance|forecast|outlook|projects?|will|target)\b",
    re.IGNORECASE,
)
_CAUSAL = re.compile(
    r"\b(?:due to|because|driven by|resulted from|reflecting|increased)\b",
    re.IGNORECASE,
)


def _reject(item: BoundFrameCandidate, reason: str, failure: str) -> VerificationDecision:
    return VerificationDecision(item, False, reason, failure)


def _local_polarity(item: BoundFrameCandidate) -> Polarity:
    start = max(0, min(item.relation_start, item.value.char_start if item.value else item.relation_start) - 24)
    end = min(
        len(item.block.text),
        max(item.relation_end, item.value.char_end if item.value else item.relation_end) + 24,
    )
    local = item.block.text[start:end]
    match = _NEGATIVE.search(local)
    return Polarity(
        positive=match is None,
        cue=match.group(0) if match else None,
        cue_start=start + match.start() if match else None,
        cue_end=start + match.end() if match else None,
    )


def _method(document: CanonicalDocument, item: BoundFrameCandidate) -> ExtractionMethod:
    if item.proposed_by_llm:
        return ExtractionMethod.LLM
    if item.value is not None:
        for index in item.block.inline_fact_indices:
            fact = document.inline_facts[index]
            if abs(float(fact.value) - item.value.value) <= max(1e-9, abs(item.value.value) * 1e-9):
                return ExtractionMethod.INLINE_XBRL
    if item.frame is SemanticFrame.CAUSE_EFFECT:
        return ExtractionMethod.DEPENDENCY_RULE
    return ExtractionMethod.SPAN_RULE


def _build_frame(document: CanonicalDocument, item: BoundFrameCandidate) -> KPIFrame:
    period, semantics = resolve_period(item.block, item.frame)
    if item.output_concept.endswith("_GUIDANCE"):
        semantics = PeriodSemantics.FORECAST
    method = _method(document, item)
    base = item.output_concept.removesuffix("_GUIDANCE").removesuffix("_CHANGE")
    tier = definition_for(base).tier
    frame = KPIFrame(
        concept=item.output_concept,
        entity=item.block.entity,
        scope=resolve_scope(item.block.text, item.block.nearest_heading),
        period=period,
        period_semantics=semantics,
        frame=item.frame,
        value=item.value.value if item.value else None,
        unit=item.value.unit if item.value else None,
        change=None,
        change_unit=None,
        comparator="PRIOR_PERIOD" if item.frame is SemanticFrame.CHANGE_BY else None,
        polarity=_local_polarity(item),
        qualifier=qualifier(item.block.text),
        source=item.block.source,
        source_span=SourceSpan(
            section=item.block.section,
            char_start=item.block.char_start,
            char_end=item.block.char_end,
            literal=item.block.text,
        ),
        extraction_method=method,
        rule_id=item.rule_id,
        rule_version=1,
        extraction_confidence=0.94 if item.proposed_by_llm else 0.97,
        authority=(
            AuthorityLevel.RESEARCH_DIAGNOSTIC
            if item.proposed_by_llm or tier is FactTier.NARRATIVE
            else AuthorityLevel.RESEARCH_EVIDENCE
        ),
        verification_status=VerificationStatus.PROPOSED,
        lower_value=item.lower_value,
        upper_value=item.upper_value,
        context_trace={
            "candidate_id": item.candidate_id,
            "origins": [origin.value for origin in item.origins],
            "relation_evidence": item.relation_evidence,
            "relation_group": item.relation_group,
            "llm_proposal_only": item.proposed_by_llm,
        },
        tier=tier,
    )
    verified = validate_kpi_frame(frame, document)
    return replace(
        verified,
        verified_by=(
            "LLM_PROPOSAL_PLUS_DETERMINISTIC_V24_VERIFIER"
            if item.proposed_by_llm
            else "DETERMINISTIC_V24_STRICT_VERIFIER"
        ),
    )


def _structural_check(item: BoundFrameCandidate) -> VerificationDecision | None:
    text = item.block.text
    metric = item.metric
    if metric.inherited_from:
        return _reject(item, "HEADING_ONLY_NUMERIC_BINDING_REQUIRES_REVIEW", "HEADING_CONTEXT")
    if text[metric.char_start : metric.char_end].casefold() != metric.alias.casefold():
        return _reject(item, "METRIC_LITERAL_NOT_EXACT", "SOURCE_SPAN_ERROR")
    if text[item.relation_start : item.relation_end] != item.relation_evidence:
        return _reject(item, "RELATION_LITERAL_NOT_EXACT", "SOURCE_SPAN_ERROR")
    if item.value is not None and item.frame is not SemanticFrame.RANGE_GUIDANCE:
        if text[item.value.char_start : item.value.char_end] != item.value.raw:
            return _reject(item, "NUMERIC_LITERAL_NOT_EXACT", "SOURCE_SPAN_ERROR")
    if item.value is not None:
        left = min(metric.char_end, item.value.char_end)
        right = max(metric.char_start, item.value.char_start)
        if right - left > 240:
            return _reject(item, "METRIC_VALUE_DISTANCE_EXCEEDS_240_CHARS", "RELATION_ERROR")
        if _BOUNDARY.search(text[left:right]):
            return _reject(item, "METRIC_VALUE_CROSSES_BOUNDARY", "DOCUMENT_CONTEXT_ERROR")
        if _SENSITIVITY.search(text[max(0, left - 24) : min(len(text), right + 48)]):
            return _reject(item, "SENSITIVITY_NOT_POINT_FACT", "RELATION_ERROR")
    if item.frame is SemanticFrame.ABSOLUTE_VALUE:
        if _ABSOLUTE_EVIDENCE.fullmatch(item.relation_evidence) is None:
            return _reject(item, "ABSOLUTE_RELATION_NOT_PROVEN", "RELATION_ERROR")
    elif item.frame is SemanticFrame.CHANGE_BY:
        if _CHANGE_EVIDENCE.fullmatch(item.relation_evidence) is None or item.value is None:
            return _reject(item, "CHANGE_RELATION_NOT_PROVEN", "RELATION_ERROR")
        quantities = extract_candidate_quantities(text)
        if item.relation_start > item.value.char_end:
            if item.relation_evidence.casefold() in {"up", "down"}:
                return _reject(item, "POST_VALUE_UP_DOWN_OWNS_NEXT_VALUE", "RELATION_ERROR")
            if any(
                (q.char_start, q.char_end) != (item.value.char_start, item.value.char_end)
                and q.char_start >= item.value.char_end
                and q.char_end <= item.relation_start
                for q in quantities
            ):
                return _reject(item, "INTERVENING_CHANGE_VALUE", "RELATION_ERROR")
        elif any(
            (q.char_start, q.char_end) != (item.value.char_start, item.value.char_end)
            and q.char_start >= item.relation_end
            and q.char_end <= item.value.char_start
            for q in quantities
        ):
            return _reject(item, "INTERVENING_CHANGE_VALUE", "RELATION_ERROR")
    elif item.frame is SemanticFrame.RANGE_GUIDANCE:
        window = text[max(0, metric.char_start - 120) : item.value.char_end if item.value else metric.char_end]
        if _FORWARD.search(window) is None:
            return _reject(item, "RANGE_WITHOUT_FORWARD_CUE", "PERIOD_ERROR")
        values = {q.value for q in extract_candidate_quantities(text)}
        if item.lower_value not in values or item.upper_value not in values:
            return _reject(item, "RANGE_ENDPOINT_NOT_EXACT", "SOURCE_SPAN_ERROR")
    elif item.frame is SemanticFrame.CAUSE_EFFECT:
        if _CAUSAL.fullmatch(item.relation_evidence) is None or not item.relation_group:
            return _reject(item, "CAUSAL_RELATION_NOT_PROVEN", "RELATION_ERROR")
    return None


def verify_bound_candidates(
    document: CanonicalDocument,
    bindings: tuple[BoundFrameCandidate, ...],
) -> tuple[VerificationDecision, ...]:
    decisions: list[VerificationDecision] = []
    absolute_groups: dict[tuple[str, int, int], list[BoundFrameCandidate]] = {}
    for item in bindings:
        if item.frame is SemanticFrame.ABSOLUTE_VALUE:
            absolute_groups.setdefault(
                (item.candidate_id, item.metric.char_start, item.metric.char_end), []
            ).append(item)
    closest_absolute: set[int] = set()
    for group in absolute_groups.values():
        closest = min(
            group,
            key=lambda item: abs(
                (item.value.char_start if item.value else item.metric.char_start)
                - item.metric.char_start
            ),
        )
        closest_absolute.add(id(closest))

    for item in bindings:
        if item.frame is SemanticFrame.ABSOLUTE_VALUE and id(item) not in closest_absolute:
            decisions.append(
                _reject(item, "MULTIPLE_VALUES_FOR_ONE_METRIC_ANCHOR", "AMBIGUITY")
            )
            continue
        rejected = _structural_check(item)
        if rejected is not None:
            decisions.append(rejected)
            continue
        try:
            frame = _build_frame(document, item)
        except (FrameValidationError, KeyError, ValueError) as exc:
            decisions.append(_reject(item, str(exc), "SEMANTIC_VALIDATION"))
            continue
        decisions.append(VerificationDecision(item, True, "STRICT_VERIFIER_PASS", "NONE", frame))
    return tuple(decisions)
