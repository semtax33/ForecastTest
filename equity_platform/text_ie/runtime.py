from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re

from equity_platform.documents import CanonicalDocument
from equity_platform.ir import (
    AuthorityLevel,
    ClaimStatus,
    ClaimType,
    EvidenceClaimIR,
    EvidenceStatus,
    ExtractionMethod,
    FactIR,
    FactOrigin,
    LineageRef,
    RelationType,
    SourceSpan,
)
from equity_platform.paths import PROJECT_ROOT

from .context import ContextStack, polarity, qualifier, resolve_period
from .document import document_text_blocks
from .dsl import TextRuleIR, compile_text_rule_file
from .model import (
    AmbiguityPolicy,
    KPIFrame,
    KPIRelationIR,
    PeriodSemantics,
    QuantityKind,
    QuantityMention,
    ReviewItem,
    SemanticFrame,
    TextBlock,
    TextExtractionResult,
    VerificationStatus,
)
from .matcher import match_sequence_pattern
from .ontology import definition_for, find_concepts
from .quantities import extract_quantities, extract_years
from .retrieval import narrative_candidate
from .spacy_backend import SemanticMatcherBackend, default_spacy_backend
from .validation import FrameValidationError, validate_kpi_frame


DEFAULT_RULE_PATH = (
    PROJECT_ROOT / "configs/parser_rules/text_ie/semantic_frames.arc"
)
DEFAULT_TEXT_RULES = compile_text_rule_file(DEFAULT_RULE_PATH)


def _source_span(block: TextBlock) -> SourceSpan:
    return SourceSpan(
        section=block.section,
        char_start=block.char_start,
        char_end=block.char_end,
        literal=block.text,
    )


