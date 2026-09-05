from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
from math import isclose

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..document import document_text_blocks
from ..dsl import compile_text_rule_file
from ..model import ConceptMention, QuantityKind, QuantityMention, SemanticFrame
from ..ontology import definition_for
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v280 import semantics as frame_factory
from ..v281 import semantics as prior_semantics


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v282_upper_context.arc"
V282_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V282_RULES}
_ALIASES = {
    "adjusted ebit margin": "OPERATING_MARGIN",
    "adjusted ebit margins": "OPERATING_MARGIN",
    "average monthly realized rent": "PRICE_REALIZATION",
    "net client cash flows": "ACTIVITY_VOLUME",
    "net inflows": "ACTIVITY_VOLUME",
}
_NEGATIVE = {"decrease", "decline", "down", "lower", "below", "negative", "reduce", "offset"}
_POSITIVE = {"increase", "grow", "growth", "up", "higher", "positive", "expand", "improve"}
_FUTURE = {"expect", "guidance", "outlook", "estimate", "reiterate", "forecast", "project"}


def _base(concept: str) -> str:
    return prior_semantics._base(concept)


@lru_cache(maxsize=1)
def semantic_backend_v282():
    return prior_semantics.semantic_backend_v281()


def _tokens(backend, text: str):
    return tuple(token for token in backend.parse(text) if not token.is_space)


def _quantity(kind: QuantityKind, value: float, unit: str, raw: str, start: int, end: int):
    return QuantityMention(kind, value, unit, raw, start, end)


def semantic_quantities_v282(text: str, backend=None) -> tuple[QuantityMention, ...]:
    selected = backend or semantic_backend_v282()
    inherited = list(prior_semantics.semantic_quantities_v281(text, selected))
    output = []
    for item in inherited:
        following = text[item.char_end : item.char_end + 24].casefold().lstrip()
        if item.kind is QuantityKind.PERCENT and (
            "percentage point" in item.raw.casefold()
            or following.startswith("percentage point")
        ):
            output.append(replace(item, kind=QuantityKind.BASIS_POINTS, value=abs(item.value) * 100.0, unit="BASIS_POINTS"))
            continue
        if item.kind is QuantityKind.PERCENT and item.value < 0 and item.raw.startswith("-"):
            prior_percent = next(
                (prior for prior in reversed(output) if prior.kind is QuantityKind.PERCENT and item.char_start - prior.char_end <= 12),
                None,
            )
            if prior_percent is not None:
                output.append(replace(item, value=abs(item.value), raw=item.raw[1:], char_start=item.char_start + 1))
                continue
        output.append(item)
    occupied = {(item.char_start, item.char_end) for item in output}
    for token in _tokens(selected, text):
        folded = token.text.casefold()
        if not folded.endswith("pp"):
            continue
        numeric = folded[:-2].replace(",", "")
        try:
            value = float(numeric)
        except ValueError:
            continue
        span = (token.idx, token.idx + len(token.text))
        if span not in occupied:
            output.append(_quantity(QuantityKind.BASIS_POINTS, abs(value) * 100.0, "BASIS_POINTS", token.text, *span))
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end, item.kind.value)))


def semantic_concepts_v282(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v282()
    output = list(prior_semantics.semantic_concepts_v281(text, selected))
    for alias, concept in _ALIASES.items():
        output.extend(
            ConceptMention(concept, literal, start, end)
            for literal, start, end in selected.phrase_mentions(text, (alias,))
        )
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept)))


def augment_candidates_v282(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...]) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v282()
    output = list(candidates)
    seen = {(item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end) for item in output}
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v282(block.text, backend)
        for mention in semantic_concepts_v282(block.text, backend):
            signature = (block.char_start, mention.concept, mention.char_start, mention.char_end)
            if signature in seen or mention.alias.casefold() not in _ALIASES:
                continue
            allowed = set(definition_for(mention.concept).quantity_kinds) | {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS, QuantityKind.COUNT, QuantityKind.MONEY}
            compatible = tuple(item for item in quantities if item.kind in allowed and abs(item.char_start - mention.char_start) <= 320)
            if not compatible:
                continue
            candidate_id = sha256(f"{document.source.sha256}:{block.char_start}:{mention.concept}:{mention.char_start}:{mention.char_end}:v282".encode()).hexdigest()[:20]
            output.append(
                RecallCandidate(
                    candidate_id=candidate_id,
                    block=block,
                    metric=MetricAnchor(mention.concept, mention.alias, mention.char_start, mention.char_end),
                    quantities=compatible,
                    origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                    rule_ids=("v282.spacy_upper_context_alias",),
                )
            )
            seen.add(signature)
    return tuple(output)


