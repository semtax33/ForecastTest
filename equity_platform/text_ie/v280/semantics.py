from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256

from equity_platform.documents import CanonicalDocument
from equity_platform.ir import AuthorityLevel, ExtractionMethod, SourceSpan
from equity_platform.paths import PROJECT_ROOT

from ..context import qualifier, resolve_period
from ..document import document_text_blocks
from ..dsl import compile_text_rule_file
from ..model import (
    ConceptMention,
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
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v279.semantics import (
    semantic_backend_v279,
    semantic_concepts_v279,
    semantic_quantities_v279,
)


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v280_semantic_context.arc"
V280_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V280_RULES}

_ALIASES = {
    "average ticket": "PRICE_REALIZATION",
    "traffic": "ACTIVITY_VOLUME",
    "net new bookings": "ORDERS",
    "new bookings": "ORDERS",
    "bookings": "ORDERS",
    "unrestricted cash balances": "CASH",
    "cash balances": "CASH",
    "short-term and long-term borrowings": "DEBT",
    "borrowings": "DEBT",
}
_NEGATIVE = {"decrease", "decline", "down", "headwind", "lower", "below", "contract", "reduce", "offset", "charge"}
_POSITIVE = {"increase", "grow", "up", "benefit", "expand", "improve", "rise", "gain", "higher"}
_FUTURE = {"expect", "anticipate", "plan", "project", "guidance", "outlook"}


def _base(concept: str) -> str:
    result = concept.removeprefix("PRIOR_YEAR_")
    while True:
        prior = result
        result = result.removesuffix("_GUIDANCE").removesuffix("_CHANGE")
        if result == prior:
            return result


@lru_cache(maxsize=1)
def semantic_backend_v280():
    return semantic_backend_v279()


def semantic_quantities_v280(text: str, backend=None) -> tuple[QuantityMention, ...]:
    selected = backend or semantic_backend_v280()
    output = list(semantic_quantities_v279(text, selected))
    occupied = {(item.char_start, item.char_end) for item in output}
    tokens = _tokens(selected, text)
    for index, token in enumerate(tokens):
        if not token.like_num:
            continue
        percentage_index = index + 1
        if percentage_index < len(tokens) and tokens[percentage_index].text == "-":
            percentage_index += 1
        point_index = percentage_index + 1
        if (
            point_index >= len(tokens)
            or tokens[percentage_index].lemma_.casefold() != "percentage"
            or tokens[point_index].lemma_.casefold() != "point"
        ):
            continue
        try:
            value = float(token.text.replace(",", ""))
        except ValueError:
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
    # In constructions such as "130 to 150 basis points", the inherited
    # parser types only the terminal number because the unit is stated once.
    # Propagate that unit across the explicit coordination edge.
    for quantity in tuple(output):
        if quantity.kind not in {QuantityKind.BASIS_POINTS, QuantityKind.PERCENT}:
            continue
        value_index = next(
            (index for index, token in enumerate(tokens) if token.idx == quantity.char_start),
            None,
        )
        if value_index is None or value_index < 2:
            continue
        connector = tokens[value_index - 1]
        lower_token = tokens[value_index - 2]
        if connector.lemma_.casefold() != "to" or not lower_token.like_num:
            continue
        span = (lower_token.idx, lower_token.idx + len(lower_token.text))
        if span in occupied:
            continue
        try:
            lower_value = float(lower_token.text.replace(",", ""))
        except ValueError:
            continue
        output.append(
            QuantityMention(
                quantity.kind,
                lower_value,
                quantity.unit,
                lower_token.text,
                span[0],
                span[1],
            )
        )
        occupied.add(span)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end)))


def semantic_concepts_v280(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v280()
    output = list(semantic_concepts_v279(text, selected))
    for alias, concept in _ALIASES.items():
        output.extend(
            ConceptMention(concept, literal, start, end)
            for literal, start, end in selected.phrase_mentions(text, (alias,))
        )
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept)))