def _trigger_position(text: str, triggers: tuple[str, ...]) -> int | None:
    positions = []
    for trigger in triggers:
        match = re.search(
            rf"(?<![A-Za-z0-9]){re.escape(trigger)}(?![A-Za-z0-9])",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            positions.append(match.start())
    return min(positions) if positions else None


def _relation_position(text: str, relations: tuple[str, ...]) -> int | None:
    return _trigger_position(text, relations)


def _quantity_candidates(
    quantities: tuple[QuantityMention, ...],
    rule: TextRuleIR,
) -> tuple[QuantityMention, ...]:
    if not rule.quantity_kinds:
        return quantities
    return tuple(item for item in quantities if item.kind in rule.quantity_kinds)


def _concept_value_candidates(
    names: tuple[str, ...],
    candidates: tuple[QuantityMention, ...],
    *,
    fail_on_mismatch: bool = True,
) -> tuple[QuantityMention, ...]:
    """Apply the ontology unit contract to an actual metric-value role.

    This must run only after a rule's structural relation has matched.  Running
    it on a trigger alone (notably ``increased`` or ``and``) turns unrelated
    quantities into false validation reviews.
    """
    if len(names) != 1 or not candidates:
        return candidates
    try:
        allowed_kinds = definition_for(names[0]).quantity_kinds
    except KeyError:
        return candidates
    if not allowed_kinds:
        return candidates
    compatible = tuple(item for item in candidates if item.kind in allowed_kinds)
    if compatible or not fail_on_mismatch:
        return compatible
    supplied = ", ".join(sorted({item.kind.value for item in candidates}))
    expected = ", ".join(item.value for item in allowed_kinds)
    raise FrameValidationError(
        f"{names[0]} does not accept {supplied}; expected {expected}"
    )


def _method(
    document: CanonicalDocument,
    block: TextBlock,
    quantity: QuantityMention | None,
    *,
    inherited: bool,
) -> ExtractionMethod:
    if quantity is not None:
        for index in block.inline_fact_indices:
            fact = document.inline_facts[index]
            tolerance = max(1e-9, abs(fact.value) * 1e-9)
            if abs(float(fact.value) - quantity.value) <= tolerance:
                return ExtractionMethod.INLINE_XBRL
    if inherited:
        return ExtractionMethod.CONTEXT_RULE
    # The built-in engine proves ordered local spans.  It deliberately does
    # not claim dependency-parser provenance unless an actual dependency
    # backend has validated the relation.
    return ExtractionMethod.SPAN_RULE


def _frame(
    *,
    document: CanonicalDocument,
    block: TextBlock,
    rule: TextRuleIR,
    concept: str,
    scope: str,
    period: str,
    period_semantics: PeriodSemantics,
    value: QuantityMention | None,
    change: QuantityMention | None = None,
    comparator: str | None = None,
    inherited: bool = False,
    lower_value: float | None = None,
    upper_value: float | None = None,
    context_trace: dict[str, object] | None = None,
    method_override: ExtractionMethod | None = None,
) -> KPIFrame:
    selected_method = method_override or _method(
        document, block, value, inherited=inherited
    )
    confidence = {
        ExtractionMethod.INLINE_XBRL: 0.99,
        ExtractionMethod.CONTEXT_RULE: 0.90,
        ExtractionMethod.SPAN_RULE: 0.96,
        ExtractionMethod.DEPENDENCY_RULE: 0.97,
    }[selected_method]
    qualifiers = qualifier(block.text)
    if qualifiers.approximation:
        confidence -= 0.02
    proposed = KPIFrame(
        concept=concept + rule.output_metric_suffix,
        entity=block.entity,
        scope=scope,
        period=period,
        period_semantics=period_semantics,
        frame=rule.frame,
        value=value.value if value else None,
        unit=value.unit if value else None,
        change=change.value if change else None,
        change_unit=change.unit if change else None,
        comparator=comparator,
        polarity=polarity(block.text),
        qualifier=qualifiers,
        source=block.source,
        source_span=_source_span(block),
        extraction_method=selected_method,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        extraction_confidence=confidence,
        authority=rule.authority,
        verification_status=VerificationStatus.PROPOSED,
        lower_value=lower_value,
        upper_value=upper_value,
        context_trace=context_trace or {},
    )
    return validate_kpi_frame(proposed, document)


def _match_rule(
    document: CanonicalDocument,
    block: TextBlock,
    rule: TextRuleIR,
    concepts: tuple[object, ...],
    quantities: tuple[QuantityMention, ...],
    *,
    inherited: bool,
    scope: str,
    backend: SemanticMatcherBackend | None,
) -> tuple[KPIFrame, ...] | None:
    trigger = _trigger_position(block.text, rule.triggers)
    if trigger is None:
        return None
    if rule.pattern:
        pattern_match = (
            backend.match_pattern(rule, block.text, concepts, quantities)
            if backend is not None
            else match_sequence_pattern(rule, block.text, concepts, quantities)
        )
        if pattern_match is None:
            return None
    names = tuple(dict.fromkeys(getattr(item, "concept") for item in concepts))
    if rule.concepts:
        names = tuple(name for name in names if name in rule.concepts)
    if rule.require_metric and not names:
        return None
    candidates = _quantity_candidates(quantities, rule)
    period, semantics = resolve_period(block, rule.frame)
    if period == "UNRESOLVED":
        return None

    if rule.frame is SemanticFrame.CHANGE_TO:
        relation = _relation_position(block.text, rule.relation_words)
        if relation is None:
            return None
        values = _concept_value_candidates(names, tuple(
            item
            for item in candidates
            if item.char_start > relation
        ))
        changes = tuple(
            item
            for item in quantities
            if item.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
            and item.char_end <= relation
        )
        if len(names) != 1 or len(values) != 1 or len(changes) > 1:
            return ()
        return (
            _frame(
                document=document,
                block=block,
                rule=rule,
                concept=names[0],
                scope=scope,
                period=period,
                period_semantics=semantics,
                value=values[0],
                change=changes[0] if changes else None,
                comparator="PRIOR_YEAR" if changes else None,
                inherited=inherited,
            ),
        )

    if rule.frame is SemanticFrame.CHANGE_BY:
        relation = _relation_position(block.text, rule.relation_words)
        changes = tuple(item for item in candidates if relation is not None and item.char_start > relation)
        if relation is None or len(names) != 1 or len(changes) != 1:
            return None if not changes else ()
        return (
            _frame(
                document=document,
                block=block,
                rule=rule,
                concept=names[0] + "_CHANGE",
                scope=scope,
                period=period,
                period_semantics=semantics,
                value=changes[0],
                comparator="PRIOR_PERIOD",
                inherited=inherited,
            ),
        )

    if rule.frame is SemanticFrame.RANGE_GUIDANCE:
        relation = _relation_position(block.text, rule.relation_words)
        if relation is None or len(candidates) < 2:
            return None
        candidates = _concept_value_candidates(names, candidates)
        same_kind = tuple(item for item in candidates if item.kind is candidates[0].kind)
        if len(names) != 1 or len(same_kind) != 2:
            return ()
        low, high = sorted((same_kind[0].value, same_kind[1].value))
        midpoint = QuantityMention(
            same_kind[0].kind,
            (low + high) / 2.0,
            same_kind[0].unit,
            f"{same_kind[0].raw}..{same_kind[1].raw}",
            same_kind[0].char_start,
            same_kind[1].char_end,
        )
        return (
            _frame(
                document=document,
                block=block,
                rule=rule,
                concept=names[0] + "_GUIDANCE",
                scope=scope,
                period=period,
                period_semantics=PeriodSemantics.FORECAST,
                value=midpoint,
                inherited=inherited,
                lower_value=low,
                upper_value=high,
            ),
        )

    if rule.frame is SemanticFrame.NOT_EXPECTED:
        candidates = _concept_value_candidates(names, candidates)
        if len(names) != 1 or len(candidates) != 1:
            return None if not candidates else ()
        return (
            _frame(
                document=document,
                block=block,
                rule=rule,
                concept=names[0],
                scope=scope,
                period=period,
                period_semantics=PeriodSemantics.FORECAST,
                value=candidates[0],
                inherited=inherited,
                context_trace={"antecedent_concept": names[0] if inherited else None},
            ),
        )

    if rule.frame is SemanticFrame.COMPARATIVE:
        years = extract_years(block.text)
        explicit_comparator = any(
            cue in block.text.casefold()
            for cue in ("versus", "compared with", "compared to", "prior year")
        ) or len(years) >= 2
        candidates = _concept_value_candidates(
            names,
            candidates,
            fail_on_mismatch=explicit_comparator,
        )
        if not candidates:
            qualitative_cues = ("improved", "remained robust")
            if not any(cue in block.text.casefold() for cue in qualitative_cues):
                return None
            return tuple(
                _frame(
                    document=document,
                    block=block,
                    rule=rule,
                    concept=name,
                    scope=scope,
                    period=period,
                    period_semantics=semantics,
                    value=None,
                    comparator="PRIOR_YEAR",
                    inherited=inherited,
                )
                for name in names
            )
        if len(names) != 1:
            return ()
        same_kind = tuple(item for item in candidates if item.kind is candidates[0].kind)
        if len(same_kind) != 2 or len(years) < 2:
            return None
        current, prior = same_kind
        return (
            _frame(
                document=document,
                block=block,
                rule=rule,
                concept=names[0],
                scope=scope,
                period=str(years[0][0]),
                period_semantics=PeriodSemantics.END_OF_PERIOD,
                value=current,
                comparator="PRIOR_YEAR",
                inherited=inherited,
                context_trace={"paired_period": str(years[1][0])},
            ),
            _frame(
                document=document,
                block=block,
                rule=rule,
                concept="PRIOR_YEAR_" + names[0],
                scope=scope,
                period=str(years[1][0]),
                period_semantics=PeriodSemantics.END_OF_PERIOD,
                value=prior,
                comparator=None,
                inherited=inherited,
                context_trace={"paired_period": str(years[0][0])},
            ),
        )

    if rule.qualitative:
        if not names:
            return None
        dependency_validated = bool(
            backend is not None
            and rule.frame is SemanticFrame.CAUSE_EFFECT
            and backend.dependency_relation(block.text, concepts)
        )
        return tuple(
            _frame(
                document=document,
                block=block,
                rule=rule,
                concept=name,
                scope=scope,
                period=period,
                period_semantics=semantics,
                value=None,
                inherited=inherited,
                context_trace={"related_concepts": list(names)},
                method_override=(
                    ExtractionMethod.DEPENDENCY_RULE
                    if dependency_validated
                    else None
                ),
            )
            for name in names
        )

    candidates = _concept_value_candidates(names, candidates)
    if len(names) != 1 or len(candidates) != 1:
        return None if not candidates else ()
    return (
        _frame(
            document=document,
            block=block,
            rule=rule,
            concept=names[0],
            scope=scope,
            period=period,
            period_semantics=semantics,
            value=candidates[0],
            inherited=inherited,
        ),
    )


def _frame_facts(frame: KPIFrame) -> tuple[FactIR, ...]:
    if frame.verification_status is not VerificationStatus.VERIFIED:
        return ()
    if frame.value is None:
        return ()
    common = {
        "entity": frame.entity,
        "scope": frame.scope,
        "period": frame.period,
        "origin": (
            FactOrigin.FORECAST
            if frame.period_semantics is PeriodSemantics.FORECAST
            else FactOrigin.OBSERVED
        ),
        "relation": RelationType.STRUCTURAL,
        "evidence": (
            EvidenceStatus.PROPOSED
            if frame.period_semantics is PeriodSemantics.FORECAST
            else EvidenceStatus.PIT
        ),
        "authority": min(frame.authority, AuthorityLevel.RESEARCH_EVIDENCE),
        "source": frame.source,
    }
    trace = {
        "frame": frame.frame.value,
        "source_span": {
            "start": frame.source_span.char_start,
            "end": frame.source_span.char_end,
            "literal": frame.source_span.literal,
        },
        "polarity": {
            "positive": frame.polarity.positive,
            "cue": frame.polarity.cue,
        },
        "qualifier": frame.qualifier.cues,
        "change": frame.change,
        "change_unit": frame.change_unit,
        "comparator": frame.comparator,
        "extraction_confidence": frame.extraction_confidence,
        "extraction_method": frame.extraction_method.value,
        "context": frame.context_trace,
    }
    if frame.lower_value is not None and frame.upper_value is not None:
        return tuple(
            FactIR(
                metric=f"{frame.concept}_{label}",
                unit=str(frame.unit),
                value=value,
                lineage=LineageRef(
                    frame.rule_id,
                    frame.rule_version,
                    match_trace=trace,
                    capture_trace={"range_endpoint": label, "value": value},
                ),
                **common,
            )
            for label, value in (
                ("LOW", frame.lower_value),
                ("HIGH", frame.upper_value),
            )
        )
    return (
        FactIR(
            metric=frame.concept,
            unit=str(frame.unit),
            value=float(frame.value),
            lineage=LineageRef(
                frame.rule_id,
                frame.rule_version,
                match_trace=trace,
                capture_trace={"value": frame.value},
            ),
            **common,
        ),
    )


def _frame_claim(frame: KPIFrame) -> EvidenceClaimIR | None:
    if frame.value is not None or frame.verification_status is not VerificationStatus.VERIFIED:
        return None
    base = frame.concept.removeprefix("PRIOR_YEAR_").removesuffix("_NOT_EXPECTED")
    try:
        claim_type = definition_for(base).claim_type
    except KeyError:
        claim_type = ClaimType.THESIS_EVIDENCE
    folded = frame.source_span.literal.casefold()
    if not frame.polarity.positive:
        predicate = "MATERIAL_EFFECT_NEGATED"
        direction = "NEGATED"
    elif "improved" in folded:
        predicate = "IMPROVED"
        direction = "IMPROVING"
    elif "robust" in folded:
        predicate = "REMAINED_ROBUST"
        direction = "STRONG"
    else:
        predicate = frame.frame.value
        direction = None
    claim_digest = sha256(
        (
            frame.source.sha256
            + frame.rule_id
            + str(frame.source_span.char_start)
            + frame.concept
        ).encode("utf-8")
    ).hexdigest()[:20]
    return EvidenceClaimIR(
        claim_id=f"text-ie-{claim_digest}",
        entity=frame.entity,
        scope=frame.scope,
        period=frame.period,
        claim_type=claim_type,
        subject=frame.concept,
        predicate=predicate,
        direction=direction,
        source=frame.source,
        source_span=frame.source_span,
        status=ClaimStatus.VERIFIED,
        authority=min(frame.authority, AuthorityLevel.RESEARCH_DIAGNOSTIC),
        extraction_method=frame.extraction_method,
        verified_by="DETERMINISTIC_TEXT_IE_VALIDATOR",
    )


def _frame_relations(
    frames: tuple[KPIFrame, ...],
    rules: tuple[TextRuleIR, ...],
) -> tuple[KPIRelationIR, ...]:
    rule_map = {rule.rule_id: rule for rule in rules}
    grouped: dict[tuple[str, int, int, str], list[KPIFrame]] = {}
    for frame in frames:
        rule = rule_map[frame.rule_id]
        if not rule.relation or frame.frame is not SemanticFrame.CAUSE_EFFECT:
            continue
        key = (
            frame.source.sha256,
            frame.source_span.char_start,
            frame.source_span.char_end,
            frame.rule_id,
        )
        grouped.setdefault(key, []).append(frame)
    relations: list[KPIRelationIR] = []
    reverse_cues = ("due to", "because", "driven by", "resulted from")
    for group in grouped.values():
        concepts = tuple(dict.fromkeys(frame.concept for frame in group))
        if len(concepts) != 2:
            continue
        literal = group[0].source_span.literal.casefold()
        cause, effect = (
            (concepts[1], concepts[0])
            if any(cue in literal for cue in reverse_cues)
            else (concepts[0], concepts[1])
        )
        rule = rule_map[group[0].rule_id]
        relations.append(
            KPIRelationIR(
                cause=cause,
                effect=effect,
                relation_type=str(rule.relation),
                direction=("POSITIVE" if group[0].polarity.positive else "NEGATED"),
                source=group[0].source,
                source_span=group[0].source_span,
                rule_id=group[0].rule_id,
                rule_version=group[0].rule_version,
                extraction_confidence=min(frame.extraction_confidence for frame in group),
                authority=AuthorityLevel.RESEARCH_DIAGNOSTIC,
                verification_status=VerificationStatus.VERIFIED,
            )
        )
    return tuple(relations)


def extract_text_kpis(
    document: CanonicalDocument,
    rules: tuple[TextRuleIR, ...] = DEFAULT_TEXT_RULES,
    backend: SemanticMatcherBackend | None = None,
) -> TextExtractionResult:
    if backend is None:
        backend = default_spacy_backend()
    stack = ContextStack()
    frames: list[KPIFrame] = []
    reviews: list[ReviewItem] = []
    for block in document_text_blocks(document):
        if not narrative_candidate(block).accepted:
            continue
        direct_mentions = find_concepts(block.text)
        quantities = extract_quantities(block.text)
        for rule in rules:
            mentions = direct_mentions
            inherited = False
            if not mentions and rule.allow_context_metric:
                mentions = stack.resolve_concepts(block, direct_mentions)
                inherited = bool(mentions)
            try:
                matched = _match_rule(
                    document,
                    block,
                    rule,
                    mentions,
                    quantities,
                    inherited=inherited,
                    scope=stack.resolve_scope(block),
                    backend=backend,
                )
            except FrameValidationError as exc:
                reviews.append(
                    ReviewItem(
                        sentence_index=block.sentence_index,
                        rule_id=rule.rule_id,
                        status="REVIEW_VALIDATION_FAILED",
                        reason=str(exc),
                        source_span=_source_span(block),
                    )
                )
                break
            if matched is None:
                continue
            if not matched:
                if rule.ambiguity is not AmbiguityPolicy.SKIP:
                    reviews.append(
                        ReviewItem(
                            sentence_index=block.sentence_index,
                            rule_id=rule.rule_id,
                            status=(
                                "FAIL_AMBIGUOUS"
                                if rule.ambiguity is AmbiguityPolicy.FAIL
                                else "REVIEW_AMBIGUOUS"
                            ),
                            reason="No unique semantic-frame assignment",
                            source_span=_source_span(block),
                            candidates=tuple(
                                sorted(
                                    {item.concept for item in mentions}
                                    | {item.raw for item in quantities}
                                )
                            ),
                        )
                    )
                break
            frames.extend(matched)
            primary = matched[0]
            base_concept = str(
                primary.context_trace.get("antecedent_concept")
                or primary.concept.removeprefix("PRIOR_YEAR_").removesuffix(
                    rule.output_metric_suffix
                )
            )
            stack.update(block, base_concept, primary.scope, primary.period)
            break
    facts = tuple(fact for frame in frames for fact in _frame_facts(frame))
    claims = tuple(
        claim
        for frame in frames
        if (claim := _frame_claim(frame)) is not None
    )
    relations = _frame_relations(tuple(frames), rules)
    return TextExtractionResult(
        tuple(frames),
        facts,
        claims,
        relations,
        tuple(reviews),
        backend.name if backend is not None else "BUILTIN_SPAN_FALLBACK",
    )
