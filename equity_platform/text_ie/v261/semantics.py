from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import re

from equity_platform.documents import CanonicalDocument
from equity_platform.ir import AuthorityLevel, ExtractionMethod, SourceSpan

from ..context import qualifier, resolve_period
from ..model import (
    FactTier,
    KPIFrame,
    Polarity,
    QuantityKind,
    QuantityMention,
    SemanticFrame,
    TextBlock,
    VerificationStatus,
)
from ..ontology import definition_for, resolve_scope
from ..v24 import extract_candidate_quantities, metric_anchors
from ..validation import FrameValidationError, validate_kpi_frame


_SPLIT = re.compile(r"[●◌◦▪·]|;|\bwhile\b", re.I)
_COMPARE = re.compile(r"\b(?:as\s+)?compared\s+(?:with|to)\b", re.I)
_CHANGE = re.compile(r"\b(increased|increase|grew|rose|decreased|decrease|declined|fell|up|down|outperformed)\b", re.I)
_NEGATIVE = {"decreased", "decrease", "declined", "fell", "down"}
_SECURITIES = re.compile(
    r"\b(?:sales agreement|sales agent|common shares?|public offering|pre-funded warrants?|"
    r"par value|price to the public|Internal Revenue Code)\b",
    re.I,
)
_OPERATIONAL_COUNT = re.compile(
    r"(?<![A-Za-z0-9])(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>tons?|units?|aircraft)\b",
    re.I,
)


@dataclass(frozen=True)
class _Anchor:
    concept: str
    start: int
    end: int
    candidate_id: str


def _quantities(text: str) -> tuple[QuantityMention, ...]:
    output = list(extract_candidate_quantities(text))
    occupied = {(item.char_start, item.char_end) for item in output}
    for match in _OPERATIONAL_COUNT.finditer(text):
        if (match.start(), match.end()) in occupied:
            continue
        output.append(QuantityMention(
            QuantityKind.COUNT,
            float(match.group("number").replace(",", "")),
            match.group("unit").upper(),
            match.group(0),
            match.start(),
            match.end(),
        ))
    return tuple(sorted(output, key=lambda item: item.char_start))


def _segments(text: str) -> tuple[tuple[int, int, str], ...]:
    starts = [0]
    ends = []
    for match in _SPLIT.finditer(text):
        ends.append(match.start())
        starts.append(match.end())
    ends.append(len(text))
    output = []
    for start, end in zip(starts, ends):
        left = start + len(text[start:end]) - len(text[start:end].lstrip())
        right = end - (len(text[start:end]) - len(text[start:end].rstrip()))
        if right > left:
            output.append((left, right, text[left:right]))
    return tuple(output)


def _anchors(block: TextBlock, segment_start: int, segment: str, candidates: tuple[object, ...]) -> tuple[_Anchor, ...]:
    output = []
    for mention in metric_anchors(segment, block.nearest_heading):
        if mention.inherited_from:
            continue
        global_start = segment_start + mention.char_start
        matching = next((
            item for item in candidates
            if item.block.char_start == block.char_start
            and item.metric.concept == mention.concept
            and item.metric.char_start == global_start
        ), None)
        candidate_id = matching.candidate_id if matching else "v261.direct." + sha256(
            f"{block.source.sha256}:{block.char_start}:{global_start}:{mention.concept}".encode()
        ).hexdigest()[:16]
        output.append(_Anchor(mention.concept, mention.char_start, mention.char_end, candidate_id))
    for concept, pattern in (
        ("CASH", re.compile(r"\bcash\b", re.I)),
        ("DEBT", re.compile(r"\bdebt\b", re.I)),
    ):
        for match in pattern.finditer(segment):
            before = _quantities(segment[max(0, match.start() - 32):match.start()])
            if not before:
                continue
            candidate_id = "v261.direct." + sha256(
                f"{block.source.sha256}:{block.char_start}:{segment_start + match.start()}:{concept}".encode()
            ).hexdigest()[:16]
            output.append(_Anchor(concept, match.start(), match.end(), candidate_id))
            break
    return tuple(sorted({(item.start, item.end, item.concept): item for item in output}.values(), key=lambda item: item.start))


