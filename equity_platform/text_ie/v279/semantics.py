from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from equity_platform.documents import CanonicalDocument
from equity_platform.ir import AuthorityLevel, ExtractionMethod, SourceSpan
from equity_platform.paths import PROJECT_ROOT

from ..context import qualifier, resolve_period
from ..dsl import compile_text_rule_file
from ..model import (
    FactTier,
    KPIFrame,
    PeriodSemantics,
    Polarity,
    QuantityKind,
    QuantityMention,
    SemanticFrame,
    TextBlock,
    VerificationStatus,
)
from ..ontology import definition_for, resolve_scope
from ..validation import FrameValidationError, validate_kpi_frame
from ..v24.model import RecallCandidate
from ..v278.semantics import (
    semantic_backend_v278,
    semantic_concepts_v278,
    semantic_quantities_v278,
)


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v279_semantic_ownership.arc"
V279_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V279_RULES}


def _base(concept: str) -> str:
    result = concept.removeprefix("PRIOR_YEAR_")
    while True:
        prior = result
        result = result.removesuffix("_GUIDANCE").removesuffix("_CHANGE")
        if result == prior:
            return result


@lru_cache(maxsize=1)
def semantic_backend_v279():
    return semantic_backend_v278()


def semantic_concepts_v279(text: str, backend=None):
    return semantic_concepts_v278(text, backend or semantic_backend_v279())


def _numeric_token_value(raw: str) -> float | None:
    normalized = raw.replace(",", "").strip()
    try:
        return float(normalized)
    except ValueError:
        return None


def semantic_quantities_v279(
    text: str,
    backend=None,
) -> tuple[QuantityMention, ...]:
    selected = backend or semantic_backend_v279()
    output = list(semantic_quantities_v278(text, selected))
    occupied = {(item.char_start, item.char_end) for item in output}
    tokens = tuple(token for token in selected.parse(text) if not token.is_space)
    for index, token in enumerate(tokens):
        if not token.like_num:
            continue
        point_index = index + 1
        if point_index < len(tokens) and tokens[point_index].text == "-":
            point_index += 1
        if point_index >= len(tokens) or tokens[point_index].lemma_.casefold() != "point":
            continue
        value = _numeric_token_value(token.text)
        if value is None:
            continue
        end = tokens[point_index].idx + len(tokens[point_index].text)
        span = (token.idx, end)
        if any(start <= span[0] and span[1] <= stop for start, stop in occupied):
            continue
        output.append(
            QuantityMention(
                QuantityKind.PERCENT,
                value,
                "PERCENT",
                text[span[0] : span[1]],
                span[0],
                span[1],
            )
        )
        occupied.add(span)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end)))


def _candidate_id(
    concept: str,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
) -> str | None:
    matches = tuple(
        candidate
        for candidate in candidates
        if candidate.block.char_start == block.char_start
        and candidate.metric.concept == _base(concept)
    )
    return min(matches, key=lambda item: item.metric.char_start).candidate_id if matches else None


