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
from ..v283 import semantics as prior_semantics


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v284_economic_roles.arc"
V284_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V284_RULES}
_ALIASES = {
    "patient days": "ACTIVITY_VOLUME",
    "revenue per patient day": "PRICE_REALIZATION",
    "revenue per advisor": "PRICE_REALIZATION",
    "solutions sales": "ACTIVITY_VOLUME",
    "follow-on contract": "ORDERS",
    "segment earnings margin": "OPERATING_MARGIN",
}
_NEGATIVE = {"decrease", "decline", "down", "lower", "reduce", "reduction"}
_POSITIVE = {"increase", "grow", "growth", "up", "higher", "improve"}


def _base(concept: str) -> str:
    return prior_semantics._base(concept)


@lru_cache(maxsize=1)
def semantic_backend_v284():
    return prior_semantics.semantic_backend_v283()


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


def _mentions(concepts, names: set[str]):
    return prior_semantics._mentions(concepts, names)


def _quantity(kind, value, unit, token):
    return QuantityMention(
        kind,
        value,
        unit,
        token.text,
        token.idx,
        token.idx + len(token.text),
    )


def semantic_quantities_v284(text: str, backend=None) -> tuple[QuantityMention, ...]:
    selected = backend or semantic_backend_v284()
    output = list(prior_semantics.semantic_quantities_v283(text, selected))
    occupied = {(item.char_start, item.char_end, item.kind) for item in output}
    tokens = _tokens(selected, text)
    folded = text.casefold()
    for index, token in enumerate(tokens):
        if not token.like_num:
            continue
        following = tokens[index + 1 : index + 6]
        has_million = any(item.lemma_.casefold() == "million" for item in following)
        if not has_million:
            continue
        is_share = "shares outstanding" in folded
        is_cubic_feet = "cubic feet" in folded and "per day" in folded
        if not (is_share or is_cubic_feet):
            continue
        signature = (token.idx, token.idx + len(token.text), QuantityKind.COUNT)
        if signature in occupied:
            continue
        try:
            value = float(token.text.replace(",", "")) * 1_000_000.0
        except ValueError:
            continue
        unit = "SHARES" if is_share else "CUBIC_FEET_PER_DAY"
        output.append(_quantity(QuantityKind.COUNT, value, unit, token))
        occupied.add(signature)
    basis_mentions = selected.phrase_mentions(text, ("basis points",))
    for _, basis_start, _ in basis_mentions:
        coordinated = tuple(
            token
            for token in tokens
            if token.like_num and 0 <= basis_start - token.idx <= 80
        )
        for token in coordinated[-2:]:
            try:
                value = float(token.text.replace(",", ""))
            except ValueError:
                continue
            output.append(_quantity(QuantityKind.BASIS_POINTS, value, "BASIS_POINTS", token))
    unique = {}
    for item in output:
        signature = (item.kind, round(item.value, 9), item.char_start)
        current = unique.get(signature)
        if current is None or (item.char_end - item.char_start) > (current.char_end - current.char_start):
            unique[signature] = item
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.kind.value)))


def semantic_concepts_v284(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v284()
    output = list(prior_semantics.semantic_concepts_v283(text, selected))
    for alias, concept in _ALIASES.items():
        output.extend(
            ConceptMention(concept, literal, start, end)
            for literal, start, end in selected.phrase_mentions(text, (alias,))
        )
    folded = text.casefold()
    if "adjusted ebitda" in folded and "a margin of" in folded:
        for mention in tuple(output):
            if mention.concept == "ADJUSTED_EBITDA":
                output.append(
                    ConceptMention(
                        "ADJUSTED_EBITDA_MARGIN",
                        mention.alias,
                        mention.char_start,
                        mention.char_end,
                    )
                )
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept)))