def _frame(
    document: CanonicalDocument,
    block: TextBlock,
    span: tuple[int, int, str],
    anchor: _Anchor,
    *,
    concept: str,
    semantic: SemanticFrame,
    value: QuantityMention,
    change: QuantityMention | None = None,
    direction: int = 1,
    rule_id: str,
) -> KPIFrame | None:
    start, end, literal = span
    period, semantics = resolve_period(block, semantic)
    proposed = KPIFrame(
        concept=concept,
        entity=block.entity,
        scope=resolve_scope(literal, block.nearest_heading),
        period=period,
        period_semantics=semantics,
        frame=semantic,
        value=value.value,
        unit=value.unit,
        change=change.value if change else None,
        change_unit=change.unit if change else None,
        comparator="PRIOR_PERIOD" if semantic in {SemanticFrame.CHANGE_BY, SemanticFrame.CHANGE_TO, SemanticFrame.COMPARATIVE} else None,
        polarity=Polarity(direction >= 0),
        qualifier=qualifier(literal),
        source=block.source,
        source_span=SourceSpan(block.section, block.char_start + start, block.char_start + end, literal),
        extraction_method=ExtractionMethod.SPAN_RULE,
        rule_id=rule_id,
        rule_version=1,
        extraction_confidence=0.995,
        authority=AuthorityLevel.RESEARCH_EVIDENCE,
        verification_status=VerificationStatus.PROPOSED,
        context_trace={"candidate_id": anchor.candidate_id, "binding_eligibility": "V261_EXACT_SEGMENT_RELATION"},
        tier=definition_for(anchor.concept).tier,
    )
    try:
        return replace(validate_kpi_frame(proposed, document), verified_by="V261_EXACT_SEGMENT_VERIFIER")
    except (FrameValidationError, KeyError, ValueError):
        return None


def _comparison(
    document: CanonicalDocument,
    block: TextBlock,
    span: tuple[int, int, str],
    anchors: tuple[_Anchor, ...],
) -> tuple[KPIFrame, ...]:
    _, _, text = span
    match = _COMPARE.search(text)
    if match is None:
        return ()
    quantities = _quantities(text)
    anchor = next((item for item in reversed(anchors) if item.end < match.start()), None)
    if anchor is None:
        return ()
    current = tuple(item for item in quantities if item.char_start >= anchor.end and item.char_end <= match.start())
    prior = tuple(item for item in quantities if item.char_start >= match.end())
    if len(current) != 1 or not prior or any(item.kind is not current[0].kind for item in prior):
        return ()
    output = []
    first = _frame(document, block, span, anchor, concept=anchor.concept, semantic=SemanticFrame.COMPARATIVE, value=current[0], rule_id="v261.comparison")
    if first:
        output.append(first)
    for value in prior:
        prior_frame = _frame(document, block, span, anchor, concept=f"PRIOR_YEAR_{anchor.concept}", semantic=SemanticFrame.COMPARATIVE, value=value, rule_id="v261.comparison")
        if prior_frame:
            output.append(prior_frame)
    return tuple(output)


def _change(
    document: CanonicalDocument,
    block: TextBlock,
    span: tuple[int, int, str],
    anchor: _Anchor,
) -> tuple[KPIFrame, ...]:
    _, _, text = span
    triggers = tuple(_CHANGE.finditer(text))
    trigger = min(triggers, key=lambda item: abs(item.start() - anchor.start), default=None)
    if trigger is None or abs(trigger.start() - anchor.start) > 180:
        return ()
    direction = -1 if trigger.group(1).casefold() in _NEGATIVE else 1
    quantities = _quantities(text)
    before_anchor = tuple(item for item in quantities if item.char_end <= anchor.start and anchor.start - item.char_end <= 40)
    between = tuple(item for item in quantities if item.char_start >= anchor.end and item.char_end <= trigger.start())
    after = tuple(item for item in quantities if item.char_start >= trigger.end())
    level = None
    if before_anchor and (
        re.search(r"\b(?:in|of)\s*$", text[before_anchor[-1].char_end:anchor.start], re.I)
        or (
            anchor.concept in {"CASH", "DEBT"}
            and not text[before_anchor[-1].char_end:anchor.start].strip()
        )
    ):
        level = before_anchor[-1]
    elif between and re.search(r"(?:^\s*|\bof\s*)$", text[anchor.end:between[-1].char_start], re.I):
        level = between[-1]
    to_levels = [
        item for item in after
        if re.search(r"\bto\b", text[trigger.end():item.char_start], re.I)
        and item.char_start - trigger.end() <= 120
    ]
    if to_levels:
        level = to_levels[0]
    relative = [
        item for item in quantities
        if item is not level
        and item.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
        and (
            item.char_start >= trigger.end()
            or (item.char_end <= trigger.start() and trigger.start() - item.char_end <= 12)
        )
    ]
    absolute_delta = [
        item for item in after
        if item is not level and item.kind is QuantityKind.MONEY
        and not re.search(r"\bto\b", text[trigger.end():item.char_start], re.I)
    ]
    if "outperformed" in trigger.group(1).casefold():
        relative.extend(
            item for item in after
            if re.search(r"\bpoints?\b", text[item.char_end:item.char_end + 12], re.I)
        )
    output = []
    if level is not None and relative:
        for delta in relative:
            frame = _frame(document, block, span, anchor, concept=anchor.concept, semantic=SemanticFrame.CHANGE_TO, value=level, change=delta, direction=direction, rule_id="v261.kpi_change")
            if frame:
                output.append(frame)
    elif level is not None:
        frame = _frame(document, block, span, anchor, concept=anchor.concept, semantic=SemanticFrame.CHANGE_TO, value=level, direction=direction, rule_id="v261.kpi_change")
        if frame:
            output.append(frame)
    else:
        for delta in (*absolute_delta, *relative):
            frame = _frame(document, block, span, anchor, concept=anchor.concept, semantic=SemanticFrame.CHANGE_BY, value=delta, direction=direction, rule_id="v261.kpi_change")
            if frame:
                output.append(frame)
    return tuple(output)


