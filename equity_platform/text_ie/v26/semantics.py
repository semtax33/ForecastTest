from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
import re

from equity_platform.documents import CanonicalDocument
from equity_platform.ir import AuthorityLevel, ExtractionMethod, SourceSpan

from ..context import qualifier, resolve_period
from ..model import (
    KPIFrame,
    PeriodSemantics,
    Polarity,
    QuantityKind,
    SemanticFrame,
    VerificationStatus,
)
from ..ontology import definition_for, resolve_scope
from ..v24 import extract_candidate_quantities
from ..validation import FrameValidationError, validate_kpi_frame
from .model import ComparisonFrame, KPIChange
from .router import BlockRoute, RoutedBlock


_COMPARE = re.compile(r"\b(?:as\s+)?compared\s+(?:with|to)\b", re.I)
_COPULA = re.compile(r"\b(?:was|were|is|are)\b", re.I)
_CHANGE = re.compile(
    r"\b(increased|grew|rose|decreased|declined|fell|up|down)\b",
    re.I,
)
_NEGATIVE = {"decreased", "declined", "fell", "down"}
_CAUSAL_BOUNDARY = re.compile(
    r"\b(?:primarily\s+)?(?:driven by|due to|because|resulting from|reflecting)\b",
    re.I,
)
_TO = re.compile(r"\bto(?:\s+(?:a|an|the|quarterly|record|of))*\s*$", re.I)
_LEVEL_BEFORE = re.compile(
    r"(?:^\s*$|(?:--|\b(?:of|at|was|were|is|are|generated)\b)[^.;]{0,48}$)",
    re.I,
)


def _route_for_span(start: int, end: int, routes: tuple[RoutedBlock, ...]) -> BlockRoute:
    return next(
        (
            item.route for item in routes
            if item.char_start is not None
            and item.char_end is not None
            and start >= item.char_start
            and end <= item.char_end
        ),
        BlockRoute.PROSE,
    )


def _source_span(candidate: object) -> SourceSpan:
    return SourceSpan(
        candidate.block.section,
        candidate.block.char_start,
        candidate.block.char_end,
        candidate.block.text,
    )


def _materialize(
    document: CanonicalDocument,
    candidate: object,
    *,
    concept: str,
    semantic: SemanticFrame,
    value: object,
    change: object | None,
    direction: int,
    rule_id: str,
) -> KPIFrame | None:
    period, semantics = resolve_period(candidate.block, semantic)
    proposed = KPIFrame(
        concept=concept,
        entity=candidate.block.entity,
        scope=resolve_scope(candidate.block.text, candidate.block.nearest_heading),
        period=period,
        period_semantics=semantics,
        frame=semantic,
        value=value.value,
        unit=value.unit,
        change=change.value if change is not None else None,
        change_unit=change.unit if change is not None else None,
        comparator="PRIOR_PERIOD",
        polarity=Polarity(direction >= 0),
        qualifier=qualifier(candidate.block.text),
        source=candidate.block.source,
        source_span=_source_span(candidate),
        extraction_method=ExtractionMethod.SPAN_RULE,
        rule_id=rule_id,
        rule_version=1,
        extraction_confidence=0.99,
        authority=AuthorityLevel.RESEARCH_EVIDENCE,
        verification_status=VerificationStatus.PROPOSED,
        context_trace={
            "candidate_id": candidate.candidate_id,
            "binding_eligibility": "V26_UNIQUE_TYPED_RELATION",
        },
        tier=definition_for(candidate.metric.concept).tier,
    )
    try:
        return replace(
            validate_kpi_frame(proposed, document),
            verified_by="V26_ROUTE_AWARE_STRICT_VERIFIER",
        )
    except (FrameValidationError, KeyError, ValueError):
        return None


def _comparison_recovery(
    document: CanonicalDocument,
    group: tuple[object, ...],
) -> tuple[tuple[ComparisonFrame, ...], tuple[KPIFrame, ...]]:
    text = group[0].block.text
    comparisons = tuple(_COMPARE.finditer(text))
    if not comparisons:
        return (), ()
    first_compare = comparisons[0]
    copulas = tuple(_COPULA.finditer(text[: first_compare.start()]))
    quantities = extract_candidate_quantities(text)
    if copulas:
        relation_start = copulas[-1].end()
    else:
        separators = [text.rfind("--", 0, first_compare.start())]
        relation_start = max(separators) + 2 if max(separators) >= 0 else -1
    if relation_start < 0:
        return (), ()
    current = tuple(
        item for item in quantities
        if item.char_start >= relation_start and item.char_end <= first_compare.start()
    )
    prior = tuple(item for item in quantities if item.char_start >= first_compare.end())
    anchors = tuple(
        item for item in group
        if not item.metric.inherited_from and item.metric.char_end <= relation_start
    )
    unique_anchors = tuple({
        (item.metric.char_start, item.metric.char_end, item.metric.concept): item
        for item in anchors
    }.values())
    unique_anchors = tuple(sorted(unique_anchors, key=lambda item: item.metric.char_start))
    if not current or not prior or not unique_anchors:
        return (), ()
    if len(unique_anchors) not in {1, len(current)}:
        return (), ()
    if len(unique_anchors) > 1 and len(current) != len(prior):
        return (), ()
    if any(left.kind is not right.kind for left, right in zip(current, prior)):
        return (), ()
    candidate = unique_anchors[0]
    concepts = (
        tuple(item.metric.concept for item in unique_anchors)
        if len(unique_anchors) > 1
        else (candidate.metric.concept,) * len(current)
    )
    comparison = ComparisonFrame(
        candidate.candidate_id,
        candidate.metric.concept,
        current,
        prior,
        _source_span(candidate),
    )
    frames = []
    for concept, value in zip(concepts, current):
        frame = _materialize(
            document, candidate, concept=concept, semantic=SemanticFrame.COMPARATIVE,
            value=value, change=None, direction=1, rule_id="v26.comparison_frame",
        )
        if frame is not None:
            frames.append(frame)
    prior_concepts = concepts if len(concepts) == len(prior) else (concepts[0],) * len(prior)
    for concept, value in zip(prior_concepts, prior):
        frame = _materialize(
            document, candidate, concept=f"PRIOR_YEAR_{concept}",
            semantic=SemanticFrame.COMPARATIVE, value=value, change=None,
            direction=1, rule_id="v26.comparison_frame",
        )
        if frame is not None:
            frames.append(frame)
    return (comparison,), tuple(frames)