def augment_candidates_v284(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v284()
    output = list(candidates)
    seen = {
        (item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end)
        for item in output
    }
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v284(block.text, backend)
        if not quantities:
            continue
        for mention in semantic_concepts_v284(block.text, backend):
            signature = (block.char_start, mention.concept, mention.char_start, mention.char_end)
            if signature in seen:
                continue
            allowed = set(definition_for(mention.concept).quantity_kinds) | {
                QuantityKind.MONEY,
                QuantityKind.PERCENT,
                QuantityKind.BASIS_POINTS,
                QuantityKind.COUNT,
            }
            compatible = tuple(
                item
                for item in quantities
                if item.kind in allowed and abs(item.char_start - mention.char_start) <= 640
            )
            if not compatible:
                continue
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:"
                f"{mention.char_start}:{mention.char_end}:v284".encode()
            ).hexdigest()[:20]
            output.append(
                RecallCandidate(
                    candidate_id=candidate_id,
                    block=block,
                    metric=MetricAnchor(mention.concept, mention.alias, mention.char_start, mention.char_end),
                    quantities=compatible,
                    origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                    rule_ids=("v284.spacy_economic_role_candidate",),
                )
            )
            seen.add(signature)
    return tuple(output)


def _new_frame(
    document,
    block,
    candidates,
    *,
    rule_id,
    concept,
    semantic,
    value,
    change=None,
    lower=None,
    upper=None,
    positive=True,
):
    frame = frame_factory._frame(
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
            "binding_eligibility": "V284_SPACY_ECONOMIC_ROLE",
            "parent_numeric_inheritance": False,
            "rule_program_sha256": rule.source_sha256,
        }
    )
    return replace(
        frame,
        rule_id=rule_id,
        rule_version=rule.version,
        verified_by="V284_SPACY_ECONOMIC_ROLE_VERIFIER",
        context_trace=trace,
    )


def _make(document, block, candidates, rule_id, concept, semantic, value, **kwargs):
    return _new_frame(
        document,
        block,
        candidates,
        rule_id=rule_id,
        concept=concept,
        semantic=semantic,
        value=value,
        **kwargs,
    )


def _phrase_bounds(backend, text: str, phrase: str):
    matches = backend.phrase_mentions(text, (phrase,))
    return matches[0][1:] if matches else None


def _between(quantities, kind, start: int, end: int):
    return tuple(item for item in quantities if item.kind is kind and start <= item.char_start < end)


def _segment_economics(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if "adjusted ebitda" not in folded or "a margin of" not in folded or "revenue" not in folded:
        return ()
    ebitda = next((item for item in concepts if item.concept == "ADJUSTED_EBITDA"), None)
    if ebitda is None:
        return ()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT and item.char_start >= ebitda.char_end)
    if not money or not percents:
        return ()
    ebitda_value = min(money, key=lambda item: abs(item.char_start - ebitda.char_start))
    revenue = next((item for item in concepts if item.concept == "REVENUE"), None)
    revenue_value = None if revenue is None else min(money, key=lambda item: abs(item.char_start - revenue.char_start))
    frames = (
        None if revenue_value is None else _make(document, block, candidates, "v284.segment_economics", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, revenue_value),
        _make(document, block, candidates, "v284.segment_economics", "ADJUSTED_EBITDA", SemanticFrame.ABSOLUTE_VALUE, ebitda_value),
        _make(document, block, candidates, "v284.segment_economics", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.ABSOLUTE_VALUE, percents[0]),
    )
    return tuple(frame for frame in frames if frame is not None)