def _exact_absolute(
    document: CanonicalDocument,
    block: TextBlock,
    span: tuple[int, int, str],
    anchor: _Anchor,
) -> KPIFrame | None:
    _, _, text = span
    quantities = _quantities(text)
    if anchor.concept == "CAPEX" and re.search(r"\bincluded\b", text, re.I):
        values = [item for item in quantities if item.char_end <= anchor.start and item.kind is QuantityKind.MONEY]
        if values and re.search(r"\bof\s*$", text[values[-1].char_end:anchor.start], re.I):
            return _frame(document, block, span, anchor, concept="CAPEX", semantic=SemanticFrame.ABSOLUTE_VALUE, value=values[-1], rule_id="v261.value_before_metric")
    if anchor.concept == "PRODUCTION":
        values = [item for item in quantities if item.char_start >= anchor.end and item.char_start - anchor.end <= 24]
        if values and re.search(r"\bof\s*$", text[anchor.end:values[0].char_start], re.I):
            return _frame(document, block, span, anchor, concept="PRODUCTION", semantic=SemanticFrame.ABSOLUTE_VALUE, value=values[0], rule_id="v261.unit_production")
    if anchor.concept == "DEBT":
        zero = next((item for item in quantities if item.value == 0 and item.char_end <= anchor.start), None)
        if zero and re.search(r"\bzero debt\b", text, re.I):
            return _frame(document, block, span, anchor, concept="DEBT", semantic=SemanticFrame.ABSOLUTE_VALUE, value=zero, rule_id="v261.explicit_zero")
    if anchor.concept == "REVENUE" and re.search(r"revenue expected to be recognized", text, re.I):
        money = [item for item in quantities if item.kind is QuantityKind.MONEY and item.char_end <= anchor.start]
        if money:
            return _frame(document, block, span, anchor, concept="REVENUE_GUIDANCE", semantic=SemanticFrame.ABSOLUTE_VALUE, value=money[-1], rule_id="v261.deferred_revenue_guidance")
    return None


def recover_v261_frames(
    document: CanonicalDocument,
    candidates: tuple[object, ...],
    allowed_spans: set[tuple[int, int]],
) -> tuple[KPIFrame, ...]:
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        for local_start, local_end, text in _segments(block.text):
            span = (local_start, local_end, text)
            anchors = _anchors(block, local_start, text, candidates)
            output.extend(_comparison(document, block, span, anchors))
            for anchor in anchors:
                output.extend(_change(document, block, span, anchor))
                absolute = _exact_absolute(document, block, span, anchor)
                if absolute:
                    output.append(absolute)
    unique = {}
    for frame in output:
        unique.setdefault((frame.concept, frame.frame, frame.value, frame.change, frame.source_span.char_start), frame)
    return tuple(unique.values())


def safe_existing_frame(frame: KPIFrame) -> bool:
    text = frame.source_span.literal
    if frame.tier is FactTier.NARRATIVE and frame.frame is not SemanticFrame.CAUSE_EFFECT:
        return False
    if frame.concept.removeprefix("PRIOR_YEAR_") in {"REVENUE", "PRICE_REALIZATION"} and _SECURITIES.search(text):
        return False
    if frame.concept == "DEBT" and re.search(r"\b(?:do not have any|no)\b.{0,48}\bdebt\b", text, re.I) and frame.value != 0:
        return False
    if frame.rule_id == "v26.kpi_change" and re.search(r"\bwhile\b", text, re.I):
        return False
    return True