def _frame(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    *,
    rule_id: str,
    concept: str,
    semantic: SemanticFrame,
    value: QuantityMention,
    change: QuantityMention | None = None,
    lower: QuantityMention | None = None,
    upper: QuantityMention | None = None,
    positive: bool = True,
) -> KPIFrame | None:
    period, period_semantics = resolve_period(block, semantic)
    if "GUIDANCE" in concept:
        period_semantics = PeriodSemantics.FORECAST
    normalized_value = (
        round(value.value, 2)
        if value.kind is QuantityKind.MONEY
        else round(value.value, 6)
    )
    normalized_change = (
        round(change.value, 2)
        if change is not None and change.kind is QuantityKind.MONEY
        else round(change.value, 6)
        if change is not None
        else None
    )
    proposed = KPIFrame(
        concept=concept,
        entity=block.entity,
        scope=resolve_scope(block.text, block.nearest_heading),
        period=period,
        period_semantics=period_semantics,
        frame=semantic,
        value=normalized_value,
        unit=value.unit,
        change=normalized_change,
        change_unit=change.unit if change is not None else None,
        comparator=(
            "PRIOR_PERIOD"
            if semantic in {SemanticFrame.CHANGE_BY, SemanticFrame.CHANGE_TO, SemanticFrame.COMPARATIVE}
            else None
        ),
        polarity=Polarity(positive),
        qualifier=qualifier(block.text),
        source=block.source,
        source_span=SourceSpan(block.section, block.char_start, block.char_end, block.text),
        extraction_method=ExtractionMethod.DEPENDENCY_RULE,
        rule_id=rule_id,
        rule_version=_RULE_BY_ID[rule_id].version,
        extraction_confidence=0.995,
        authority=AuthorityLevel.RESEARCH_EVIDENCE,
        verification_status=VerificationStatus.PROPOSED,
        context_trace={
            "candidate_id": _candidate_id(concept, block, candidates),
            "binding_eligibility": "V279_SPACY_SEMANTIC_OWNERSHIP",
            "rule_program_sha256": _RULE_BY_ID[rule_id].source_sha256,
        },
        tier=definition_for(_base(concept)).tier,
        lower_value=round(lower.value, 6) if lower is not None else None,
        upper_value=round(upper.value, 6) if upper is not None else None,
    )
    try:
        return replace(
            validate_kpi_frame(proposed, document),
            verified_by="V279_SPACY_SEMANTIC_OWNERSHIP_VERIFIER",
            tier=FactTier.CRITICAL,
        )
    except (FrameValidationError, KeyError, ValueError):
        return None


def _segments(text: str, backend) -> tuple[tuple[int, int], ...]:
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    output: list[tuple[int, int]] = []
    start = 0
    for token in tokens:
        delimiter = token.text in {"◦", "•", ";", "➢"}
        sentence_end = bool(getattr(token, "is_sent_end", False))
        if not delimiter and not sentence_end:
            continue
        end = token.idx if delimiter else token.idx + len(token.text)
        if text[start:end].strip():
            output.append((start, end))
        start = token.idx + len(token.text)
    if text[start:].strip():
        output.append((start, len(text)))
    return tuple(output) or ((0, len(text)),)


_NEGATIVE = {"decrease", "decline", "down", "headwind", "lower", "contract", "reduce"}
_POSITIVE = {"increase", "grow", "up", "benefit", "expand", "improve", "rise"}


def _polarity(
    tokens: tuple[object, ...],
    start: int,
    end: int,
    default: bool = True,
) -> bool:
    direction = default
    for token in tokens:
        if not (start <= token.idx < end):
            continue
        cue = token.lemma_.casefold()
        if cue in _NEGATIVE or token.lower_ in _NEGATIVE:
            direction = False
        elif cue in _POSITIVE or token.lower_ in _POSITIVE:
            direction = True
    return direction


def _has_cue(tokens: tuple[object, ...], start: int, end: int, cues: set[str]) -> bool:
    return any(
        start <= token.idx < end
        and (token.lemma_.casefold() in cues or token.lower_ in cues)
        for token in tokens
    )


def _first_phrase_start(backend, text: str, phrases: tuple[str, ...], start: int = 0) -> int | None:
    positions = tuple(
        match_start
        for _, match_start, _ in backend.phrase_mentions(text, phrases)
        if match_start >= start
    )
    return min(positions, default=None)