def _economic_driver_frames(document, block, candidates, concepts, quantities, backend):
    tokens = _tokens(backend, block.text)
    output = []
    mentions = _mentions(concepts, {"ACTIVITY_VOLUME", "PRICE_REALIZATION", "ORDERS"})
    for index, mention in enumerate(mentions):
        end = mentions[index + 1].char_start if index + 1 < len(mentions) else len(block.text)
        money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY and mention.char_start - 40 <= item.char_start < end)
        percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT and mention.char_start - 20 <= item.char_start < end)
        frame = None
        if mention.concept == "ORDERS" and money:
            frame = _make(document, block, candidates, "v284.economic_driver_roles", "ORDERS", SemanticFrame.ABSOLUTE_VALUE, min(money, key=lambda item: abs(item.char_start - mention.char_start)))
        elif mention.concept == "ACTIVITY_VOLUME" and "patient days" in mention.alias.casefold() and percents:
            frame = _make(document, block, candidates, "v284.economic_driver_roles", "ACTIVITY_VOLUME", SemanticFrame.CHANGE_BY, percents[0], positive=_polarity(tokens, mention.char_start, percents[0].char_end))
        elif mention.concept == "ACTIVITY_VOLUME" and money and percents:
            frame = _make(document, block, candidates, "v284.economic_driver_roles", "ACTIVITY_VOLUME", SemanticFrame.CHANGE_TO, money[0], change=percents[0], positive=_polarity(tokens, mention.char_start, money[0].char_end))
        elif mention.concept == "PRICE_REALIZATION" and money and percents:
            price_unit = "USD_PER_ADVISOR" if "advisor" in mention.alias.casefold() else "USD_PER_UNIT"
            realized_price = replace(money[0], kind=QuantityKind.PRICE, unit=price_unit)
            frame = _make(document, block, candidates, "v284.economic_driver_roles", "PRICE_REALIZATION", SemanticFrame.CHANGE_TO, realized_price, change=percents[0], positive=_polarity(tokens, mention.char_start, percents[0].char_end))
        elif mention.concept == "PRICE_REALIZATION" and percents:
            frame = _make(document, block, candidates, "v284.economic_driver_roles", "PRICE_REALIZATION", SemanticFrame.CHANGE_BY, percents[0], positive=_polarity(tokens, mention.char_start, percents[0].char_end))
        if frame is not None:
            output.append(frame)
    return tuple(output)