def _new_frame(document, block, candidates, *, rule_id, concept, semantic, value, change=None, lower=None, upper=None, positive=True):
    frame = frame_factory._frame(
        document, block, candidates, rule_id="v280.parallel_metric_ownership", concept=concept,
        semantic=semantic, value=value, change=change, lower=lower, upper=upper, positive=positive,
    )
    if frame is None:
        return None
    rule = _RULE_BY_ID[rule_id]
    trace = dict(frame.context_trace)
    trace.update({"binding_eligibility": "V282_SPACY_UPPER_CONTEXT", "rule_program_sha256": rule.source_sha256})
    return replace(frame, rule_id=rule_id, rule_version=rule.version, verified_by="V282_SPACY_UPPER_CONTEXT_VERIFIER", context_trace=trace)


def _has(tokens, start: int, end: int, cues: set[str]) -> bool:
    return any(start <= token.idx < end and (token.lemma_.casefold() in cues or token.lower_ in cues) for token in tokens)


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


def _nearest_polarity(tokens, position: int, start: int, end: int, default: bool = True) -> bool:
    directional = []
    for token in tokens:
        if not start <= token.idx < end:
            continue
        cue = token.lemma_.casefold()
        if cue in _NEGATIVE or token.lower_ in _NEGATIVE:
            directional.append((abs(token.idx - position), False))
        elif cue in _POSITIVE or token.lower_ in _POSITIVE:
            directional.append((abs(token.idx - position), True))
    return min(directional, default=(0, default), key=lambda item: item[0])[1]


def _segment(text: str, backend, position: int):
    return prior_semantics._segment_for(text, backend, position)


def _mentions(concepts, names: set[str]):
    return prior_semantics._dedup_mentions(concepts, names)


def _range(document, block, candidates, rule_id, concept, low, high, positive=True):
    middle = replace(low, value=(low.value + high.value) / 2)
    return _new_frame(document, block, candidates, rule_id=rule_id, concept=concept, semantic=SemanticFrame.RANGE_GUIDANCE, value=middle, lower=low, upper=high, positive=positive)


def _margin_frames(document, block, candidates, concepts, quantities, backend):
    tokens = _tokens(backend, block.text)
    output = []
    for mention in _mentions(concepts, {"OPERATING_MARGIN", "GROSS_MARGIN"}):
        start, end = _segment(block.text, backend, mention.char_start)
        values = tuple(item for item in quantities if mention.char_end <= item.char_start < end)
        percents = tuple(item for item in values if item.kind is QuantityKind.PERCENT)
        basis = tuple(item for item in values if item.kind is QuantityKind.BASIS_POINTS)
        future = _has(tokens, start, end, _FUTURE)
        if future and len(percents) >= 2:
            made = _range(document, block, candidates, "v282.margin_role_context", f"{mention.concept}_GUIDANCE", percents[0], percents[1])
            if made is not None:
                output.append(made)
            continue
        if percents and basis:
            made = _new_frame(document, block, candidates, rule_id="v282.margin_role_context", concept=mention.concept, semantic=SemanticFrame.CHANGE_TO, value=percents[0], change=basis[0], positive=_nearest_polarity(tokens, basis[0].char_start, mention.char_end, end))
            if made is not None:
                output.append(made)
        elif basis:
            for value in basis:
                made = _new_frame(document, block, candidates, rule_id="v282.margin_role_context", concept=mention.concept, semantic=SemanticFrame.CHANGE_BY, value=value, positive=_nearest_polarity(tokens, value.char_start, mention.char_end, end))
                if made is not None:
                    output.append(made)
    return tuple(output)