def _revenue_clause_frames(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    concepts,
    quantities: tuple[QuantityMention, ...],
    backend,
) -> tuple[KPIFrame, ...]:
    output: list[KPIFrame] = []
    tokens = tuple(token for token in backend.parse(block.text) if not token.is_space)
    for start, end in _segments(block.text, backend):
        segment_concepts = tuple(
            item
            for item in concepts
            if item.concept == "REVENUE" and start <= item.char_start < end
        )
        if not segment_concepts:
            continue
        if _has_cue(tokens, start, end, {"expect", "guidance"}):
            continue
        metric = segment_concepts[0]
        money = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.MONEY
            and metric.char_end <= item.char_start < end
            and item.char_start - metric.char_end <= 180
        )
        if not money:
            continue
        level = money[0]
        component_start = _first_phrase_start(
            backend,
            block.text,
            ("including", "driven by", "due to"),
            level.char_end,
        )
        main_end = min(end, component_start) if component_start is not None else end
        percents = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT
            and metric.char_end <= item.char_start < main_end
        )
        cues = _NEGATIVE | _POSITIVE | {"represent"}
        if percents and _has_cue(tokens, metric.char_start, main_end, cues):
            before = tuple(item for item in percents if item.char_end <= level.char_start)
            owned = (before[-1],) if before else tuple(
                item for item in percents if item.char_start >= level.char_end
            )
            prior_end = metric.char_end
            inherited = _polarity(tokens, metric.char_end, main_end)
            for change in owned:
                inherited = _polarity(tokens, prior_end, change.char_start, inherited)
                made = _frame(
                    document,
                    block,
                    candidates,
                    rule_id="v279.clause_revenue_level_and_growth",
                    concept="REVENUE",
                    semantic=SemanticFrame.CHANGE_TO,
                    value=level,
                    change=change,
                    positive=inherited,
                )
                if made is not None:
                    output.append(made)
                prior_end = change.char_end
        elif _has_cue(tokens, metric.char_end, level.char_start, {"be"}) or ":" in block.text[metric.char_end : level.char_start]:
            made = _frame(
                document,
                block,
                candidates,
                rule_id="v279.clause_revenue_level_and_growth",
                concept="REVENUE",
                semantic=SemanticFrame.ABSOLUTE_VALUE,
                value=level,
            )
            if made is not None:
                output.append(made)
    return tuple(output)


def _amount_before_metric_frames(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    concepts,
    quantities: tuple[QuantityMention, ...],
    backend,
) -> tuple[KPIFrame, ...]:
    tokens = tuple(token for token in backend.parse(block.text) if not token.is_space)
    verbs = tuple(
        token
        for token in tokens
        if token.lemma_.casefold() in {"book", "recognize"}
    )
    output: list[KPIFrame] = []
    for concept in concepts:
        if concept.concept not in {"ORDERS", "REVENUE"}:
            continue
        levels = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.MONEY
            and item.char_end <= concept.char_start
            and concept.char_start - item.char_end <= 80
        )
        if not levels:
            continue
        level = levels[-1]
        owners = tuple(
            token
            for token in verbs
            if token.idx <= level.char_start and level.char_start - token.idx <= 50
        )
        if not owners:
            continue
        owner = owners[-1].lemma_.casefold()
        if concept.concept == "ORDERS" and owner != "book":
            continue
        if concept.concept == "REVENUE" and owner != "recognize":
            continue
        made = _frame(
            document,
            block,
            candidates,
            rule_id="v279.amount_before_metric_ownership",
            concept=concept.concept,
            semantic=SemanticFrame.ABSOLUTE_VALUE,
            value=level,
        )
        if made is not None:
            output.append(made)
    return tuple(output)


