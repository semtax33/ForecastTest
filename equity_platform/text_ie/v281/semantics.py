from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..document import document_text_blocks
from ..dsl import compile_text_rule_file
from ..model import ConceptMention, QuantityKind, QuantityMention, SemanticFrame
from ..ontology import definition_for
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v279.semantics import _segments
from ..v280 import semantics as prior_semantics


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v281_hierarchical_context.arc"
V281_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V281_RULES}
_ALIASES = {
    "shipments": "ACTIVITY_VOLUME",
    "total shipments": "ACTIVITY_VOLUME",
    "passenger unit revenue": "PRICE_REALIZATION",
    "experiences supply": "ACTIVITY_VOLUME",
    "supply": "ACTIVITY_VOLUME",
    "nights booked": "ORDERS",
    "seats booked": "ORDERS",
}
_NEGATIVE = {"decrease", "decline", "down", "lower", "below", "headwind", "reduce", "offset"}
_POSITIVE = {"increase", "grow", "up", "higher", "benefit", "expand", "improve"}
_FUTURE = {"expect", "anticipate", "project", "guidance", "outlook", "plan", "reaffirm"}


def _base(concept: str) -> str:
    result = concept.removeprefix("PRIOR_YEAR_")
    while True:
        prior = result
        result = result.removesuffix("_GUIDANCE").removesuffix("_CHANGE")
        if result == prior:
            return result


@lru_cache(maxsize=1)
def semantic_backend_v281():
    return prior_semantics.semantic_backend_v280()


def _tokens(backend, text: str):
    return tuple(token for token in backend.parse(text) if not token.is_space)


def semantic_quantities_v281(text: str, backend=None) -> tuple[QuantityMention, ...]:
    selected = backend or semantic_backend_v281()
    output = list(prior_semantics.semantic_quantities_v280(text, selected))
    occupied = {(item.char_start, item.char_end) for item in output}
    tokens = _tokens(selected, text)
    for index, token in enumerate(tokens):
        if not token.like_num or token.idx < 0:
            continue
        following = tokens[index + 1 : index + 6]
        has_million = any(item.lemma_.casefold() == "million" for item in following)
        has_metric_tons = (
            any(item.lemma_.casefold() == "metric" for item in following)
            and any(item.lemma_.casefold() == "ton" for item in following)
        )
        if not has_million or not has_metric_tons:
            continue
        span = (token.idx, token.idx + len(token.text))
        if span in occupied:
            continue
        try:
            value = float(token.text.replace(",", "")) * 1_000_000.0
        except ValueError:
            continue
        output.append(
            QuantityMention(
                QuantityKind.COUNT,
                value,
                "METRIC_TONS",
                token.text,
                span[0],
                span[1],
            )
        )
        occupied.add(span)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end)))


def semantic_concepts_v281(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v281()
    output = list(prior_semantics.semantic_concepts_v280(text, selected))
    for alias, concept in _ALIASES.items():
        output.extend(
            ConceptMention(concept, literal, start, end)
            for literal, start, end in selected.phrase_mentions(text, (alias,))
        )
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept)))


def augment_candidates_v281(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...]) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v281()
    output = list(candidates)
    seen = {
        (item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end)
        for item in output
    }
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v281(block.text, backend)
        for mention in semantic_concepts_v281(block.text, backend):
            signature = (block.char_start, mention.concept, mention.char_start, mention.char_end)
            if signature in seen or mention.alias.casefold() not in _ALIASES:
                continue
            allowed = set(definition_for(mention.concept).quantity_kinds) | {
                QuantityKind.PERCENT,
                QuantityKind.BASIS_POINTS,
                QuantityKind.COUNT,
            }
            compatible = tuple(
                item for item in quantities
                if item.kind in allowed and abs(item.char_start - mention.char_start) <= 260
            )
            if not compatible:
                continue
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:"
                f"{mention.char_start}:{mention.char_end}:v281".encode()
            ).hexdigest()[:20]
            output.append(
                RecallCandidate(
                    candidate_id=candidate_id,
                    block=block,
                    metric=MetricAnchor(mention.concept, mention.alias, mention.char_start, mention.char_end),
                    quantities=compatible,
                    origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                    rule_ids=("v281.spacy_hierarchical_context_alias",),
                )
            )
            seen.add(signature)
    return tuple(output)