def _revenue_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    tokens = _tokens(backend, block.text)
    mentions = _mentions(concepts, {"REVENUE"})
    if not mentions:
        return ()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    output = []
    if "respectively" in folded and "total" in folded and len(money) >= 3 and percents:
        for value in money[:2]:
            made = _new_frame(document, block, candidates, rule_id="v282.revenue_role_context", concept="REVENUE", semantic=SemanticFrame.ABSOLUTE_VALUE, value=value)
            if made is not None:
                output.append(made)
        made = _new_frame(document, block, candidates, rule_id="v282.revenue_role_context", concept="REVENUE", semantic=SemanticFrame.CHANGE_TO, value=money[2], change=percents[-1], positive=_polarity(tokens, money[2].char_end, len(block.text)))
        if made is not None:
            output.append(made)
        return tuple(output)
    if "comprised of" in folded and len(money) >= 3:
        net_of = folded.find("net of")
        for value in money:
            if net_of >= 0 and value.char_start >= net_of:
                continue
            made = _new_frame(document, block, candidates, rule_id="v282.revenue_role_context", concept="REVENUE", semantic=SemanticFrame.ABSOLUTE_VALUE, value=value)
            if made is not None:
                output.append(made)
        return tuple(output)
    if _has(tokens, 0, len(block.text), _FUTURE) and len(money) >= 2 and ("between" in folded or "range" in folded):
        made = _range(document, block, candidates, "v282.revenue_role_context", "REVENUE_GUIDANCE", money[0], money[1])
        return (made,) if made is not None else ()
    if "impact" in folded and money and percents and mentions[0].char_start > money[0].char_start:
        for value in (money[-1], percents[-1]):
            made = _new_frame(document, block, candidates, rule_id="v282.revenue_role_context", concept="REVENUE", semantic=SemanticFrame.CHANGE_BY, value=value, positive=_polarity(tokens, 0, mentions[0].char_end))
            if made is not None:
                output.append(made)
        return tuple(output)
    for mention in mentions:
        start, end = _segment(block.text, backend, mention.char_start)
        preposed = tuple(item for item in percents if start <= item.char_start < mention.char_start and mention.char_start - item.char_end <= 55)
        if preposed and _has(tokens, preposed[-1].char_end, mention.char_start, {"increase", "decrease"}):
            value = preposed[-1]
            made = _new_frame(document, block, candidates, rule_id="v282.revenue_role_context", concept="REVENUE", semantic=SemanticFrame.CHANGE_BY, value=value, positive=_polarity(tokens, value.char_start, mention.char_end))
            if made is not None:
                output.append(made)
            continue
        local_money = tuple(item for item in money if mention.char_end <= item.char_start < end)
        if not local_money:
            continue
        level = local_money[0]
        if (
            _has(tokens, mention.char_end, level.char_start, {"increase", "decrease"})
            and not _has(tokens, mention.char_end, level.char_start, {"of", "to"})
        ):
            made = _new_frame(
                document,
                block,
                candidates,
                rule_id="v282.revenue_role_context",
                concept="REVENUE",
                semantic=SemanticFrame.CHANGE_BY,
                value=level,
                positive=_nearest_polarity(tokens, level.char_start, mention.char_end, end),
            )
            if made is not None:
                output.append(made)
            continue
        local_percent = tuple(item for item in percents if mention.char_end <= item.char_start < end)
        owned = tuple(item for item in local_percent if item.char_start < level.char_start or item.char_start - level.char_end <= 80)
        if owned:
            change = owned[0]
            made = _new_frame(document, block, candidates, rule_id="v282.revenue_role_context", concept="REVENUE", semantic=SemanticFrame.CHANGE_TO, value=level, change=change, positive=_nearest_polarity(tokens, change.char_start, mention.char_end, end))
        else:
            made = _new_frame(document, block, candidates, rule_id="v282.revenue_role_context", concept="REVENUE", semantic=SemanticFrame.ABSOLUTE_VALUE, value=level)
        if made is not None:
            output.append(made)
    return tuple(output)


def _driver_frames(document, block, candidates, concepts, quantities, backend):
    tokens = _tokens(backend, block.text)
    output = []
    mentions = _mentions(concepts, {"PRICE_REALIZATION", "ACTIVITY_VOLUME"})
    for index, mention in enumerate(mentions):
        start, end = _segment(block.text, backend, mention.char_start)
        next_start = mentions[index + 1].char_start if index + 1 < len(mentions) and mentions[index + 1].char_start < end else end
        if mention.concept == "ACTIVITY_VOLUME" and mention.alias.casefold() in {"net client cash flows", "net inflows"}:
            values = tuple(item for item in quantities if item.kind is QuantityKind.MONEY and mention.char_end <= item.char_start < next_start)
            for value in values:
                made = _new_frame(document, block, candidates, rule_id="v282.driver_role_context", concept="ACTIVITY_VOLUME", semantic=SemanticFrame.ABSOLUTE_VALUE, value=value)
                if made is not None:
                    output.append(made)
        elif mention.concept == "PRICE_REALIZATION":
            values = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT and mention.char_end <= item.char_start < next_start)
            if not values:
                preceding = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT and item.char_end <= mention.char_start and mention.char_start - item.char_end <= 55)
                values = preceding[-1:] if preceding else ()
            for value in values:
                made = _new_frame(document, block, candidates, rule_id="v282.driver_role_context", concept="PRICE_REALIZATION", semantic=SemanticFrame.CHANGE_BY, value=value, positive=_polarity(tokens, min(value.char_start, mention.char_start), max(value.char_end, mention.char_end)))
                if made is not None:
                    output.append(made)
    if "volumes" in block.text.casefold() and "respectively" in block.text.casefold():
        values = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
        for value in values[:2]:
            made = _new_frame(document, block, candidates, rule_id="v282.driver_role_context", concept="ACTIVITY_VOLUME", semantic=SemanticFrame.CHANGE_BY, value=value, positive=_polarity(tokens, 0, value.char_end))
            if made is not None:
                output.append(made)
    return tuple(output)