def _guidance_frames(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    concepts,
    quantities: tuple[QuantityMention, ...],
    backend,
) -> tuple[KPIFrame, ...]:
    if not any(item.concept == "REVENUE" for item in concepts):
        return ()
    folded = block.text.casefold()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    output: list[KPIFrame] = []
    if "expected between" in folded and "midpoint" in folded and len(money) >= 3:
        low, high = money[:2]
        midpoint = money[2]
        made = _frame(
            document,
            block,
            candidates,
            rule_id="v279.revenue_expected_between_guidance",
            concept="REVENUE_GUIDANCE",
            semantic=SemanticFrame.RANGE_GUIDANCE,
            value=midpoint,
            lower=low,
            upper=high,
        )
        if made is not None:
            output.append(made)
        if percents:
            change = percents[0]
            tokens = tuple(token for token in backend.parse(block.text) if not token.is_space)
            made = _frame(
                document,
                block,
                candidates,
                rule_id="v279.revenue_expected_between_guidance",
                concept="REVENUE_CHANGE_GUIDANCE",
                semantic=SemanticFrame.ABSOLUTE_VALUE,
                value=change,
                positive=_polarity(tokens, 0, change.char_start),
            )
            if made is not None:
                output.append(made)
    elif "guidance" in folded and "unchanged at" in folded and money:
        made = _frame(
            document,
            block,
            candidates,
            rule_id="v279.revenue_unchanged_guidance_level",
            concept="REVENUE_GUIDANCE",
            semantic=SemanticFrame.ABSOLUTE_VALUE,
            value=money[0],
        )
        if made is not None:
            output.append(made)
    elif (
        "expected to reduce" in folded
        and "sales growth" in folded
        and percents
    ):
        made = _frame(
            document,
            block,
            candidates,
            rule_id="v279.revenue_growth_reduction_guidance",
            concept="REVENUE_CHANGE_GUIDANCE",
            semantic=SemanticFrame.ABSOLUTE_VALUE,
            value=percents[0],
            positive=False,
        )
        if made is not None:
            output.append(made)
    return tuple(output)


def _revenue_component_frames(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    concepts,
    quantities: tuple[QuantityMention, ...],
    backend,
) -> tuple[KPIFrame, ...]:
    if not any(item.concept == "REVENUE" for item in concepts):
        return ()
    tokens = tuple(token for token in backend.parse(block.text) if not token.is_space)
    output: list[KPIFrame] = []
    for quantity in quantities:
        if "point" not in quantity.raw.casefold():
            continue
        following = tuple(
            token
            for token in tokens
            if quantity.char_end <= token.idx <= quantity.char_end + 28
        )
        if not any(token.lemma_.casefold() in {"benefit", "headwind"} for token in following):
            continue
        positive = not any(token.lemma_.casefold() == "headwind" for token in following)
        made = _frame(
            document,
            block,
            candidates,
            rule_id="v279.revenue_bridge_components",
            concept="REVENUE",
            semantic=SemanticFrame.CHANGE_BY,
            value=quantity,
            positive=positive,
        )
        if made is not None:
            output.append(made)
    return tuple(output)


def _price_volume_frames(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    concepts,
    quantities: tuple[QuantityMention, ...],
    backend,
) -> tuple[KPIFrame, ...]:
    by_name = {
        name: tuple(item for item in concepts if item.concept == name)
        for name in ("REVENUE", "PRICE_REALIZATION", "ACTIVITY_VOLUME")
    }
    if not all(by_name.values()) or "driven" not in block.text.casefold():
        return ()
    tokens = tuple(token for token in backend.parse(block.text) if not token.is_space)
    output: list[KPIFrame] = []
    ordered_concepts = tuple(
        sorted(
            (item for items in by_name.values() for item in items),
            key=lambda item: item.char_start,
        )
    )
    for index, mention in enumerate(ordered_concepts):
        if mention.concept not in by_name:
            continue
        region_end = (
            ordered_concepts[index + 1].char_start
            if index + 1 < len(ordered_concepts)
            else len(block.text)
        )
        values = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT
            and mention.char_end <= item.char_start < region_end
        )
        if not values:
            continue
        value = values[0]
        made = _frame(
            document,
            block,
            candidates,
            rule_id="v279.revenue_bridge_components",
            concept=mention.concept,
            semantic=SemanticFrame.CHANGE_BY,
            value=value,
            positive=_polarity(tokens, mention.char_start, value.char_start),
        )
        if made is not None:
            output.append(made)
    return tuple(output)