def _new_frame(document, block, candidates, *, rule_id, concept, semantic, value, change=None, lower=None, upper=None, positive=True):
    frame = prior_semantics._frame(
        document,
        block,
        candidates,
        rule_id="v280.parallel_metric_ownership",
        concept=concept,
        semantic=semantic,
        value=value,
        change=change,
        lower=lower,
        upper=upper,
        positive=positive,
    )
    if frame is None:
        return None
    rule = _RULE_BY_ID[rule_id]
    trace = dict(frame.context_trace)
    trace.update(
        {
            "binding_eligibility": "V281_SPACY_HIERARCHICAL_CONTEXT",
            "rule_program_sha256": rule.source_sha256,
        }
    )
    return replace(
        frame,
        rule_id=rule_id,
        rule_version=rule.version,
        verified_by="V281_SPACY_HIERARCHICAL_CONTEXT_VERIFIER",
        context_trace=trace,
    )


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


def _segment_for(text: str, backend, position: int) -> tuple[int, int]:
    return next(
        ((start, end) for start, end in _segments(text, backend) if start <= position < end),
        (0, len(text)),
    )


def _dedup_mentions(concepts, names: set[str]):
    ordered = sorted(
        (item for item in concepts if item.concept in names),
        key=lambda item: (item.char_start, -(item.char_end - item.char_start)),
    )
    output = []
    for mention in ordered:
        if any(
            prior.concept == mention.concept
            and prior.char_start <= mention.char_start
            and mention.char_end <= prior.char_end
            for prior in output
        ):
            continue
        output.append(mention)
    return tuple(output)


def _range_frame(document, block, candidates, *, rule_id, concept, values, positive=True):
    low, high = values
    midpoint = replace(low, value=(low.value + high.value) / 2)
    return _new_frame(
        document,
        block,
        candidates,
        rule_id=rule_id,
        concept=concept,
        semantic=SemanticFrame.RANGE_GUIDANCE,
        value=midpoint,
        lower=low,
        upper=high,
        positive=positive,
    )


def _is_linked_range(tokens, low, high, start: int) -> bool:
    return (
        _has(tokens, start, low.char_start, {"between"})
        or _has(tokens, low.char_end, high.char_start, {"to"})
    )


def _revenue_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if "passenger unit revenue" in folded:
        return ()
    if "repositioning sales" in folded and "securities" in folded:
        return ()
    mentions = _dedup_mentions(concepts, {"REVENUE"})
    if not mentions:
        return ()
    tokens = _tokens(backend, block.text)
    output = []
    for mention in mentions:
        start, end = _segment_for(block.text, backend, mention.char_start)
        local_money = tuple(
            item for item in quantities
            if item.kind is QuantityKind.MONEY and mention.char_end <= item.char_start < end
        )
        local_percent = tuple(
            item for item in quantities
            if item.kind is QuantityKind.PERCENT and mention.char_end <= item.char_start < end
        )
        future = _has(tokens, start, end, _FUTURE)
        actual_reported = _has(tokens, mention.char_end, end, {"report"})
        if len(local_percent) == 2 and _is_linked_range(tokens, local_percent[0], local_percent[1], mention.char_end):
            frame = _range_frame(document, block, candidates, rule_id="v281.range_guidance_context", concept="REVENUE_CHANGE_GUIDANCE", values=local_percent)
            if frame is not None:
                output.append(frame)
            continue
        if future and not actual_reported and local_percent:
            for value in local_percent:
                made = _new_frame(document, block, candidates, rule_id="v281.range_guidance_context", concept="REVENUE_CHANGE_GUIDANCE", semantic=SemanticFrame.ABSOLUTE_VALUE, value=value, positive=_polarity(tokens, mention.char_start, value.char_start))
                if made is not None:
                    output.append(made)
            continue
        if local_money:
            level = local_money[0]
            level_is_delta = (
                _has(tokens, mention.char_end, level.char_start, {"increase", "decrease", "higher", "lower"})
                and not _has(tokens, mention.char_end, level.char_start, {"of", "to"})
            )
            if level_is_delta:
                made = _new_frame(
                    document,
                    block,
                    candidates,
                    rule_id="v281.local_revenue_context",
                    concept="REVENUE",
                    semantic=SemanticFrame.CHANGE_BY,
                    value=level,
                    positive=_polarity(tokens, mention.char_end, level.char_start),
                )
                if made is not None:
                    output.append(made)
                continue
            if local_percent:
                for change in local_percent:
                    made = _new_frame(document, block, candidates, rule_id="v281.local_revenue_context", concept="REVENUE", semantic=SemanticFrame.CHANGE_TO, value=level, change=change, positive=_polarity(tokens, mention.char_start, change.char_start))
                    if made is not None:
                        output.append(made)
            else:
                made = _new_frame(document, block, candidates, rule_id="v281.local_revenue_context", concept="REVENUE", semantic=SemanticFrame.ABSOLUTE_VALUE, value=level)
                if made is not None:
                    output.append(made)
            for delta in local_money[1:]:
                directional_between = _has(tokens, level.char_end, delta.char_start, {"increase", "decrease", "higher", "lower"})
                comparative_delta = (
                    _has(tokens, level.char_end, delta.char_start, {"be"})
                    and _has(tokens, delta.char_end, end, {"higher", "lower"})
                )
                if not directional_between and not comparative_delta:
                    continue
                made = _new_frame(document, block, candidates, rule_id="v281.local_revenue_context", concept="REVENUE", semantic=SemanticFrame.CHANGE_BY, value=delta, positive=_polarity(tokens, level.char_end, end))
                if made is not None:
                    output.append(made)
        elif local_percent:
            for value in local_percent:
                made = _new_frame(document, block, candidates, rule_id="v281.local_revenue_context", concept="REVENUE", semantic=SemanticFrame.CHANGE_BY, value=value, positive=_polarity(tokens, mention.char_start, value.char_start))
                if made is not None:
                    output.append(made)
    return tuple(output)