def _metric_pair_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    tokens = _tokens(backend, block.text)
    output = []
    if "adjusted ebit" in folded and "margin" not in folded:
        mentions = _mentions(concepts, {"EBIT"})
        money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
        percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
        for index, mention in enumerate(mentions):
            left = mentions[index - 1].char_end if index else 0
            right = mentions[index + 1].char_start if index + 1 < len(mentions) else len(block.text)
            levels = tuple(item for item in money if left <= item.char_start < right)
            changes = tuple(item for item in percents if mention.char_end <= item.char_start < right)
            if not levels or not changes:
                continue
            level = min(levels, key=lambda item: abs(item.char_start - mention.char_start))
            made = _new_frame(document, block, candidates, rule_id="v282.metric_pair_context", concept="EBIT", semantic=SemanticFrame.CHANGE_TO, value=level, change=changes[0], positive=_polarity(tokens, mention.char_start, right))
            if made is not None:
                output.append(made)
    if "adjusted ebitda" in folded and "respectively" in folded:
        mention = next((item for item in concepts if item.concept == "ADJUSTED_EBITDA"), None)
        respective_at = folded.find("respectively", mention.char_end if mention is not None else 0)
        values = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT and (mention is None or item.char_start >= mention.char_end))
        if mention is not None and respective_at >= 0 and values:
            made = _new_frame(document, block, candidates, rule_id="v282.metric_pair_context", concept="ADJUSTED_EBITDA", semantic=SemanticFrame.CHANGE_BY, value=values[0], positive=_polarity(tokens, mention.char_end, values[0].char_end))
            if made is not None:
                output.append(made)
    if "thousand shares" in folded and "respectively" in folded:
        numeric = []
        for token in _tokens(backend, block.text):
            if not token.like_num:
                continue
            try:
                value = float(token.text.replace(",", ""))
            except ValueError:
                continue
            if value >= 10_000:
                numeric.append(_quantity(QuantityKind.COUNT, value * 1_000.0, "SHARES", token.text, token.idx, token.idx + len(token.text)))
        if len(numeric) >= 2:
            current = _new_frame(document, block, candidates, rule_id="v282.metric_pair_context", concept="SHARES", semantic=SemanticFrame.COMPARATIVE, value=numeric[0])
            prior = _new_frame(document, block, candidates, rule_id="v282.metric_pair_context", concept="PRIOR_YEAR_SHARES", semantic=SemanticFrame.COMPARATIVE, value=numeric[1])
            output.extend(frame for frame in (current, prior) if frame is not None)
    return tuple(output)


