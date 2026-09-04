from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

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
from ..v24 import generate_recall_candidates
from .binding import constraint_bind
from .model import CanonicalBinding, V25ExtractionResult
from .table_router import route_financial_grid


def _inside(block: object, route: object) -> bool:
    return block.char_start >= route.char_start and block.char_end <= route.char_end


def _frame(document: CanonicalDocument, binding: CanonicalBinding) -> KPIFrame:
    if binding.level is not None and binding.delta is not None:
        semantic = SemanticFrame.CHANGE_TO
        value = binding.level
        change = binding.delta.value
        change_unit = binding.delta.unit
    elif binding.delta is not None:
        semantic = SemanticFrame.CHANGE_BY
        value = binding.delta
        change = None
        change_unit = None
    elif binding.level is not None:
        semantic = SemanticFrame.ABSOLUTE_VALUE
        value = binding.level
        change = None
        change_unit = None
    else:
        raise ValueError("canonical binding has no numeric role")
    period, semantics = resolve_period(binding.candidate.block, semantic)
    if definition_for(binding.candidate.metric.concept).tier is FactTier.NARRATIVE:
        authority = AuthorityLevel.RESEARCH_DIAGNOSTIC
    else:
        authority = AuthorityLevel.RESEARCH_EVIDENCE
    start = binding.candidate.block.char_start + binding.clause.char_start
    end = binding.candidate.block.char_start + binding.clause.char_end
    proposed = KPIFrame(
        concept=binding.candidate.metric.concept,
        entity=binding.candidate.block.entity,
        scope=resolve_scope(binding.clause.text, binding.candidate.block.nearest_heading),
        period=period,
        period_semantics=semantics,
        frame=semantic,
        value=value.value,
        unit=value.unit,
        change=change,
        change_unit=change_unit,
        comparator="PRIOR_PERIOD" if semantic in {SemanticFrame.CHANGE_BY, SemanticFrame.CHANGE_TO} else None,
        polarity=Polarity(positive=binding.direction >= 0),
        qualifier=qualifier(binding.clause.text),
        source=binding.candidate.block.source,
        source_span=SourceSpan(
            section=binding.candidate.block.section,
            char_start=start,
            char_end=end,
            literal=binding.clause.text,
        ),
        extraction_method=ExtractionMethod.SPAN_RULE,
        rule_id="v25.constraint_binding",
        rule_version=1,
        extraction_confidence=min(0.99, binding.score),
        authority=authority,
        verification_status=VerificationStatus.PROPOSED,
        context_trace={
            "candidate_id": binding.candidate.candidate_id,
            "binding_eligibility": "ELIGIBLE",
            "ambiguity_margin": binding.ambiguity_margin,
            "canonical_change_merged": binding.level is not None and binding.delta is not None,
            "scope_precedence": "sentence>bullet>heading>subsection>section>entity",
        },
        tier=definition_for(binding.candidate.metric.concept).tier,
    )
    return replace(
        validate_kpi_frame(proposed, document),
        verified_by="V25_CONSTRAINT_BINDER_AND_STRICT_VERIFIER",
    )


def extract_text_kpis_v25(document: CanonicalDocument) -> V25ExtractionResult:
    candidates, old_routes = generate_recall_candidates(document)
    routes = list(old_routes)
    route_keys = {(item.char_start, item.char_end) for item in routes}
    for block in document_text_blocks(document):
        route = route_financial_grid(block)
        if route is not None and (route.char_start, route.char_end) not in route_keys:
            routes.append(route)
            route_keys.add((route.char_start, route.char_end))
    text_candidates = tuple(
        item for item in candidates if not any(_inside(item.block, route) for route in routes)
    )
    roles, bindings = constraint_bind(text_candidates)
    frames: list[KPIFrame] = []
    reviews: list[ReviewItem] = []
    abstentions: list[AbstentionItem] = []
    emitted: list[tuple[CanonicalBinding, KPIFrame]] = []
    for binding in bindings:
        span = SourceSpan(
            section=binding.candidate.block.section,
            char_start=binding.candidate.block.char_start + binding.clause.char_start,
            char_end=binding.candidate.block.char_start + binding.clause.char_end,
            literal=binding.clause.text,
        )
        if binding.status == "REVIEW":
            reviews.append(ReviewItem(
                binding.candidate.block.sentence_index,
                "v25.binding_margin",
                "REVIEW_V25_AMBIGUOUS_BINDING",
                binding.reason,
                span,
                (binding.candidate.metric.concept,),
                definition_for(binding.candidate.metric.concept).tier,
            ))
            continue
        if binding.status != "AUTO":
            abstentions.append(AbstentionItem(
                binding.candidate.block.sentence_index,
                "v25.binding_eligibility",
                binding.reason,
                "NO_ELIGIBLE_BINDING",
                span,
                definition_for(binding.candidate.metric.concept).tier,
                (binding.candidate.metric.concept,),
            ))
            continue
        try:
            emitted.append((binding, _frame(document, binding)))
        except (FrameValidationError, KeyError, ValueError) as exc:
            reviews.append(ReviewItem(
                binding.candidate.block.sentence_index,
                "v25.strict_verifier",
                "REVIEW_V25_VALIDATION_REJECTED",
                str(exc),
                span,
                (binding.candidate.metric.concept,),
                definition_for(binding.candidate.metric.concept).tier,
            ))

    groups: dict[tuple[object, ...], list[tuple[CanonicalBinding, KPIFrame]]] = defaultdict(list)
    for item in emitted:
        frame = item[1]
        groups[(frame.concept, frame.scope, frame.period, frame.source_span.char_start)].append(item)
    conflicts = 0
    for group in groups.values():
        signatures = {(item[1].frame, item[1].value, item[1].change) for item in group}
        if len(signatures) > 1:
            conflicts += 1
            for binding, frame in group:
                reviews.append(ReviewItem(
                    binding.candidate.block.sentence_index,
                    "v25.conflict_resolver",
                    "REVIEW_V25_CONFLICT",
                    "CONFLICTING_VALUES_FOR_CONCEPT_SCOPE_PERIOD_SPAN",
                    frame.source_span,
                    (frame.concept,),
                    frame.tier,
                ))
            continue
        frames.append(group[0][1])

    for route in routes:
        abstentions.append(AbstentionItem(
            route.sentence_index,
            "v25.layout_table_router",
            "FINANCIAL_GRID_ROUTED_BEFORE_TEXT_IE",
            "TABLE_TEXT_BOUNDARY",
            SourceSpan(None, route.char_start, route.char_end, route.source_literal),
            FactTier.CRITICAL,
            tuple(route.metric_labels),
        ))
    extraction = TextExtractionResult(
        frames=tuple(frames),
        facts=tuple(fact for frame in frames for fact in _frame_facts(frame)),
        evidence_claims=tuple(
            claim for frame in frames if (claim := _frame_claim(frame)) is not None
        ),
        relations=(),
        reviews=tuple(reviews),
        abstentions=tuple(abstentions),
        backend_name="V25_CONSTRAINT_BASED_SEMANTIC_BINDING",
    )
    return V25ExtractionResult(
        extraction,
        candidates,
        roles,
        bindings,
        tuple(routes),
        sum(binding.level is not None and binding.delta is not None for binding in bindings),
        conflicts,
    )