def _driver_frames(document, block, candidates, concepts, quantities, backend):
    tokens = _tokens(backend, block.text)
    output = []
    mentions = _dedup_mentions(concepts, {"PRICE_REALIZATION", "ACTIVITY_VOLUME", "ORDERS"})
    order_range = "bookings growth of" in block.text.casefold()
    for index, mention in enumerate(mentions):
        if mention.concept == "ORDERS" and order_range:
            continue
        start, segment_end = _segment_for(block.text, backend, mention.char_start)
        if mention.concept == "ORDERS" and any(
            item.kind is QuantityKind.MONEY and mention.char_end <= item.char_start < segment_end
            for item in quantities
        ):
            continue
        next_start = mentions[index + 1].char_start if index + 1 < len(mentions) and mentions[index + 1].char_start < segment_end else segment_end
        values = tuple(
            item for item in quantities
            if item.kind is QuantityKind.PERCENT and mention.char_end <= item.char_start < next_start
        )
        if not values and mention.concept == "ACTIVITY_VOLUME":
            values = tuple(
                item for item in quantities
                if item.kind is QuantityKind.PERCENT
                and item.char_end <= mention.char_start
                and mention.char_start - item.char_end <= 45
                and _has(tokens, item.char_end, mention.char_start, {"increase", "grow", "up"})
            )
        for value in values:
            made = _new_frame(document, block, candidates, rule_id="v281.economic_driver_context", concept=mention.concept, semantic=SemanticFrame.CHANGE_BY, value=value, positive=_polarity(tokens, mention.char_start, value.char_start))
            if made is not None:
                output.append(made)
    return tuple(output)


def _orders_actual_frames(document, block, candidates, concepts, quantities, backend):
    tokens = _tokens(backend, block.text)
    output = []
    for mention in _dedup_mentions(concepts, {"ORDERS"}):
        start, end = _segment_for(block.text, backend, mention.char_start)
        if _has(tokens, start, end, _FUTURE):
            continue
        money = tuple(
            item for item in quantities
            if item.kind is QuantityKind.MONEY and mention.char_end <= item.char_start < end
        )
        percents = tuple(
            item for item in quantities
            if item.kind is QuantityKind.PERCENT and mention.char_end <= item.char_start < end
        )
        if not money or not percents:
            continue
        made = _new_frame(
            document,
            block,
            candidates,
            rule_id="v281.actual_level_change_context",
            concept="ORDERS",
            semantic=SemanticFrame.CHANGE_TO,
            value=money[0],
            change=percents[0],
            positive=_polarity(tokens, mention.char_end, percents[0].char_start),
        )
        if made is not None:
            output.append(made)
    return tuple(output)