def _change_recovery(
    document: CanonicalDocument,
    group: tuple[object, ...],
) -> tuple[tuple[KPIChange, ...], tuple[KPIFrame, ...]]:
    text = group[0].block.text
    anchors = tuple(sorted(
        {
            (item.metric.char_start, item.metric.char_end, item.metric.concept): item
            for item in group if not item.metric.inherited_from
        }.values(),
        key=lambda item: item.metric.char_start,
    ))
    quantities = extract_candidate_quantities(text)
    changes = []
    frames = []
    for index, candidate in enumerate(anchors):
        start = candidate.metric.char_end
        end = anchors[index + 1].metric.char_start if index + 1 < len(anchors) else len(text)
        segment = text[start:end]
        triggers = tuple(_CHANGE.finditer(segment))
        if not triggers:
            continue
        first_trigger = triggers[0]
        trigger_pos = start + first_trigger.start()
        trigger_end = start + first_trigger.end()
        causal = _CAUSAL_BOUNDARY.search(text, trigger_end, end)
        semantic_end = causal.start() if causal else end
        local = tuple(
            item for item in quantities
            if item.char_start >= start and item.char_end <= semantic_end
        )
        if not local:
            continue
        deltas = tuple(
            item for item in local
            if item.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
            and item.char_start >= trigger_pos
        )
        levels_after_to = tuple(
            item for item in local
            if item.char_start >= trigger_end
            and item.kind not in {QuantityKind.BASIS_POINTS}
            and _TO.search(text[trigger_end:item.char_start]) is not None
        )
        levels_before = tuple(
            item for item in local
            if item.char_end <= trigger_pos
            and item.kind not in {QuantityKind.BASIS_POINTS}
            and _LEVEL_BEFORE.search(text[start:item.char_start]) is not None
        )
        level = levels_after_to[0] if levels_after_to else levels_before[-1] if levels_before else None
        if level is not None and level.kind is QuantityKind.PERCENT:
            deltas = tuple(item for item in deltas if item is not level)
        if not deltas and level is None:
            continue
        selected_deltas = deltas or (None,)
        direction = -1 if first_trigger.group(1).casefold() in _NEGATIVE else 1
        for delta in selected_deltas:
            event = KPIChange(
                candidate.candidate_id,
                candidate.metric.concept,
                level,
                delta,
                direction,
                _source_span(candidate),
            )
            changes.append(event)
            semantic = SemanticFrame.CHANGE_TO if level is not None else SemanticFrame.CHANGE_BY
            value = level if level is not None else delta
            assert value is not None
            frame = _materialize(
                document,
                candidate,
                concept=candidate.metric.concept,
                semantic=semantic,
                value=value,
                change=delta if level is not None else None,
                direction=direction,
                rule_id="v26.kpi_change",
            )
            if frame is not None:
                frames.append(frame)
    return tuple(changes), tuple(frames)


def recover_route_aware_semantics(
    document: CanonicalDocument,
    candidates: tuple[object, ...],
    routes: tuple[RoutedBlock, ...],
) -> tuple[tuple[KPIChange, ...], tuple[ComparisonFrame, ...], tuple[KPIFrame, ...]]:
    groups: dict[tuple[str, int, int], list[object]] = defaultdict(list)
    for candidate in candidates:
        route = _route_for_span(candidate.block.char_start, candidate.block.char_end, routes)
        if route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}:
            continue
        groups[(candidate.block.source.sha256, candidate.block.char_start, candidate.block.char_end)].append(candidate)
    changes = []
    comparisons = []
    frames = []
    for group in groups.values():
        ordered = tuple(group)
        block_comparisons, comparison_frames = _comparison_recovery(document, ordered)
        block_changes, change_frames = _change_recovery(document, ordered)
        comparisons.extend(block_comparisons)
        changes.extend(block_changes)
        frames.extend(comparison_frames)
        frames.extend(change_frames)
    return tuple(changes), tuple(comparisons), tuple(frames)
