from __future__ import annotations

from dataclasses import replace
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
from .context_validation import ContextBindingError, validate_context_binding
from .document import document_text_blocks
from .dsl import TextRuleIR, compile_text_rule_file
from .model import (
    AmbiguityPolicy,
    AbstentionItem,
    FactTier,
    KPIFrame,
    KPIRelationIR,
    PeriodSemantics,
    Polarity,
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
from .semantic_binding import bind_metric_values
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
    folded = text.casefold()
    positions: list[int] = []
    for trigger in triggers:
        needle = trigger.casefold()
        cursor = 0
        while (position := folded.find(needle, cursor)) >= 0:
            left_ok = position == 0 or not folded[position - 1].isalnum()
            end = position + len(needle)
            right_ok = end == len(folded) or not folded[end].isalnum()
            if left_ok and right_ok:
                positions.append(position)
                break
            cursor = position + 1
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


def _range_quantity_pair(
    text: str,
    candidates: tuple[QuantityMention, ...],
) -> tuple[QuantityMention, QuantityMention] | tuple[()]:
    """Return one structurally adjacent range pair, otherwise abstain.

    Merely finding two quantities in an IR text block is insufficient: large
    flattened blocks commonly contain unrelated KPIs.  This bounded relation
    check is the semantic equivalent of a labeled ``low connector high`` DSL
    pattern.
    """

    ordered = sorted(candidates, key=lambda item: item.char_start)
    pairs: list[tuple[QuantityMention, QuantityMention]] = []
    for left, right in zip(ordered, ordered[1:]):
        if left.kind is not right.kind or left.unit != right.unit:
            continue
        connector = text[left.char_end : right.char_start]
        direct = re.fullmatch(
            r"\s*(?:to|through|[-–—])\s*",
            connector,
            re.IGNORECASE,
        )
        between = re.fullmatch(r"\s*and\s*", connector, re.IGNORECASE) and re.search(
            r"\bbetween\s*$",
            text[max(0, left.char_start - 32) : left.char_start],
            re.IGNORECASE,
        )
        if direct or between:
            pairs.append((left, right))
    return pairs[0] if len(pairs) == 1 else ()


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
    base_concept = concept.removeprefix("PRIOR_YEAR_")
    for suffix in (rule.output_metric_suffix, "_GUIDANCE", "_CHANGE"):
        if suffix:
            base_concept = base_concept.removesuffix(suffix)
    tier = definition_for(base_concept).tier
    selected_polarity = polarity(block.text)
    if "resolve_polarity" in rule.operations and context_trace:
        trigger_roles = dict(context_trace.get("semantic_roles", {})).get(
            "trigger", []
        )
        if trigger_roles:
            trigger_role = trigger_roles[0]
            cue = str(trigger_role.get("value", ""))
            folded_cue = cue.casefold()
            negative = folded_cue.startswith(
                (
                    "contract",
                    "decrease",
                    "decline",
                    "fall",
                    "headwind",
                    "lower",
                    "negative",
                    "reduce",
                    "down",
                )
            )
            selected_polarity = Polarity(
                positive=not negative,
                cue=cue,
                cue_start=int(trigger_role["start"]),
                cue_end=int(trigger_role["end"]),
            )
    if "resolve_parenthesized_sign" in rule.operations and value and value.value < 0:
        selected_polarity = Polarity(
            positive=False,
            cue="PARENTHESIZED_NEGATIVE",
            cue_start=value.char_start,
            cue_end=value.char_end,
        )
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
        polarity=selected_polarity,
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
        tier=tier,
    )
    semantic = validate_kpi_frame(proposed, document)
    trace_roles = dict((context_trace or {}).get("semantic_roles", {}))
    trace_backends = tuple((context_trace or {}).get("matcher_trace", ()))
    value_roles = tuple(
        role
        for label in (
            "value",
            "current",
            "change",
            "low",
            "high",
            "midpoint",
            "tolerance",
            "baseline",
            "prior",
        )
        for role in trace_roles.get(label, ())
    )
    metric_roles = tuple(
        role
        for label in ("metric", "cause", "effect")
        for role in trace_roles.get(label, ())
    )
    labeled_role_binding = bool(
        value is not None
        and value_roles
        and metric_roles
        and "bind_labeled_roles" in rule.operations
        and "SPACY_MATCHER" in trace_backends
        and (
            any(
                int(role["start"]) <= value.char_start
                and value.char_end <= int(role["end"])
                for role in value_roles
            )
            or (
                min(int(role["start"]) for role in value_roles)
                <= value.char_start
                and value.char_end
                <= max(int(role["end"]) for role in value_roles)
            )
        )
    )
    if labeled_role_binding:
        dependency_proved = "SPACY_DEPENDENCY_MATCHER" in trace_backends
        return replace(
            semantic,
            context_trace={
                **semantic.context_trace,
                "context_validation": {
                    "reason": (
                        "SPACY_DEPENDENCY_ROLE_BINDING"
                        if dependency_proved
                        else "SPACY_BOUNDED_LABELED_ROLE_BINDING"
                    ),
                    "metric_span": (
                        int(metric_roles[0]["start"]),
                        int(metric_roles[0]["end"]),
                    ),
                    "value_span": (value.char_start, value.char_end),
                },
            },
        )
    decision = validate_context_binding(
        semantic,
        block,
        find_concepts(block.text),
        value,
        inherited=inherited,
    )
    if not decision.accepted:
        raise ContextBindingError(decision)
    return replace(
        semantic,
        context_trace={
            **semantic.context_trace,
            "context_validation": {
                "reason": decision.reason,
                "metric_span": decision.metric_span,
                "value_span": decision.value_span,
            },
        },
    )


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
    pattern_match = ()
    if rule.pattern:
        pattern_match = (
            backend.match_pattern(rule, block.text, concepts, quantities)
            if backend is not None
            else match_sequence_pattern(rule, block.text, concepts, quantities)
        )
        if pattern_match is None:
            return None
    roles: dict[str, tuple[object, ...]] = {}
    for label in dict.fromkeys(span.label for span in pattern_match):
        roles[label] = tuple(span for span in pattern_match if span.label == label)
    trigger_roles = roles.get("trigger", ())
    trigger = (
        int(trigger_roles[0].char_start)
        if trigger_roles
        else trigger
    )

    role_concepts = tuple(
        dict.fromkeys(
            str(span.value)
            for label in ("metric", "cause", "effect")
            for span in roles.get(label, ())
        )
    )
    pattern_start = min(
        (span.char_start for span in pattern_match),
        default=0,
    )
    pattern_end = max(
        (span.char_end for span in pattern_match),
        default=len(block.text),
    )
    competing_concepts = tuple(
        item
        for item in concepts
        if pattern_start <= getattr(item, "char_start") < pattern_end
        and getattr(item, "concept") not in role_concepts
    )
    names = tuple(dict.fromkeys(getattr(item, "concept") for item in concepts))
    if role_concepts and not competing_concepts:
        names = role_concepts
    if rule.concepts:
        names = tuple(name for name in names if name in rule.concepts)
    if not rule.qualitative:
        names = tuple(name for name in names if definition_for(name).quantity_kinds)
    if rule.require_metric and not names:
        return None
    candidates = _quantity_candidates(quantities, rule)

    number_words = {
        "zero": 0.0,
        "one": 1.0,
        "two": 2.0,
        "three": 3.0,
        "four": 4.0,
        "five": 5.0,
        "six": 6.0,
        "seven": 7.0,
        "eight": 8.0,
        "nine": 9.0,
        "ten": 10.0,
        "eleven": 11.0,
        "twelve": 12.0,
        "thirteen": 13.0,
        "fourteen": 14.0,
        "fifteen": 15.0,
        "sixteen": 16.0,
        "seventeen": 17.0,
        "eighteen": 18.0,
        "nineteen": 19.0,
        "twenty": 20.0,
    }

    def materialize_quantity(span: object) -> QuantityMention | None:
        if len(rule.quantity_kinds) == 1:
            kind = rule.quantity_kinds[0]
        elif "normalize_percent" in rule.operations:
            kind = QuantityKind.PERCENT
        elif "normalize_count" in rule.operations:
            kind = QuantityKind.COUNT
        elif "normalize_money" in rule.operations:
            kind = QuantityKind.MONEY
        else:
            return None
        raw = block.text[span.char_start : span.char_end]
        folded = raw.casefold().strip()
        normalized = (
            folded.replace(",", "")
            .replace("$", "")
            .replace("%", "")
            .replace("(", "")
            .replace(")", "")
            .strip()
        )
        value = number_words.get(normalized)
        if value is None:
            numeric = normalized.split()[0] if normalized.split() else ""
            try:
                value = float(numeric)
            except ValueError:
                return None
        if "billion" in folded or folded.endswith("bn"):
            value *= 1_000_000_000
        elif "million" in folded or folded.endswith("mm"):
            value *= 1_000_000
        if "resolve_parenthesized_sign" in rule.operations:
            left = block.text[max(0, span.char_start - 1) : span.char_start]
            right = block.text[span.char_end : span.char_end + 1]
            if left == "(" and right == ")":
                value = -abs(value)
        unit = {
            QuantityKind.MONEY: "USD",
            QuantityKind.PERCENT: "PERCENT",
            QuantityKind.BASIS_POINTS: "BASIS_POINTS",
            QuantityKind.COUNT: "COUNT",
            QuantityKind.RATE: "RATE",
            QuantityKind.PRICE: "USD",
        }[kind]
        return QuantityMention(
            kind=kind,
            value=value,
            unit=unit,
            raw=raw,
            char_start=span.char_start,
            char_end=span.char_end,
        )

    def role_quantities(*labels: str) -> tuple[QuantityMention, ...]:
        spans = tuple(span for label in labels for span in roles.get(label, ()))
        output: list[QuantityMention] = []
        for span in spans:
            matched = next(
                (
                    item
                    for item in candidates
                    if span.char_start <= item.char_start
                    and item.char_end <= span.char_end
                ),
                None,
            )
            quantity = matched or materialize_quantity(span)
            if quantity is not None and not any(
                existing.char_start == quantity.char_start
                and existing.char_end == quantity.char_end
                for existing in output
            ):
                output.append(quantity)
        return tuple(output)

    semantic_trace = {
        "semantic_roles": {
            label: [
                {
                    "start": span.char_start,
                    "end": span.char_end,
                    "value": span.value,
                }
                for span in spans
            ]
            for label, spans in roles.items()
        },
        "matcher_trace": list(
            getattr(backend, "last_match_trace", ())
            if backend is not None and roles
            else ()
        ),
    }
    dependency_matched = "SPACY_DEPENDENCY_MATCHER" in semantic_trace["matcher_trace"]
    semantic_method = (
        ExtractionMethod.DEPENDENCY_RULE if dependency_matched else None
    )

    def traced(extra: dict[str, object] | None = None) -> dict[str, object]:
        if not roles:
            return extra or {}
        return {**semantic_trace, **(extra or {})}

    period, semantics = resolve_period(block, rule.frame)
    if period == "UNRESOLVED":
        return None

    if rule.frame is SemanticFrame.CHANGE_TO:
        relation_roles = roles.get("relation", ())
        relation = (
            int(relation_roles[0].char_start)
            if relation_roles
            else _relation_position(block.text, rule.relation_words)
        )
        if relation is None and roles.get("value") and roles.get("change"):
            relation = trigger
        if relation is None:
            return None
        labeled_values = role_quantities("value")
        values = _concept_value_candidates(
            names,
            labeled_values
            or tuple(item for item in candidates if item.char_start > relation),
        )
        labeled_changes = role_quantities("change")
        changes = labeled_changes or tuple(
            item
            for item in quantities
            if item.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
            and item.char_end <= relation
        )
        if len(names) != 1 or len(values) != 1 or len(changes) > 1:
            return None if not values else ()
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
                context_trace=traced(),
                method_override=semantic_method,
            ),
        )

    if rule.frame is SemanticFrame.CHANGE_BY:
        relation_roles = roles.get("relation", ())
        relation = (
            int(relation_roles[0].char_start)
            if relation_roles
            else _relation_position(block.text, rule.relation_words)
        )
        if relation is None:
            # English commonly omits ``by``: "revenue grew 9 percent".
            relation = trigger
        change_labels = (
            ("change", "value", "current", "prior")
            if "emit_each_value" in rule.operations
            else ("change", "value")
        )
        changes = role_quantities(*change_labels) or tuple(
            item
            for item in candidates
            if relation is not None and item.char_start > relation
        )
        if (
            "emit_each_value" in rule.operations
            and relation is not None
            and len(names) == 1
            and changes
        ):
            return tuple(
                _frame(
                    document=document,
                    block=block,
                    rule=rule,
                    concept=(
                        names[0]
                        if "emit_base_metric" in rule.operations
                        else names[0] + "_CHANGE"
                    ),
                    scope=scope,
                    period=period,
                    period_semantics=semantics,
                    value=change,
                    comparator="PRIOR_PERIOD",
                    inherited=inherited,
                    context_trace=traced(),
                    method_override=semantic_method,
                )
                for change in changes
            )
        if relation is None or len(names) != 1 or len(changes) != 1:
            return None if not changes else ()
        return (
            _frame(
                document=document,
                block=block,
                rule=rule,
                concept=(
                    names[0]
                    if "emit_base_metric" in rule.operations
                    else names[0] + "_CHANGE"
                ),
                scope=scope,
                period=period,
                period_semantics=semantics,
                value=changes[0],
                comparator="PRIOR_PERIOD",
                inherited=inherited,
                context_trace=traced(),
                method_override=semantic_method,
            ),
        )

    if rule.frame is SemanticFrame.RANGE_GUIDANCE:
        relation_roles = tuple(
            role
            for label in ("relation", "dash", "to", "between")
            for role in roles.get(label, ())
        )
        relation = (
            int(relation_roles[0].char_start)
            if relation_roles
            else _relation_position(block.text, rule.relation_words)
        )
        if "derive_relative_range" in rule.operations:
            midpoint_roles = role_quantities("midpoint")
            tolerance_roles = role_quantities("tolerance")
            if (
                len(names) != 1
                or len(midpoint_roles) != 1
                or len(tolerance_roles) != 1
                or tolerance_roles[0].kind is not QuantityKind.PERCENT
                or tolerance_roles[0].value < 0
            ):
                return ()
            midpoint = midpoint_roles[0]
            tolerance = tolerance_roles[0].value / 100.0
            low = midpoint.value * (1.0 - tolerance)
            high = midpoint.value * (1.0 + tolerance)
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
                    context_trace=traced(
                        {"relative_tolerance_percent": tolerance_roles[0].value}
                    ),
                    method_override=semantic_method,
                ),
            )
        labeled_pair = role_quantities("low", "high")
        if relation is None or (len(candidates) < 2 and len(labeled_pair) < 2):
            return None
        candidates = (
            labeled_pair
            if labeled_pair
            and all(
                item.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
                for item in labeled_pair
            )
            else _concept_value_candidates(names, labeled_pair or candidates)
        )
        pair = (
            labeled_pair
            if len(labeled_pair) == 2
            else _range_quantity_pair(block.text, candidates)
        )
        if len(names) != 1 or not pair:
            return ()
        low, high = sorted((pair[0].value, pair[1].value))
        midpoint = QuantityMention(
            pair[0].kind,
            (low + high) / 2.0,
            pair[0].unit,
            f"{pair[0].raw}..{pair[1].raw}",
            pair[0].char_start,
            pair[1].char_end,
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
                context_trace=traced(),
                method_override=semantic_method,
            ),
        )

    if rule.frame is SemanticFrame.NOT_EXPECTED:
        candidates = _concept_value_candidates(
            names,
            role_quantities("value") or candidates,
        )
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
                context_trace=traced(
                    {"antecedent_concept": names[0] if inherited else None}
                ),
                method_override=semantic_method,
            ),
        )

    if rule.frame is SemanticFrame.COMPARATIVE:
        years = extract_years(block.text)
        labeled_current = role_quantities("value", "current")
        labeled_prior = role_quantities("prior", "comparator_value")
        if (
            "emit_each_value" in rule.operations
            and len(names) == 1
            and labeled_current
            and len(labeled_current) == len(labeled_prior)
            and all(
                current.kind is prior.kind
                for current, prior in zip(labeled_current, labeled_prior)
            )
        ):
            return tuple(
                frame
                for prefix, values in (
                    ("", labeled_current),
                    ("PRIOR_YEAR_", labeled_prior),
                )
                for frame in (
                    _frame(
                        document=document,
                        block=block,
                        rule=rule,
                        concept=prefix + names[0],
                        scope=scope,
                        period=period,
                        period_semantics=semantics,
                        value=value,
                        comparator="PRIOR_YEAR" if not prefix else None,
                        inherited=inherited,
                        context_trace=traced(),
                        method_override=semantic_method,
                    )
                    for value in values
                )
            )
        if (
            len(names) == 1
            and len(labeled_current) == 1
            and len(labeled_prior) == 1
            and labeled_current[0].kind is labeled_prior[0].kind
        ):
            return (
                _frame(
                    document=document,
                    block=block,
                    rule=rule,
                    concept=names[0],
                    scope=scope,
                    period=period,
                    period_semantics=semantics,
                    value=labeled_current[0],
                    comparator="PRIOR_YEAR",
                    inherited=inherited,
                    context_trace=traced(),
                    method_override=semantic_method,
                ),
                _frame(
                    document=document,
                    block=block,
                    rule=rule,
                    concept="PRIOR_YEAR_" + names[0],
                    scope=scope,
                    period=period,
                    period_semantics=semantics,
                    value=labeled_prior[0],
                    comparator=None,
                    inherited=inherited,
                    context_trace=traced(),
                    method_override=semantic_method,
                ),
            )
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

    if rule.frame is SemanticFrame.COMPOSITION:
        percentages = role_quantities("value") or tuple(
            item for item in quantities if item.kind is QuantityKind.PERCENT
        )
        if len(names) != 1 or len(percentages) != 1:
            return None if not percentages else ()
        return (
            _frame(
                document=document,
                block=block,
                rule=rule,
                concept=names[0],
                scope=scope,
                period=period,
                period_semantics=semantics,
                value=percentages[0],
                inherited=inherited,
                context_trace=traced(),
                method_override=semantic_method,
            ),
        )

    if rule.qualitative:
        if not names:
            return None
        # A causal frame has exactly two semantic roles.  Flattened filing or
        # IR blocks can mention several unrelated KPIs; emitting all pairwise
        # combinations would manufacture evidence.  Fail closed to review.
        if rule.frame is SemanticFrame.CAUSE_EFFECT and len(names) < 2:
            return None
        if rule.frame is SemanticFrame.CAUSE_EFFECT and len(names) > 2:
            return ()
        dependency_validated = dependency_matched or bool(
            backend is not None
            and rule.frame is SemanticFrame.CAUSE_EFFECT
            and backend.dependency_relation(block.text, concepts)
        )
        if rule.frame is SemanticFrame.CAUSE_EFFECT and not dependency_validated:
            return ()
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
                context_trace=traced({"related_concepts": list(names)}),
                method_override=(
                    ExtractionMethod.DEPENDENCY_RULE
                    if dependency_validated
                    else None
                ),
            )
            for name in names
        )

    if rule.output_metric_suffix.endswith("_GUIDANCE"):
        labeled_values = role_quantities("value")
        if len(names) == 1 and len(labeled_values) == 1:
            return (
                _frame(
                    document=document,
                    block=block,
                    rule=rule,
                    concept=names[0],
                    scope=scope,
                    period=period,
                    period_semantics=PeriodSemantics.FORECAST,
                    value=labeled_values[0],
                    inherited=inherited,
                    context_trace=traced(),
                    method_override=semantic_method,
                ),
            )
        bindings = bind_metric_values(
            block.text,
            tuple(item for item in concepts if getattr(item, "concept") in names),
            candidates,
            forward_only=True,
        )
        if bindings:
            return tuple(
                _frame(
                    document=document,
                    block=block,
                    rule=rule,
                    concept=binding.metric.concept,
                    scope=scope,
                    period=period,
                    period_semantics=PeriodSemantics.FORECAST,
                    value=binding.value,
                    inherited=inherited,
                    context_trace=traced({"binding_order": binding.relation}),
                )
                for binding in bindings
            )
        _concept_value_candidates(names, candidates)
        return None

    if rule.rule_id == "semantic.absolute":
        labeled_values = role_quantities("value")
        if len(names) == 1 and len(labeled_values) == 1:
            return (
                _frame(
                    document=document,
                    block=block,
                    rule=rule,
                    concept=names[0],
                    scope=scope,
                    period=period,
                    period_semantics=semantics,
                    value=labeled_values[0],
                    inherited=inherited,
                    context_trace=traced(),
                    method_override=semantic_method,
                ),
            )
        bindings = bind_metric_values(
            block.text,
            tuple(item for item in concepts if getattr(item, "concept") in names),
            candidates,
        )
        if bindings:
            return tuple(
                _frame(
                    document=document,
                    block=block,
                    rule=rule,
                    concept=binding.metric.concept,
                    scope=scope,
                    period=period,
                    period_semantics=semantics,
                    value=binding.value,
                    inherited=inherited,
                    context_trace=traced({"binding_order": binding.relation}),
                )
                for binding in bindings
            )

    value_labels = (
        ("value", "current", "prior")
        if "emit_each_value" in rule.operations
        else ("value",)
    )
    candidates = _concept_value_candidates(
        names,
        role_quantities(*value_labels) or candidates,
    )
    if (
        "emit_each_value" in rule.operations
        and len(names) == 1
        and candidates
    ):
        return tuple(
            _frame(
                document=document,
                block=block,
                rule=rule,
                concept=names[0],
                scope=scope,
                period=period,
                period_semantics=semantics,
                value=value,
                inherited=inherited,
                context_trace=traced(),
                method_override=semantic_method,
            )
            for value in candidates
        )
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
            context_trace=traced(),
            method_override=semantic_method,
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
    abstentions: list[AbstentionItem] = []
    for block in document_text_blocks(document):
        direct_mentions = find_concepts(block.text)
        retrieval = narrative_candidate(block)
        if not retrieval.accepted:
            if direct_mentions:
                tier = (
                    FactTier.CRITICAL
                    if any(definition_for(item.concept).tier is FactTier.CRITICAL for item in direct_mentions)
                    else FactTier.NARRATIVE
                )
                abstentions.append(
                    AbstentionItem(
                        sentence_index=block.sentence_index,
                        rule_id="retrieval.narrative_candidate",
                        reason=retrieval.reason,
                        failure_class="TABLE_TEXT_BOUNDARY",
                        source_span=_source_span(block),
                        tier=tier,
                        candidates=tuple(sorted({item.concept for item in direct_mentions})),
                    )
                )
            continue
        quantities = extract_quantities(block.text)
        handled = False
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
            except ContextBindingError as exc:
                decision = exc.decision
                abstentions.append(
                    AbstentionItem(
                        sentence_index=block.sentence_index,
                        rule_id=rule.rule_id,
                        reason=decision.reason,
                        failure_class=decision.failure_class,
                        source_span=_source_span(block),
                        tier=decision.tier,
                        candidates=tuple(
                            sorted(
                                {item.concept for item in mentions}
                                | {item.raw for item in quantities}
                            )
                        ),
                    )
                )
                handled = True
                break
            except FrameValidationError as exc:
                tier = (
                    FactTier.CRITICAL
                    if any(definition_for(item.concept).tier is FactTier.CRITICAL for item in mentions)
                    else FactTier.NARRATIVE
                )
                reviews.append(
                    ReviewItem(
                        sentence_index=block.sentence_index,
                        rule_id=rule.rule_id,
                        status="REVIEW_VALIDATION_FAILED",
                        reason=str(exc),
                        source_span=_source_span(block),
                        tier=tier,
                    )
                )
                handled = True
                break
            if matched is None:
                continue
            handled = True
            if not matched:
                if rule.ambiguity is not AmbiguityPolicy.SKIP:
                    tier = (
                        FactTier.CRITICAL
                        if any(definition_for(item.concept).tier is FactTier.CRITICAL for item in mentions)
                        else FactTier.NARRATIVE
                    )
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
                            tier=tier,
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
        if direct_mentions and not handled:
            tier = (
                FactTier.CRITICAL
                if any(definition_for(item.concept).tier is FactTier.CRITICAL for item in direct_mentions)
                else FactTier.NARRATIVE
            )
            abstentions.append(
                AbstentionItem(
                    sentence_index=block.sentence_index,
                    rule_id="semantic.no_rule_match",
                    reason="NO_SAFE_SEMANTIC_RULE_MATCH",
                    failure_class="FALSE_KPI_FRAME",
                    source_span=_source_span(block),
                    tier=tier,
                    candidates=tuple(sorted({item.concept for item in direct_mentions})),
                )
            )
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
        tuple(abstentions),
        backend.name if backend is not None else "BUILTIN_SPAN_FALLBACK",
    )