def _operating_income_frames(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    concepts,
    quantities: tuple[QuantityMention, ...],
    backend,
) -> tuple[KPIFrame, ...]:
    tokens = tuple(token for token in backend.parse(block.text) if not token.is_space)
    output: list[KPIFrame] = []
    for mention in (item for item in concepts if item.concept == "OPERATING_INCOME"):
        money = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.MONEY
            and mention.char_end <= item.char_start <= mention.char_end + 80
        )
        if not money:
            continue
        level = money[0]
        changes = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT
            and level.char_end <= item.char_start <= level.char_end + 60
        )
        if not changes or not _has_cue(tokens, mention.char_start, changes[0].char_start, _NEGATIVE | _POSITIVE):
            continue
        change = changes[0]
        made = _frame(
            document,
            block,
            candidates,
            rule_id="v279.operating_income_level_and_change",
            concept="OPERATING_INCOME",
            semantic=SemanticFrame.CHANGE_TO,
            value=level,
            change=change,
            positive=_polarity(tokens, mention.char_start, change.char_start),
        )
        if made is not None:
            output.append(made)
    return tuple(output)


def _margin_frames(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    concepts,
    quantities: tuple[QuantityMention, ...],
    backend,
) -> tuple[KPIFrame, ...]:
    mentions = tuple(
        sorted(
            (item for item in concepts if item.concept in {"GROSS_MARGIN", "OPERATING_MARGIN"}),
            key=lambda item: (item.char_start, item.char_end),
        )
    )
    tokens = tuple(token for token in backend.parse(block.text) if not token.is_space)
    output: list[KPIFrame] = []
    for index, mention in enumerate(mentions):
        end = mentions[index + 1].char_start if index + 1 < len(mentions) else len(block.text)
        if end <= mention.char_end:
            continue
        include_start = _first_phrase_start(backend, block.text, ("including",), mention.char_end)
        primary_end = min(end, include_start) if include_start is not None and include_start < end else end
        percents = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT
            and mention.char_end <= item.char_start < primary_end
        )
        basis = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.BASIS_POINTS
            and mention.char_end <= item.char_start < primary_end
        )
        if percents and basis:
            level = percents[0]
            change = min(basis, key=lambda item: abs(item.char_start - level.char_start))
            made = _frame(
                document,
                block,
                candidates,
                rule_id="v279.margin_level_and_change",
                concept=mention.concept,
                semantic=SemanticFrame.CHANGE_TO,
                value=level,
                change=change,
                positive=_polarity(tokens, mention.char_start, max(level.char_start, change.char_start)),
            )
            if made is not None:
                output.append(made)
        elif len(percents) >= 2 and _has_cue(tokens, percents[0].char_end, percents[1].char_start, {"from", "compare"}):
            current = _frame(
                document,
                block,
                candidates,
                rule_id="v279.margin_comparison",
                concept=mention.concept,
                semantic=SemanticFrame.COMPARATIVE,
                value=percents[0],
            )
            prior = _frame(
                document,
                block,
                candidates,
                rule_id="v279.margin_comparison",
                concept=f"PRIOR_YEAR_{mention.concept}",
                semantic=SemanticFrame.COMPARATIVE,
                value=percents[1],
            )
            output.extend(frame for frame in (current, prior) if frame is not None)
        if include_start is not None and include_start < end:
            component_basis = tuple(
                item
                for item in quantities
                if item.kind is QuantityKind.BASIS_POINTS
                and include_start <= item.char_start < end
            )
            for component in component_basis:
                if not _has_cue(tokens, component.char_end, min(end, component.char_end + 40), {"benefit", "headwind"}):
                    continue
                made = _frame(
                    document,
                    block,
                    candidates,
                    rule_id="v279.margin_driver_component",
                    concept=mention.concept,
                    semantic=SemanticFrame.CHANGE_BY,
                    value=component,
                    positive=_polarity(tokens, component.char_end, min(end, component.char_end + 40)),
                )
                if made is not None:
                    output.append(made)
    return tuple(output)