def _plus_minus_guidance(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if "+/-" not in folded or "guidance" not in folded or "revenue" not in folded:
        return ()
    revenue = next((item for item in concepts if item.concept == "REVENUE"), None)
    if revenue is None:
        return ()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY and item.char_start >= revenue.char_end)
    if len(money) < 2:
        return ()
    center, delta = money[:2]
    low = replace(center, value=center.value - delta.value)
    high = replace(center, value=center.value + delta.value)
    frame = _make(document, block, candidates, "v284.plus_minus_guidance", "REVENUE_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, center, lower=low, upper=high)
    return (frame,) if frame is not None else ()


def _comparison_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    tokens = _tokens(backend, block.text)
    output = []
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    counts = tuple(item for item in quantities if item.kind is QuantityKind.COUNT)
    if "revenue was" in folded and "compared with" in folded and len(money) >= 3:
        specs = (("REVENUE", money[0]), ("PRIOR_YEAR_REVENUE", money[1]), ("PRIOR_YEAR_REVENUE", money[2]))
        output.extend(frame for concept, value in specs if (frame := _make(document, block, candidates, "v284.multi_role_comparison", concept, SemanticFrame.COMPARATIVE, value)) is not None)
    if "operating margin" in folded and " from " in folded and len(percents) >= 2:
        specs = (("OPERATING_MARGIN", percents[0]), ("PRIOR_YEAR_OPERATING_MARGIN", percents[1]))
        output.extend(frame for concept, value in specs if (frame := _make(document, block, candidates, "v284.multi_role_comparison", concept, SemanticFrame.COMPARATIVE, value)) is not None)
    if "shares outstanding" in folded and "compared" in folded and len(counts) >= 2:
        positive = _polarity(tokens, 0, len(block.text))
        specs = (("SHARES", counts[0]), ("PRIOR_YEAR_SHARES", counts[1]))
        output.extend(frame for concept, value in specs if (frame := _make(document, block, candidates, "v284.multi_role_comparison", concept, SemanticFrame.COMPARATIVE, value, positive=positive)) is not None)
    production_mentions = _mentions(concepts, {"PRODUCTION"})
    if "reported production" in folded and "adjusted production" in folded and len(counts) >= 2:
        production_counts = tuple(item for item in counts if any(abs(item.char_start - mention.char_start) <= 180 for mention in production_mentions))
        for value in production_counts[:2]:
            frame = _make(document, block, candidates, "v284.multi_role_comparison", "PRODUCTION", SemanticFrame.ABSOLUTE_VALUE, value)
            if frame is not None:
                output.append(frame)
    if "production increased to" in folded and "cubic feet" in folded and counts:
        frame = _make(document, block, candidates, "v284.multi_role_comparison", "PRODUCTION", SemanticFrame.CHANGE_TO, counts[0])
        if frame is not None:
            output.append(frame)
    return tuple(output)


def _balance_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    tokens = _tokens(backend, block.text)
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    if "reduced total debt by" in folded and money:
        frame = _make(document, block, candidates, "v284.balance_and_unit_ownership", "DEBT", SemanticFrame.CHANGE_BY, money[0], positive=False)
        return (frame,) if frame is not None else ()
    if "borrowings outstanding" in folded and money:
        phrase = _phrase_bounds(backend, block.text, "borrowings outstanding")
        if phrase is not None:
            value = min(money, key=lambda item: abs(item.char_start - phrase[0]))
            frame = _make(document, block, candidates, "v284.balance_and_unit_ownership", "DEBT", SemanticFrame.ABSOLUTE_VALUE, value)
            return (frame,) if frame is not None else ()
    return ()


def _revenue_role_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if any(phrase in folded for phrase in ("revenue per advisor", "revenue per patient day", "solutions sales")):
        return ()
    tokens = _tokens(backend, block.text)
    mentions = _mentions(concepts, {"REVENUE"})
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    if not mentions or not money or not percents:
        return ()
    mention = mentions[0]
    leading = next((item for item in percents if item.char_start >= mention.char_end and item.char_start < money[0].char_start), None)
    if leading is None or not _has(tokens, leading.char_end, money[0].char_start, {"to"}):
        return ()
    output = []
    main = _make(document, block, candidates, "v284.results_highlights", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=leading, positive=_polarity(tokens, mention.char_start, leading.char_end))
    if main is not None:
        output.append(main)
    contribution = _phrase_bounds(backend, block.text, "sales contribution")
    if contribution is not None:
        component_values = tuple(item for item in money[1:] if abs(item.char_start - contribution[0]) <= 100)
        if component_values:
            made = _make(document, block, candidates, "v284.results_highlights", "REVENUE", SemanticFrame.CHANGE_BY, component_values[0], positive=True)
            if made is not None:
                output.append(made)
    return tuple(output)


def _metric_role_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    tokens = _tokens(backend, block.text)
    output = []
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    basis = tuple(item for item in quantities if item.kind is QuantityKind.BASIS_POINTS)
    if "adjusted ebitda margin" in folded and "respectively" in folded and len(percents) >= 2:
        for value in percents[:2]:
            frame = _make(document, block, candidates, "v284.multi_role_comparison", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.ABSOLUTE_VALUE, value)
            if frame is not None:
                output.append(frame)
    if "reported net revenues" in folded and "organic" in folded and len(percents) >= 2:
        for value in percents[:2]:
            frame = _make(document, block, candidates, "v284.results_highlights", "REVENUE", SemanticFrame.CHANGE_BY, value, positive=_polarity(tokens, 0, value.char_end))
            if frame is not None:
                output.append(frame)
    if "reported and adjusted gross margin" in folded and "respectively" in folded and len(basis) >= 2:
        for value in basis[:2]:
            frame = _make(document, block, candidates, "v284.results_highlights", "GROSS_MARGIN", SemanticFrame.CHANGE_BY, value, positive=True)
            if frame is not None:
                output.append(frame)
    if "segment earnings margin" in folded and percents and basis:
        frame = _make(document, block, candidates, "v284.balance_and_unit_ownership", "OPERATING_MARGIN", SemanticFrame.CHANGE_TO, percents[0], change=basis[0], positive=_polarity(tokens, 0, basis[0].char_end))
        if frame is not None:
            output.append(frame)
    return tuple(output)


def _results_bullet_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if "total revenue was" not in folded or "adjusted ebitda" not in folded or "capital expenditures" not in folded or "compared to" not in folded:
        return ()
    output = []
    concept_start = {
        name: min((item.char_start for item in concepts if item.concept == name), default=None)
        for name in ("ADJUSTED_EBITDA", "CAPEX")
    }
    revenue_start = _phrase_bounds(backend, block.text, "total revenue")
    net_loss = _phrase_bounds(backend, block.text, "net loss")
    net_cash = _phrase_bounds(backend, block.text, "net cash provided")
    sections = (
        (None if revenue_start is None else revenue_start[0], None if net_loss is None else net_loss[0], QuantityKind.MONEY, ("REVENUE", "PRIOR_YEAR_REVENUE")),
        (concept_start["ADJUSTED_EBITDA"], None if net_cash is None else net_cash[0], QuantityKind.MONEY, ("ADJUSTED_EBITDA", "PRIOR_YEAR_ADJUSTED_EBITDA")),
        (concept_start["ADJUSTED_EBITDA"], None if net_cash is None else net_cash[0], QuantityKind.PERCENT, ("ADJUSTED_EBITDA_MARGIN", "PRIOR_YEAR_ADJUSTED_EBITDA_MARGIN")),
        (concept_start["CAPEX"], len(block.text), QuantityKind.MONEY, ("CAPEX", "PRIOR_YEAR_CAPEX")),
    )
    for start, end, kind, names in sections:
        if start is None or end is None:
            continue
        values = _between(quantities, kind, start, end)
        for concept, value in zip(names, values[:2]):
            frame = _make(document, block, candidates, "v284.results_highlights", concept, SemanticFrame.COMPARATIVE, value)
            if frame is not None:
                output.append(frame)
    return tuple(output)


def _simple_highlight_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    tokens = _tokens(backend, block.text)
    output = []
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    revenues = _mentions(concepts, {"REVENUE"})
    revenue = revenues[0] if revenues else None
    gross = _mentions(concepts, {"GROSS_MARGIN"})
    if revenue is not None and "revenue was" in folded and money and percents and "year-over-year" in folded:
        frame = _make(document, block, candidates, "v284.results_highlights", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=percents[0], positive=_polarity(tokens, revenue.char_start, percents[0].char_end))
        if frame is not None:
            output.append(frame)
    for index, mention in enumerate(revenues[1:], start=1):
        end = revenues[index + 1].char_start if index + 1 < len(revenues) else len(block.text)
        value = next(
            (item for item in percents if mention.char_end <= item.char_start < end),
            None,
        )
        if value is not None and _has(tokens, mention.char_start, value.char_end, {"grow", "grew", "increase"}):
            frame = _make(document, block, candidates, "v284.results_highlights", "REVENUE", SemanticFrame.CHANGE_BY, value, positive=True)
            if frame is not None:
                output.append(frame)
    if gross:
        for mention in gross:
            value = next((item for item in percents if item.char_start >= mention.char_end), None)
            if value is not None:
                frame = _make(document, block, candidates, "v284.results_highlights", "GROSS_MARGIN", SemanticFrame.ABSOLUTE_VALUE, value)
                if frame is not None:
                    output.append(frame)
    return tuple(output)


def recover_v284_frames(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...], allowed_spans: set[tuple[int, int]]):
    backend = semantic_backend_v284()
    blocks = {(item.block.char_start, item.block.char_end): item.block for item in candidates}
    output = []
    binders = (
        _segment_economics,
        _economic_driver_frames,
        _plus_minus_guidance,
        _comparison_frames,
        _balance_frames,
        _revenue_role_frames,
        _metric_role_frames,
        _results_bullet_frames,
        _simple_highlight_frames,
    )
    for span, block in blocks.items():
        if span not in allowed_spans:
            continue
        concepts = semantic_concepts_v284(block.text, backend)
        quantities = semantic_quantities_v284(block.text, backend)
        for binder in binders:
            output.extend(binder(document, block, candidates, concepts, quantities, backend))
    unique = {}
    for frame in output:
        signature = (
            frame.concept,
            frame.frame,
            round(frame.value, 6),
            None if frame.change is None else round(frame.change, 6),
            frame.lower_value,
            frame.upper_value,
            frame.polarity.positive,
            frame.source.sha256,
            frame.source_span.char_start,
        )
        unique[signature] = frame
    return tuple(unique.values())