def augment_candidates_v280(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v280()
    output = list(candidates)
    seen = {
        (item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end)
        for item in output
    }
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v280(block.text, backend)
        for mention in semantic_concepts_v280(block.text, backend):
            signature = (block.char_start, mention.concept, mention.char_start, mention.char_end)
            if signature in seen or mention.alias.casefold() not in _ALIASES:
                continue
            allowed = set(definition_for(mention.concept).quantity_kinds) | {
                QuantityKind.PERCENT,
                QuantityKind.BASIS_POINTS,
                QuantityKind.MONEY,
                QuantityKind.RATE,
            }
            compatible = tuple(
                item
                for item in quantities
                if item.kind in allowed and abs(item.char_start - mention.char_start) <= 240
            )
            if not compatible:
                continue
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:"
                f"{mention.char_start}:{mention.char_end}:v280".encode()
            ).hexdigest()[:20]
            output.append(
                RecallCandidate(
                    candidate_id=candidate_id,
                    block=block,
                    metric=MetricAnchor(
                        mention.concept,
                        mention.alias,
                        mention.char_start,
                        mention.char_end,
                    ),
                    quantities=compatible,
                    origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                    rule_ids=("v280.spacy_semantic_context_alias",),
                )
            )
            seen.add(signature)
    return tuple(output)


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
    proposed = KPIFrame(
        concept=concept,
        entity=block.entity,
        scope=resolve_scope(block.text, block.nearest_heading),
        period=period,
        period_semantics=period_semantics,
        frame=semantic,
        value=round(value.value, 2) if value.kind is QuantityKind.MONEY else round(value.value, 6),
        unit=value.unit,
        change=(
            round(change.value, 2)
            if change is not None and change.kind is QuantityKind.MONEY
            else round(change.value, 6)
            if change is not None
            else None
        ),
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
            "binding_eligibility": "V280_SPACY_HIERARCHICAL_CONTEXT",
            "rule_program_sha256": _RULE_BY_ID[rule_id].source_sha256,
        },
        tier=definition_for(_base(concept)).tier,
        lower_value=round(lower.value, 6) if lower is not None else None,
        upper_value=round(upper.value, 6) if upper is not None else None,
    )
    try:
        return replace(
            validate_kpi_frame(proposed, document),
            verified_by="V280_SPACY_HIERARCHICAL_CONTEXT_VERIFIER",
            tier=FactTier.CRITICAL,
        )
    except (FrameValidationError, KeyError, ValueError):
        return None


def _tokens(backend, text: str):
    return tuple(token for token in backend.parse(text) if not token.is_space)


def _has(tokens, start: int, end: int, cues: set[str]) -> bool:
    return any(
        start <= token.idx < end
        and (token.lemma_.casefold() in cues or token.lower_ in cues)
        for token in tokens
    )


def _polarity(tokens, start: int, end: int, default: bool = True) -> bool:
    direction = default
    for token in tokens:
        if not start <= token.idx < end:
            continue
        cue = token.lemma_.casefold()
        if cue in _NEGATIVE or token.lower_ in _NEGATIVE:
            direction = False
        elif cue in _POSITIVE or token.lower_ in _POSITIVE:
            direction = True
    return direction


def _phrase_start(backend, text: str, phrases: tuple[str, ...], start: int = 0) -> int | None:
    positions = tuple(
        match_start
        for _, match_start, _ in backend.phrase_mentions(text, phrases)
        if match_start >= start
    )
    return min(positions, default=None)


def _metric_regions(concepts, names: set[str], text_end: int):
    mentions = tuple(
        sorted(
            (item for item in concepts if item.concept in names),
            key=lambda item: (item.char_start, -(item.char_end - item.char_start)),
        )
    )
    selected: list[ConceptMention] = []
    for mention in mentions:
        if any(
            prior.concept == mention.concept
            and prior.char_start <= mention.char_start
            and mention.char_end <= prior.char_end
            for prior in selected
        ):
            continue
        selected.append(mention)
    return tuple(
        (mention, selected[index + 1].char_start if index + 1 < len(selected) else text_end)
        for index, mention in enumerate(selected)
    )


