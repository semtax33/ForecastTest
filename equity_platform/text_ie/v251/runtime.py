from __future__ import annotations

from dataclasses import dataclass, replace
import re

from equity_platform.documents import CanonicalDocument
from equity_platform.ir import AuthorityLevel, ExtractionMethod, SourceSpan

from ..context import qualifier, resolve_period
from ..document import document_text_blocks
from ..model import (
    AbstentionItem,
    FactTier,
    KPIFrame,
    PeriodSemantics,
    Polarity,
    ReviewItem,
    SemanticFrame,
    TextExtractionResult,
    VerificationStatus,
)
from ..ontology import definition_for, resolve_scope
from ..runtime import _frame_claim, _frame_facts
from ..validation import FrameValidationError, validate_kpi_frame
from ..v24 import extract_candidate_quantities, metric_anchors
from ..v25 import extract_text_kpis_v25
from ..v25.table_router import route_financial_grid


_CHANGE = re.compile(r"\b(?:increase|increased|grew|rose|decrease|decreased|declined|fell|up|down|expansion)\b", re.I)
_FORWARD = re.compile(r"\b(?:expect|expects|expected|guidance|outlook|forecast|target)\b", re.I)
_RANGE = re.compile(r"^\s*(?:to|through|[-–—])\s*$", re.I)
_YEAR = re.compile(r"^20\d{2}$")


@dataclass(frozen=True)
class V251ExtractionResult:
    extraction: TextExtractionResult
    candidates: tuple[object, ...]
    table_routes: tuple[object, ...]
    precision_rejections: int


def _strong_table(block: object) -> object | None:
    routed = route_financial_grid(block)
    if routed is not None:
        return routed
    quantities = extract_candidate_quantities(block.text)
    concepts = tuple(dict.fromkeys(item.concept for item in metric_anchors(block.text, block.nearest_heading)))
    sentence_punctuation = len(re.findall(r"(?<!\d)[.!?](?!\d)", block.text))
    low_punctuation = sentence_punctuation / max(1, len(block.text.split())) < 0.015
    if len(quantities) >= 8 and low_punctuation and concepts:
        from equity_platform.documents.table_reconstruction import TableReconstructionCandidate
        return TableReconstructionCandidate(
            block.sentence_index, block.char_start, block.char_end, block.text, (), concepts,
            len(quantities), ("V251_HIGH_DENSITY_GRID",),
        )
    return None


def _safe(frame: KPIFrame) -> bool:
    text = frame.source_span.literal
    quantities = extract_candidate_quantities(text)
    if frame.unit == "X" and _YEAR.fullmatch(str(int(frame.value or 0))):
        return False
    if frame.frame is SemanticFrame.ABSOLUTE_VALUE:
        if _CHANGE.search(text):
            return False
        for left, right in zip(quantities, quantities[1:]):
            if left.kind is right.kind and _RANGE.fullmatch(text[left.char_end:right.char_start]):
                return False
        return True
    if frame.frame is SemanticFrame.CHANGE_TO:
        deltas = [item for item in quantities if item.unit in {"PERCENT", "BASIS_POINTS"}]
        levels = [item for item in quantities if item.unit not in {"PERCENT", "BASIS_POINTS"}]
        return len(deltas) == 1 and len(levels) == 1
    if frame.frame is SemanticFrame.CHANGE_BY:
        deltas = [item for item in quantities if item.unit in {"PERCENT", "BASIS_POINTS"}]
        levels = [item for item in quantities if item.unit not in {"PERCENT", "BASIS_POINTS"}]
        return len(deltas) == 1 and not levels and " to " not in text.casefold()
    return False