def _highlight_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if "highlights" not in folded:
        return ()
    tokens = _tokens(backend, block.text)
    output = []
    ebitda = next((item for item in concepts if item.concept == "ADJUSTED_EBITDA"), None)
    capex = next((item for item in concepts if item.concept == "CAPEX"), None)
    production = next((item for item in concepts if item.concept == "PRODUCTION"), None)
    if ebitda is not None:
        money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY and ebitda.char_end <= item.char_start)
        rates = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT and ebitda.char_end <= item.char_start)
        if money and rates:
            made = _new_frame(document, block, candidates, rule_id="v282.metric_pair_context", concept="ADJUSTED_EBITDA", semantic=SemanticFrame.CHANGE_TO, value=money[0], change=rates[0], positive=_polarity(tokens, ebitda.char_end, rates[0].char_end))
            if made is not None:
                output.append(made)
    if capex is not None:
        money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
        if money:
            value = min(money, key=lambda item: abs(item.char_start - capex.char_start))
            made = _new_frame(document, block, candidates, rule_id="v282.metric_pair_context", concept="CAPEX", semantic=SemanticFrame.ABSOLUTE_VALUE, value=value)
            if made is not None:
                output.append(made)
    if production is not None:
        parsed = _tokens(backend, block.text)
        for index, token in enumerate(parsed):
            if "bcf" not in token.text.casefold() or index == 0:
                continue
            prior = parsed[index - 1]
            try:
                level = _quantity(QuantityKind.COUNT, float(prior.text.replace(",", "")), "BCF_PER_DAY", prior.text, prior.idx, prior.idx + len(prior.text))
            except ValueError:
                continue
            rates = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT and item.char_start >= production.char_end)
            if rates:
                made = _new_frame(document, block, candidates, rule_id="v282.driver_role_context", concept="PRODUCTION", semantic=SemanticFrame.CHANGE_TO, value=level, change=rates[0], positive=_polarity(tokens, production.char_end, rates[0].char_end))
                if made is not None:
                    output.append(made)
            break
    return tuple(output)


def recover_v282_frames(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...], allowed_spans: set[tuple[int, int]]):
    backend = semantic_backend_v282()
    blocks = {(item.block.char_start, item.block.char_end): item.block for item in candidates}
    output = []
    for span, block in blocks.items():
        if span not in allowed_spans:
            continue
        concepts = semantic_concepts_v282(block.text, backend)
        quantities = semantic_quantities_v282(block.text, backend)
        for binder in (_margin_frames, _revenue_frames, _driver_frames, _metric_pair_frames, _highlight_frames):
            output.extend(binder(document, block, candidates, concepts, quantities, backend))
    unique = {}
    for frame in output:
        signature = (frame.concept, frame.frame, round(frame.value, 6), None if frame.change is None else round(frame.change, 6), frame.lower_value, frame.upper_value, frame.polarity.positive, frame.source.sha256, frame.source_span.char_start)
        unique[signature] = frame
    return tuple(unique.values())


def resolve_frame_conflicts_v282(existing, recovered):
    first = prior_semantics.resolve_frame_conflicts_v281(existing, recovered)

    def numbers(frame):
        return tuple(value for value in (frame.value, frame.change, frame.lower_value, frame.upper_value) if value is not None)

    def overlaps(frame, item):
        return item.source.sha256 == frame.source.sha256 and item.source_span.char_start <= frame.source_span.char_start and frame.source_span.char_end <= item.source_span.char_end

    def close_values(left, right):
        return any(isclose(a, b, rel_tol=1e-10, abs_tol=1e-6) for a in numbers(left) for b in numbers(right))

    def superseded(frame):
        replacements = tuple(item for item in recovered if overlaps(frame, item))
        literal = frame.source_span.literal.casefold()
        same = any(_base(item.concept) == _base(frame.concept) and close_values(item, frame) for item in replacements)
        margin_revenue = frame.concept.startswith("REVENUE") and "margin" in literal and any(_base(item.concept) in {"OPERATING_MARGIN", "GROSS_MARGIN"} and close_values(item, frame) for item in replacements)
        combined_cash = frame.concept == "CASH" and "cash and agency mbs" in literal
        expense_rate = (
            frame.concept == "REVENUE"
            and ("decrease in expenses" in literal or "operating expenses" in literal)
            and any(item.concept == "REVENUE" for item in replacements)
        )
        respectively_metric = frame.concept == "ADJUSTED_EBITDA" and "respectively" in literal and any(item.concept == "ADJUSTED_EBITDA" for item in replacements)
        operating_guidance_revenue = (
            frame.concept.startswith("REVENUE")
            and "operating margin" in literal
            and any(item.concept == "OPERATING_MARGIN_GUIDANCE" for item in replacements)
        )
        return same or margin_revenue or combined_cash or expense_rate or respectively_metric or operating_guidance_revenue

    merged = (*(frame for frame in first if not superseded(frame)), *recovered)
    unique = {}
    for frame in merged:
        signature = (
            frame.concept, frame.frame, round(frame.value, 4),
            None if frame.change is None else round(frame.change, 4),
            None if frame.lower_value is None else round(frame.lower_value, 4),
            None if frame.upper_value is None else round(frame.upper_value, 4),
            frame.polarity.positive, frame.source.sha256, frame.source_span.char_start,
        )
        current = unique.get(signature)
        if current is None or frame.rule_id.startswith("v282."):
            unique[signature] = frame
    return tuple(unique.values())