def _parallel_metric_frames(document, block, candidates, concepts, quantities, backend):
    names = {"OPERATING_INCOME", "OPERATING_MARGIN", "GROSS_MARGIN", "ADJUSTED_EBITDA", "ORDERS", "BOOK_TO_BILL"}
    tokens = _tokens(backend, block.text)
    output: list[KPIFrame] = []
    for mention, end in _metric_regions(concepts, names, len(block.text)):
        start = mention.char_end
        include_at = _phrase_start(
            backend,
            block.text,
            ("including", "included", "includes", "inclusive of"),
            start,
        )
        primary_end = min(end, include_at) if include_at is not None and include_at < end else end
        money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY and start <= item.char_start < primary_end)
        rates = tuple(item for item in quantities if item.kind is QuantityKind.RATE and start <= item.char_start < primary_end)
        percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT and start <= item.char_start < primary_end)
        basis = tuple(item for item in quantities if item.kind is QuantityKind.BASIS_POINTS and start <= item.char_start < primary_end)
        future = _has(tokens, max(0, mention.char_start - 45), primary_end, _FUTURE)
        if mention.concept in {"OPERATING_MARGIN", "GROSS_MARGIN"}:
            compare_at = _phrase_start(backend, block.text, ("compared to", "versus last year", "versus last year's", "expanded from"), start)
            if compare_at is not None and compare_at < primary_end and len(percents) >= 2:
                current, prior = percents[0], percents[-1]
                current_frame = _frame(document, block, candidates, rule_id="v280.comparative_context", concept=mention.concept, semantic=SemanticFrame.COMPARATIVE, value=current)
                prior_frame = _frame(document, block, candidates, rule_id="v280.comparative_context", concept=f"PRIOR_YEAR_{mention.concept}", semantic=SemanticFrame.COMPARATIVE, value=prior)
                output.extend(frame for frame in (current_frame, prior_frame) if frame is not None)
                middle = tuple(item for item in percents[1:-1])
                for change in middle:
                    made = _frame(document, block, candidates, rule_id="v280.comparative_context", concept=mention.concept, semantic=SemanticFrame.CHANGE_BY, value=change, positive=_polarity(tokens, current.char_end, change.char_start + 1))
                    if made is not None:
                        output.append(made)
            elif percents and basis:
                made = _frame(document, block, candidates, rule_id="v280.parallel_metric_ownership", concept=mention.concept, semantic=SemanticFrame.CHANGE_TO, value=percents[0], change=basis[0], positive=_polarity(tokens, mention.char_start, max(percents[0].char_start, basis[0].char_start)))
                if made is not None:
                    output.append(made)
            elif percents:
                concept = f"{mention.concept}_GUIDANCE" if future else mention.concept
                directional = _has(
                    tokens,
                    mention.char_start,
                    percents[0].char_start,
                    _NEGATIVE | _POSITIVE,
                )
                semantic = (
                    SemanticFrame.ABSOLUTE_VALUE
                    if future or not directional
                    else SemanticFrame.CHANGE_BY
                )
                made = _frame(document, block, candidates, rule_id="v280.guidance_context" if future else "v280.parallel_metric_ownership", concept=concept, semantic=semantic, value=percents[0], positive=_polarity(tokens, mention.char_start, percents[0].char_start))
                if made is not None:
                    output.append(made)
            elif basis:
                made = _frame(document, block, candidates, rule_id="v280.parallel_metric_ownership", concept=mention.concept, semantic=SemanticFrame.CHANGE_BY, value=basis[0], positive=_polarity(tokens, mention.char_start, basis[0].char_start))
                if made is not None:
                    output.append(made)
            if include_at is not None and include_at < end:
                components = tuple(item for item in quantities if item.kind is QuantityKind.BASIS_POINTS and include_at <= item.char_start < end)
                negative_context = _has(tokens, include_at, end, {"charge", "headwind"})
                respectively = _has(tokens, include_at, end, {"respectively"})
                for component_index, component in enumerate(components):
                    component_concept = (
                        f"PRIOR_YEAR_{mention.concept}"
                        if respectively and component_index == 1
                        else mention.concept
                    )
                    made = _frame(document, block, candidates, rule_id="v280.margin_component_context", concept=component_concept, semantic=SemanticFrame.CHANGE_BY, value=component, positive=_polarity(tokens, component.char_end, min(end, component.char_end + 55), not negative_context))
                    if made is not None:
                        output.append(made)
            continue
        values = money if mention.concept != "BOOK_TO_BILL" else rates
        if not values:
            continue
        value = values[0]
        change_values = tuple(item for item in percents if item.char_start != value.char_start)
        compare_at = _phrase_start(backend, block.text, ("compared to",), start)
        if compare_at is not None and compare_at < end and len(money) >= 2:
            current = _frame(document, block, candidates, rule_id="v280.comparative_context", concept=mention.concept, semantic=SemanticFrame.COMPARATIVE, value=money[0])
            prior = _frame(document, block, candidates, rule_id="v280.comparative_context", concept=f"PRIOR_YEAR_{mention.concept}", semantic=SemanticFrame.COMPARATIVE, value=money[1])
            output.extend(frame for frame in (current, prior) if frame is not None)
        elif change_values:
            made = _frame(document, block, candidates, rule_id="v280.parallel_metric_ownership", concept=mention.concept, semantic=SemanticFrame.CHANGE_TO, value=value, change=change_values[0], positive=_polarity(tokens, mention.char_start, change_values[0].char_start))
            if made is not None:
                output.append(made)
        else:
            made = _frame(document, block, candidates, rule_id="v280.parallel_metric_ownership", concept=mention.concept, semantic=SemanticFrame.ABSOLUTE_VALUE, value=value)
            if made is not None:
                output.append(made)
    return tuple(output)