def _cash_frames(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    concepts,
    quantities: tuple[QuantityMention, ...],
    backend,
) -> tuple[KPIFrame, ...]:
    mentions = tuple(item for item in concepts if item.concept == "CASH")
    if not mentions or not backend.phrase_mentions(
        block.text,
        ("cash and investments", "cash and equivalents", "cash, cash equivalents"),
    ):
        return ()
    metric = mentions[0]
    money = tuple(
        item
        for item in quantities
        if item.kind is QuantityKind.MONEY and item.char_start >= metric.char_end
    )
    if len(money) < 2:
        return ()
    tokens = tuple(token for token in backend.parse(block.text) if not token.is_space)
    compare_start = _first_phrase_start(backend, block.text, ("compared to",), metric.char_end)
    if compare_start is not None:
        current_values = tuple(item for item in money if item.char_end <= compare_start)
        prior_values = tuple(item for item in money if item.char_start >= compare_start)
        if current_values and prior_values:
            current = _frame(
                document,
                block,
                candidates,
                rule_id="v279.cash_comparison",
                concept="CASH",
                semantic=SemanticFrame.COMPARATIVE,
                value=current_values[0],
            )
            prior = _frame(
                document,
                block,
                candidates,
                rule_id="v279.cash_comparison",
                concept="PRIOR_YEAR_CASH",
                semantic=SemanticFrame.COMPARATIVE,
                value=prior_values[0],
            )
            return tuple(frame for frame in (current, prior) if frame is not None)
    direction_tokens = tuple(
        token
        for token in tokens
        if token.idx >= money[0].char_end and token.lemma_.casefold() in {"down", "up", "decrease", "increase"}
    )
    if not direction_tokens:
        return ()
    direction = direction_tokens[0]
    changes = tuple(item for item in money[1:] if item.char_start >= direction.idx)
    if not changes:
        return ()
    made = _frame(
        document,
        block,
        candidates,
        rule_id="v279.cash_level_and_change",
        concept="CASH",
        semantic=SemanticFrame.CHANGE_TO,
        value=money[0],
        change=changes[0],
        positive=_polarity(tokens, money[0].char_end, changes[0].char_start),
    )
    return (made,) if made is not None else ()


def recover_v279_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
) -> tuple[KPIFrame, ...]:
    backend = semantic_backend_v279()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v279(block.text, backend)
        quantities = semantic_quantities_v279(block.text, backend)
        for binder in (
            _revenue_clause_frames,
            _amount_before_metric_frames,
            _guidance_frames,
            _revenue_component_frames,
            _price_volume_frames,
            _operating_income_frames,
            _margin_frames,
            _cash_frames,
        ):
            output.extend(binder(document, block, candidates, concepts, quantities, backend))
    unique: dict[tuple[object, ...], KPIFrame] = {}
    for frame in output:
        signature = (
            frame.concept,
            frame.frame,
            frame.value,
            frame.change,
            frame.lower_value,
            frame.upper_value,
            frame.polarity.positive,
            frame.source.sha256,
            frame.source_span.char_start,
        )
        unique[signature] = frame
    return tuple(unique.values())


def resolve_frame_conflicts_v279(
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
) -> tuple[KPIFrame, ...]:
    def superseded(frame: KPIFrame) -> bool:
        direct_takeover = any(
            replacement.source.sha256 == frame.source.sha256
            and _base(replacement.concept) == _base(frame.concept)
            and replacement.source_span.char_start <= frame.source_span.char_start
            and frame.source_span.char_end <= replacement.source_span.char_end
            for replacement in recovered
        )
        margin_ownership = any(
            replacement.source.sha256 == frame.source.sha256
            and _base(frame.concept) == "OPERATING_INCOME"
            and _base(replacement.concept) == "OPERATING_MARGIN"
            and replacement.value == frame.value
            and replacement.source_span.char_start <= frame.source_span.char_start
            and frame.source_span.char_end <= replacement.source_span.char_end
            for replacement in recovered
        )
        return direct_takeover or margin_ownership

    merged = (
        *(frame for frame in existing if not superseded(frame)),
        *recovered,
    )
    unique: dict[tuple[object, ...], KPIFrame] = {}
    for frame in merged:
        signature = (
            frame.concept,
            frame.frame,
            frame.value,
            frame.change,
            frame.lower_value,
            frame.upper_value,
            frame.polarity.positive,
            frame.source.sha256,
            frame.source_span.char_start,
        )
        current = unique.get(signature)
        if current is None or frame.rule_id.startswith("v279."):
            unique[signature] = frame
    return tuple(unique.values())