def resolve_frame_conflicts_v284(existing, recovered):
    # Freeze the inherited output first. V284 replacements are adjudicated below;
    # feeding them into an older resolver can silently discard a newer economic role.
    first = prior_semantics.resolve_frame_conflicts_v283(existing, ())

    def values(frame):
        return tuple(value for value in (frame.value, frame.change, frame.lower_value, frame.upper_value) if value is not None)

    def overlaps(frame, item):
        return item.source.sha256 == frame.source.sha256 and item.source_span.char_start <= frame.source_span.char_start and frame.source_span.char_end <= item.source_span.char_end

    def close(left, right):
        return any(isclose(a, b, rel_tol=1e-10, abs_tol=1e-6) for a in values(left) for b in values(right))

    def superseded(frame):
        literal = frame.source_span.literal.casefold()
        replacements = tuple(item for item in recovered if overlaps(frame, item))
        same = any(_base(item.concept) == _base(frame.concept) and close(item, frame) for item in replacements)
        specialized_bases = {
            _base(item.concept)
            for item in replacements
            if item.rule_id in {
                "v284.multi_role_comparison",
                "v284.plus_minus_guidance",
                "v284.results_highlights",
                "v284.balance_and_unit_ownership",
            }
        }
        specialized = _base(frame.concept) in specialized_bases
        driver_retyping = (
            _base(frame.concept) == "REVENUE"
            and any(phrase in literal for phrase in ("revenue per advisor", "revenue per patient day", "solutions sales"))
            and any(_base(item.concept) in {"PRICE_REALIZATION", "ACTIVITY_VOLUME"} for item in replacements)
        )
        cash_flow = _base(frame.concept) == "CASH" and any(
            phrase in literal
            for phrase in ("cash from operations", "cash flow from", "cash provided by operating activities")
        )
        ebitda_activity = _base(frame.concept) == "ACTIVITY_VOLUME" and "adjusted ebitda margin" in literal
        segment_margin = _base(frame.concept) == "GROSS_MARGIN" and "segment earnings margin" in literal and any(_base(item.concept) == "OPERATING_MARGIN" for item in replacements)
        return same or specialized or driver_retyping or cash_flow or ebitda_activity or segment_margin

    merged = (*(frame for frame in first if not superseded(frame)), *recovered)
    unique = {}
    for frame in merged:
        signature = (
            frame.concept,
            frame.frame,
            round(frame.value, 4),
            None if frame.change is None else round(frame.change, 4),
            None if frame.lower_value is None else round(frame.lower_value, 4),
            None if frame.upper_value is None else round(frame.upper_value, 4),
            frame.polarity.positive,
            frame.source.sha256,
            frame.source_span.char_start,
        )
        current = unique.get(signature)
        if current is None or frame.rule_id.startswith("v284."):
            unique[signature] = frame
    return tuple(unique.values())