def _driver_frames(document, block, candidates, concepts, quantities, backend):
    tokens = _tokens(backend, block.text)
    driver_names = {"PRICE_REALIZATION", "ACTIVITY_VOLUME"}
    output: list[KPIFrame] = []
    for mention, end in _metric_regions(concepts, driver_names, len(block.text)):
        values = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT
            and (
                mention.char_end <= item.char_start < end
                or (item.char_end <= mention.char_start and mention.char_start - item.char_end <= 45)
            )
        )
        if not values:
            continue
        preceding = tuple(item for item in values if item.char_end <= mention.char_start)
        following = tuple(item for item in values if item.char_start >= mention.char_end)
        governed_preceding = tuple(
            item
            for item in preceding
            if _has(tokens, item.char_end, mention.char_start, _NEGATIVE | _POSITIVE)
            and _has(tokens, item.char_end, mention.char_start, {"in"})
        )
        value = (
            governed_preceding[-1]
            if governed_preceding
            else following[0]
            if following
            else None
        )
        if value is None:
            continue
        made = _frame(document, block, candidates, rule_id="v280.driver_preposed_value", concept=mention.concept, semantic=SemanticFrame.CHANGE_BY, value=value, positive=_polarity(tokens, min(value.char_start, mention.char_start), max(value.char_end, mention.char_end)))
        if made is not None:
            output.append(made)
    return tuple(output)