def _range_frame(document: CanonicalDocument, candidate: object) -> KPIFrame | None:
    if candidate.metric.inherited_from:
        return None
    text = candidate.block.text
    prefix = text[max(0, candidate.metric.char_start - 100):candidate.metric.char_start]
    suffix = text[candidate.metric.char_end:]
    if _FORWARD.search(prefix + suffix[:80]) is None:
        return None
    values = [item for item in candidate.quantities if item.char_start >= candidate.metric.char_end and item.char_start - candidate.metric.char_end <= 180]
    pairs = []
    for left, right in zip(values, values[1:]):
        if left.kind is right.kind and left.unit == right.unit and _RANGE.fullmatch(text[left.char_end:right.char_start]):
            pairs.append((left, right))
    if len(pairs) != 1:
        return None
    left, right = pairs[0]
    period, _ = resolve_period(candidate.block, SemanticFrame.RANGE_GUIDANCE)
    low, high = sorted((left.value, right.value))
    proposed = KPIFrame(
        concept=candidate.metric.concept + "_GUIDANCE", entity=candidate.block.entity,
        scope=resolve_scope(text, candidate.block.nearest_heading), period=period,
        period_semantics=PeriodSemantics.FORECAST, frame=SemanticFrame.RANGE_GUIDANCE,
        value=(low + high) / 2, unit=left.unit, change=None, change_unit=None,
        comparator=None, polarity=Polarity(True), qualifier=qualifier(text),
        source=candidate.block.source,
        source_span=SourceSpan(candidate.block.section, candidate.block.char_start, candidate.block.char_end, text),
        extraction_method=ExtractionMethod.SPAN_RULE, rule_id="v251.range_adjudicator", rule_version=1,
        extraction_confidence=0.98, authority=AuthorityLevel.RESEARCH_EVIDENCE,
        verification_status=VerificationStatus.PROPOSED, lower_value=low, upper_value=high,
        context_trace={"binding_eligibility": "UNIQUE_TYPED_RANGE"},
        tier=definition_for(candidate.metric.concept).tier,
    )
    return replace(validate_kpi_frame(proposed, document), verified_by="V251_RANGE_STRICT_VERIFIER")


def extract_text_kpis_v251(document: CanonicalDocument) -> V251ExtractionResult:
    prior = extract_text_kpis_v25(document)
    routes = list(prior.table_routes)
    keys = {(item.char_start, item.char_end) for item in routes}
    for block in document_text_blocks(document):
        route = _strong_table(block)
        if route is not None and (route.char_start, route.char_end) not in keys:
            routes.append(route)
            keys.add((route.char_start, route.char_end))
    frames = []
    rejected = 0
    for frame in prior.extraction.frames:
        if any(frame.source_span.char_start >= route.char_start and frame.source_span.char_end <= route.char_end for route in routes):
            rejected += 1
            continue
        if not _safe(frame):
            rejected += 1
            continue
        if frame.frame is SemanticFrame.ABSOLUTE_VALUE and _FORWARD.search(frame.source_span.literal):
            frame = replace(frame, concept=frame.concept + "_GUIDANCE", period_semantics=PeriodSemantics.FORECAST, rule_id="v251.point_guidance_adjudicator")
        frames.append(frame)
    existing_spans = {(frame.source_span.char_start, frame.concept) for frame in frames}
    for candidate in prior.candidates:
        if any(candidate.block.char_start >= route.char_start and candidate.block.char_end <= route.char_end for route in routes):
            continue
        try:
            frame = _range_frame(document, candidate)
        except (FrameValidationError, KeyError, ValueError):
            frame = None
        if frame is not None and (frame.source_span.char_start, frame.concept) not in existing_spans:
            frames.append(frame)
            existing_spans.add((frame.source_span.char_start, frame.concept))
    reviews = list(prior.extraction.reviews)
    abstentions = list(prior.extraction.abstentions)
    covered = {(frame.source_span.char_start, frame.source_span.char_end) for frame in frames}
    covered.update((item.source_span.char_start, item.source_span.char_end) for item in reviews)
    covered.update((item.source_span.char_start, item.source_span.char_end) for item in abstentions)
    for candidate in prior.candidates:
        span = (candidate.block.char_start, candidate.block.char_end)
        if span in covered or any(candidate.block.char_start >= route.char_start and candidate.block.char_end <= route.char_end for route in routes):
            continue
        abstentions.append(AbstentionItem(
            candidate.block.sentence_index, "v251.fail_closed_coverage", "NO_SAFE_FINAL_BINDING",
            "PRECISION_RECOVERY_ABSTENTION", SourceSpan(candidate.block.section, *span, candidate.block.text),
            definition_for(candidate.metric.concept).tier, (candidate.metric.concept,),
        ))
        covered.add(span)
    extraction = TextExtractionResult(
        frames=tuple(frames), facts=tuple(fact for frame in frames for fact in _frame_facts(frame)),
        evidence_claims=tuple(claim for frame in frames if (claim := _frame_claim(frame)) is not None),
        relations=(), reviews=tuple(reviews), abstentions=tuple(abstentions),
        backend_name="V251_PRECISION_ADJUDICATOR",
    )
    return V251ExtractionResult(extraction, prior.candidates, tuple(routes), rejected)