def _orders_guidance_frames(document, block, candidates, concepts, quantities, backend):
    if "bookings growth of" not in block.text.casefold():
        return ()
    mentions = tuple(item for item in concepts if item.concept == "ORDERS")
    values = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    if not mentions or len(values) < 2:
        return ()
    made = _range_frame(
        document,
        block,
        candidates,
        rule_id="v281.range_guidance_context",
        concept="ORDERS_CHANGE_GUIDANCE",
        values=values[:2],
    )
    return (made,) if made is not None else ()


def _physical_guidance_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if "production" not in folded or "shipments" not in folded or "respectively" not in folded:
        return ()
    values = tuple(item for item in quantities if item.kind is QuantityKind.COUNT and item.unit == "METRIC_TONS")
    if len(values) < 4:
        return ()
    first = _range_frame(document, block, candidates, rule_id="v281.physical_range_guidance", concept="PRODUCTION_GUIDANCE", values=values[:2])
    second = _range_frame(document, block, candidates, rule_id="v281.physical_range_guidance", concept="ACTIVITY_VOLUME_GUIDANCE", values=values[2:4])
    return tuple(frame for frame in (first, second) if frame is not None)


def _ebitda_frames(document, block, candidates, concepts, quantities, backend):
    mentions = _dedup_mentions(concepts, {"ADJUSTED_EBITDA"})
    if not mentions:
        return ()
    mention = mentions[0]
    tokens = _tokens(backend, block.text)
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY and item.char_start >= mention.char_end)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    future = _has(tokens, 0, len(block.text), _FUTURE)
    if future and len(percents) >= 2:
        made = _range_frame(document, block, candidates, rule_id="v281.range_guidance_context", concept="ADJUSTED_EBITDA_CHANGE_GUIDANCE", values=percents[:2])
        return (made,) if made is not None else ()
    if len(money) >= 2 and percents and _has(tokens, money[0].char_end, len(block.text), {"compare"}):
        current = _new_frame(document, block, candidates, rule_id="v281.metric_comparison_context", concept="ADJUSTED_EBITDA", semantic=SemanticFrame.COMPARATIVE, value=money[0])
        prior = _new_frame(document, block, candidates, rule_id="v281.metric_comparison_context", concept="PRIOR_YEAR_ADJUSTED_EBITDA", semantic=SemanticFrame.COMPARATIVE, value=money[1])
        change = _new_frame(document, block, candidates, rule_id="v281.metric_comparison_context", concept="ADJUSTED_EBITDA", semantic=SemanticFrame.CHANGE_BY, value=percents[0], positive=_polarity(tokens, mention.char_start, percents[0].char_start))
        return tuple(frame for frame in (current, prior, change) if frame is not None)
    return ()


def _margin_frames(document, block, candidates, concepts, quantities, backend):
    mentions = _dedup_mentions(concepts, {"OPERATING_MARGIN"})
    if not mentions:
        return ()
    mention = mentions[0]
    tokens = _tokens(backend, block.text)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT and item.char_start >= mention.char_end)
    basis = tuple(item for item in quantities if item.kind is QuantityKind.BASIS_POINTS and item.char_start >= mention.char_end)
    if not basis:
        return ()
    output = []
    include_matches = prior_semantics.semantic_backend_v280().phrase_mentions(block.text, ("including",))
    include_at = include_matches[0][1] if include_matches else None
    close_at = block.text.find(")", include_at) if include_at is not None else -1
    component = tuple(item for item in basis if include_at is not None and include_at <= item.char_start < close_at)
    primary = tuple(item for item in basis if close_at < item.char_start)
    if percents and primary:
        made = _new_frame(document, block, candidates, rule_id="v281.parallel_margin_context", concept="OPERATING_MARGIN", semantic=SemanticFrame.CHANGE_TO, value=percents[0], change=primary[0], positive=_polarity(tokens, mention.char_start, primary[0].char_start))
        if made is not None:
            output.append(made)
        residual = primary[1:]
    else:
        residual = basis
    for value in (*component, *residual):
        made = _new_frame(document, block, candidates, rule_id="v281.parallel_margin_context", concept="OPERATING_MARGIN", semantic=SemanticFrame.CHANGE_BY, value=value, positive=_polarity(tokens, mention.char_start, value.char_start))
        if made is not None:
            output.append(made)
    return tuple(output)