def _revenue_context_frames(document, block, candidates, concepts, quantities, backend):
    mentions = tuple(item for item in concepts if item.concept == "REVENUE")
    if not mentions:
        return ()
    tokens = _tokens(backend, block.text)
    folded = block.text.casefold()
    output: list[KPIFrame] = []
    revenue = mentions[0]
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    money_after = tuple(item for item in money if item.char_start >= revenue.char_end)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    basis = tuple(item for item in quantities if item.kind is QuantityKind.BASIS_POINTS)
    future = _has(tokens, 0, len(block.text), _FUTURE)

    if "earnings per share" in folded and revenue.alias.casefold() in {"sales", "revenue"} and revenue.char_start < _phrase_start(backend, block.text, ("earnings per share",), 0):
        return ()
    if (
        "included" in folded
        and backend.phrase_mentions(block.text, ("average ticket",))
        and backend.phrase_mentions(block.text, ("traffic",))
    ):
        return ()
    if "below our expectations" in folded and "all delivered" in folded:
        return ()
    if future:
        if "mid-point" in folded or "midpoint" in folded:
            if percents:
                made = _frame(document, block, candidates, rule_id="v280.guidance_context", concept="REVENUE_CHANGE_GUIDANCE", semantic=SemanticFrame.ABSOLUTE_VALUE, value=percents[0])
                if made is not None:
                    output.append(made)
            reflecting_at = _phrase_start(backend, block.text, ("reflecting",), 0)
            if reflecting_at is not None:
                for component in basis:
                    made = _frame(document, block, candidates, rule_id="v280.guidance_context", concept="REVENUE_CHANGE_GUIDANCE", semantic=SemanticFrame.CHANGE_BY, value=component, positive=_polarity(tokens, max(reflecting_at, component.char_start - 45), min(len(block.text), component.char_end + 45)))
                    if made is not None:
                        output.append(made)
            return tuple(output)
        relative_basis = bool(
            basis
            and _has(
                tokens,
                basis[0].char_end,
                len(block.text),
                {"lower", "below", "higher", "above", "reduce"},
            )
        )
        if relative_basis:
            for component in basis:
                made = _frame(document, block, candidates, rule_id="v280.guidance_context", concept="REVENUE_CHANGE_GUIDANCE", semantic=SemanticFrame.CHANGE_BY, value=component, positive=_polarity(tokens, component.char_end, min(len(block.text), component.char_end + 75)))
                if made is not None:
                    output.append(made)
            return tuple(output)
        range_cue = any(phrase in folded for phrase in ("expected to increase", "planning", "plan for", "projected to"))
        if range_cue and len(percents) >= 2:
            for index in range(0, len(percents) - 1, 2):
                low, high = percents[index], percents[index + 1]
                midpoint = replace(low, value=(low.value + high.value) / 2)
                made = _frame(document, block, candidates, rule_id="v280.guidance_context", concept="REVENUE_CHANGE_GUIDANCE", semantic=SemanticFrame.RANGE_GUIDANCE, value=midpoint, lower=low, upper=high)
                if made is not None:
                    output.append(made)
            return tuple(output)
        if percents:
            selected = percents[0]
            made = _frame(document, block, candidates, rule_id="v280.guidance_context", concept="REVENUE_CHANGE_GUIDANCE", semantic=SemanticFrame.ABSOLUTE_VALUE if selected.kind is QuantityKind.PERCENT else SemanticFrame.CHANGE_BY, value=selected, positive=_polarity(tokens, revenue.char_start, selected.char_start))
            if made is not None:
                output.append(made)
        if basis and _has(tokens, 0, len(block.text), {"lower", "higher", "reduce"}):
            for component in basis:
                made = _frame(document, block, candidates, rule_id="v280.guidance_context", concept="REVENUE_CHANGE_GUIDANCE", semantic=SemanticFrame.CHANGE_BY, value=component, positive=_polarity(tokens, max(0, component.char_start - 60), min(len(block.text), component.char_end + 60)))
                if made is not None:
                    output.append(made)
        return tuple(output)

    compare_at = _phrase_start(backend, block.text, ("compared to", "up from"), revenue.char_end)
    if compare_at is not None and len(money_after) >= 2:
        current = _frame(document, block, candidates, rule_id="v280.comparative_context", concept="REVENUE", semantic=SemanticFrame.COMPARATIVE, value=money_after[0])
        prior = _frame(document, block, candidates, rule_id="v280.comparative_context", concept="PRIOR_YEAR_REVENUE", semantic=SemanticFrame.COMPARATIVE, value=money_after[1])
        output.extend(frame for frame in (current, prior) if frame is not None)
        for change in percents:
            made = _frame(document, block, candidates, rule_id="v280.comparative_context", concept="REVENUE", semantic=SemanticFrame.CHANGE_BY, value=change, positive=_polarity(tokens, revenue.char_start, change.char_start))
            if made is not None:
                output.append(made)
        return tuple(output)
    if money_after and percents:
        for change in percents:
            made = _frame(document, block, candidates, rule_id="v280.parallel_metric_ownership", concept="REVENUE", semantic=SemanticFrame.CHANGE_TO, value=money_after[0], change=change, positive=_polarity(tokens, revenue.char_start, change.char_start))
            if made is not None:
                output.append(made)
        return tuple(output)
    if "on top of" in folded and "last year" in folded and len(percents) >= 2:
        for concept, value in (("REVENUE", percents[0]), ("PRIOR_YEAR_REVENUE", percents[1])):
            made = _frame(document, block, candidates, rule_id="v280.comparative_context", concept=concept, semantic=SemanticFrame.CHANGE_BY, value=value, positive=_polarity(tokens, revenue.char_start, value.char_start))
            if made is not None:
                output.append(made)
        return tuple(output)
    if "respectively" in folded and percents:
        made = _frame(document, block, candidates, rule_id="v280.respectively_alignment", concept="REVENUE", semantic=SemanticFrame.CHANGE_BY, value=percents[0], positive=_polarity(tokens, revenue.char_start, percents[0].char_start))
        if made is not None:
            output.append(made)
        if "portfolio mix" in folded and len(percents) >= 3:
            mix = _frame(document, block, candidates, rule_id="v280.respectively_alignment", concept="REVENUE", semantic=SemanticFrame.CHANGE_BY, value=percents[-1], positive=_polarity(tokens, revenue.char_start, percents[-1].char_start))
            if mix is not None:
                output.append(mix)
        return tuple(output)
    revenue_regions = _metric_regions(concepts, {"REVENUE"}, len(block.text))
    if len(revenue_regions) >= 2:
        for mention, end in revenue_regions:
            owned = tuple(
                item
                for item in percents
                if mention.char_end <= item.char_start < end
            )
            if not owned:
                continue
            made = _frame(document, block, candidates, rule_id="v280.respectively_alignment", concept="REVENUE", semantic=SemanticFrame.CHANGE_BY, value=owned[0], positive=_polarity(tokens, mention.char_start, owned[0].char_start))
            if made is not None:
                output.append(made)
        if output:
            return tuple(output)
    driver_mentions = tuple(item for item in concepts if item.concept in {"PRICE_REALIZATION", "ACTIVITY_VOLUME"})
    boundary = min((item.char_start for item in driver_mentions if item.char_start > revenue.char_end), default=len(block.text))
    owned = tuple(item for item in percents if revenue.char_end <= item.char_start < boundary)
    if not owned:
        owned = tuple(item for item in percents if item.char_end <= revenue.char_start and revenue.char_start - item.char_end <= 80)
    if owned:
        value = owned[-1] if owned[0].char_end <= revenue.char_start else owned[0]
        made = _frame(document, block, candidates, rule_id="v280.driver_preposed_value", concept="REVENUE", semantic=SemanticFrame.CHANGE_BY, value=value, positive=_polarity(tokens, min(revenue.char_start, value.char_start), max(revenue.char_end, value.char_end)))
        if made is not None:
            output.append(made)
    return tuple(output)