def _capex_guidance_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if "capex plan" not in folded and "capital expenditures plan" not in folded:
        return ()
    mentions = tuple(item for item in concepts if item.concept == "CAPEX")
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    if not mentions or not money:
        return ()
    value = min(money, key=lambda item: abs(item.char_start - mentions[0].char_start))
    made = _new_frame(document, block, candidates, rule_id="v281.range_guidance_context", concept="CAPEX_GUIDANCE", semantic=SemanticFrame.ABSOLUTE_VALUE, value=value)
    return (made,) if made is not None else ()


def recover_v281_frames(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...], allowed_spans: set[tuple[int, int]]):
    backend = semantic_backend_v281()
    blocks = {(item.block.char_start, item.block.char_end): item.block for item in candidates}
    output = []
    for span, block in blocks.items():
        if span not in allowed_spans:
            continue
        concepts = semantic_concepts_v281(block.text, backend)
        quantities = semantic_quantities_v281(block.text, backend)
        for binder in (_revenue_frames, _driver_frames, _orders_actual_frames, _orders_guidance_frames, _physical_guidance_frames, _ebitda_frames, _margin_frames, _capex_guidance_frames):
            output.extend(binder(document, block, candidates, concepts, quantities, backend))
    unique = {}
    for frame in output:
        signature = (frame.concept, frame.frame, frame.value, frame.change, frame.lower_value, frame.upper_value, frame.polarity.positive, frame.source.sha256, frame.source_span.char_start)
        unique[signature] = frame
    return tuple(unique.values())


def resolve_frame_conflicts_v281(existing, recovered):
    def numbers(frame):
        return {
            value for value in (frame.value, frame.change, frame.lower_value, frame.upper_value)
            if value is not None
        }

    def superseded(frame):
        replacements = tuple(
            item for item in recovered
            if item.source.sha256 == frame.source.sha256
            and item.source_span.char_start <= frame.source_span.char_start
            and frame.source_span.char_end <= item.source_span.char_end
        )
        literal = frame.source_span.literal.casefold()
        same_base = any(
            _base(item.concept) == _base(frame.concept)
            and bool(numbers(item) & numbers(frame))
            for item in replacements
        )
        price_over_revenue = _base(frame.concept) == "REVENUE" and any(
            _base(item.concept) == "PRICE_REALIZATION"
            and bool(numbers(item) & numbers(frame))
            for item in replacements
        )
        causal_driver = (
            _base(frame.concept) in {"ACTIVITY_VOLUME", "PRICE_REALIZATION"}
            and "revenue" in literal
            and ("on lower volumes" in literal or "on higher volumes" in literal)
            and any(_base(item.concept) == "REVENUE" and item.value == frame.value for item in replacements)
        )
        capex_plan_over_income_change = (
            frame.concept == "CAPEX"
            and frame.rule_id == "v261.kpi_change"
            and "net income" in literal
            and any(item.concept == "CAPEX_GUIDANCE" for item in replacements)
        )
        negative_cash = _base(frame.concept) == "CASH" and any(phrase in literal for phrase in ("cash used for", "cash dividend", "cash returns to shareholders"))
        securities_sales = _base(frame.concept) == "REVENUE" and "repositioning sales" in literal and "securities" in literal
        return same_base or price_over_revenue or causal_driver or capex_plan_over_income_change or negative_cash or securities_sales

    merged = (*(frame for frame in existing if not superseded(frame)), *recovered)
    unique = {}
    for frame in merged:
        signature = (frame.concept, frame.frame, frame.value, frame.change, frame.lower_value, frame.upper_value, frame.polarity.positive, frame.source.sha256, frame.source_span.char_start)
        current = unique.get(signature)
        if current is None or frame.rule_id.startswith("v281."):
            unique[signature] = frame
    return tuple(unique.values())