def _balance_sheet_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if "cash flow" in folded or "scheduled debt maturities" in folded:
        return ()
    tokens = _tokens(backend, block.text)
    output: list[KPIFrame] = []
    for mention, end in _metric_regions(concepts, {"CASH", "DEBT"}, len(block.text)):
        money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY and mention.char_end <= item.char_start < end)
        if not money:
            continue
        compare_at = _phrase_start(backend, block.text, ("compared to", "down from", "up from"), mention.char_end)
        if compare_at is not None and len(money) >= 2:
            current = _frame(document, block, candidates, rule_id="v280.comparative_context", concept=mention.concept, semantic=SemanticFrame.COMPARATIVE, value=money[0])
            prior = _frame(document, block, candidates, rule_id="v280.comparative_context", concept=f"PRIOR_YEAR_{mention.concept}", semantic=SemanticFrame.COMPARATIVE, value=money[1])
            output.extend(frame for frame in (current, prior) if frame is not None)
        else:
            made = _frame(document, block, candidates, rule_id="v280.balance_sheet_level", concept=mention.concept, semantic=SemanticFrame.ABSOLUTE_VALUE, value=money[0], positive=_polarity(tokens, mention.char_start, money[0].char_start))
            if made is not None:
                output.append(made)
    return tuple(output)


def _margin_plan_range_frames(document, block, candidates, concepts, quantities, backend):
    mentions = tuple(item for item in concepts if item.concept == "OPERATING_MARGIN")
    basis = tuple(item for item in quantities if item.kind is QuantityKind.BASIS_POINTS)
    folded = block.text.casefold()
    if not mentions or len(basis) < 3 or "plan" not in folded:
        return ()
    tokens = _tokens(backend, block.text)
    actual = _frame(document, block, candidates, rule_id="v280.guidance_context", concept="OPERATING_MARGIN", semantic=SemanticFrame.CHANGE_BY, value=basis[0], positive=_polarity(tokens, mentions[0].char_start, basis[0].char_start))
    midpoint = replace(basis[1], value=(basis[1].value + basis[2].value) / 2)
    guidance = _frame(document, block, candidates, rule_id="v280.guidance_context", concept="OPERATING_MARGIN_CHANGE_GUIDANCE", semantic=SemanticFrame.RANGE_GUIDANCE, value=midpoint, lower=basis[1], upper=basis[2])
    return tuple(frame for frame in (actual, guidance) if frame is not None)


def recover_v280_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
) -> tuple[KPIFrame, ...]:
    backend = semantic_backend_v280()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v280(block.text, backend)
        quantities = semantic_quantities_v280(block.text, backend)
        for binder in (
            _parallel_metric_frames,
            _driver_frames,
            _revenue_context_frames,
            _balance_sheet_frames,
            _margin_plan_range_frames,
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


def resolve_frame_conflicts_v280(
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
) -> tuple[KPIFrame, ...]:
    recovered_by_span: dict[tuple[str, int], tuple[KPIFrame, ...]] = {}
    for frame in recovered:
        key = (frame.source.sha256, frame.source_span.char_start)
        recovered_by_span[key] = (*recovered_by_span.get(key, ()), frame)

    def superseded(frame: KPIFrame) -> bool:
        replacements = recovered_by_span.get((frame.source.sha256, frame.source_span.char_start), ())
        same_base = any(_base(item.concept) == _base(frame.concept) for item in replacements)
        driver_takeover = any(
            _base(item.concept) in {"PRICE_REALIZATION", "ACTIVITY_VOLUME"}
            and _base(frame.concept) == "REVENUE"
            and item.value == frame.value
            for item in replacements
        )
        parallel_takeover = any(
            _base(item.concept) in {"OPERATING_MARGIN", "BOOK_TO_BILL"}
            and _base(frame.concept) == "OPERATING_INCOME"
            and item.value == frame.value
            for item in replacements
        )
        eps_antecedent = (
            _base(frame.concept) == "REVENUE"
            and "earnings per share" in frame.source_span.literal.casefold()
            and "sales projections" in frame.source_span.literal.casefold()
        )
        literal = frame.source_span.literal.casefold()
        cash_flow_not_balance = _base(frame.concept) == "CASH" and "cash flow" in literal
        maturity_ladder_not_level = (
            _base(frame.concept) == "DEBT" and "scheduled debt maturities" in literal
        )
        ambiguous_multi_segment = (
            _base(frame.concept) == "REVENUE"
            and "below our expectations" in literal
            and "all delivered" in literal
        )
        return (
            same_base
            or driver_takeover
            or parallel_takeover
            or eps_antecedent
            or cash_flow_not_balance
            or maturity_ladder_not_level
            or ambiguous_multi_segment
        )

    merged = (*(frame for frame in existing if not superseded(frame)), *recovered)
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
        if current is None or frame.rule_id.startswith("v280."):
            unique[signature] = frame
    return tuple(unique.values())
