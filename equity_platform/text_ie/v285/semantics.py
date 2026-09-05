from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
from math import isclose

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..document import document_text_blocks
from ..dsl import compile_text_rule_file
from ..model import ConceptMention, QuantityKind, SemanticFrame, TextBlock
from ..ontology import definition_for
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v280 import semantics as frame_factory
from ..v284 import semantics as prior_semantics


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v285_generalized_financial_roles.arc"
V285_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V285_RULES}


def _base(concept: str) -> str:
    return prior_semantics._base(concept)


@lru_cache(maxsize=1)
def semantic_backend_v285():
    return prior_semantics.semantic_backend_v284()


def _tokens(backend, text: str):
    return tuple(token for token in backend.parse(text) if not token.is_space)


def _mentions(concepts, names: set[str]):
    return prior_semantics._mentions(concepts, names)


def _has(tokens, start: int, end: int, cues: set[str]) -> bool:
    return any(
        start <= token.idx < end
        and (token.lemma_.casefold() in cues or token.lower_ in cues)
        for token in tokens
    )


def _polarity(tokens, start: int, end: int, default: bool = True) -> bool:
    return prior_semantics._polarity(tokens, start, end, default)


def semantic_quantities_v285(text: str, backend=None):
    return prior_semantics.semantic_quantities_v284(text, backend or semantic_backend_v285())


def semantic_concepts_v285(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v285()
    output = list(prior_semantics.semantic_concepts_v284(text, selected))
    folded = text.casefold()

    def add_phrase(phrase: str, concept: str) -> None:
        output.extend(
            ConceptMention(concept, literal, start, end)
            for literal, start, end in selected.phrase_mentions(text, (phrase,))
        )

    add_phrase("adjusted segment ebitda", "ADJUSTED_EBITDA")
    if "adjusted segment ebitda" in folded and "margin" in folded:
        add_phrase("adjusted segment ebitda", "ADJUSTED_EBITDA_MARGIN")
    if "prepay" in folded and "term loan balance" in folded:
        add_phrase("term loan balance", "DEBT")
    if "targeting" in folded and "ebitda" in folded:
        add_phrase("ebitda", "ADJUSTED_EBITDA")
    add_phrase("otif performance", "ACTIVITY_VOLUME")
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept)))


def augment_candidates_v285(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...]) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v285()
    output = list(candidates)
    seen = {(item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end) for item in output}
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v285(block.text, backend)
        if not quantities:
            continue
        for mention in semantic_concepts_v285(block.text, backend):
            signature = (block.char_start, mention.concept, mention.char_start, mention.char_end)
            if signature in seen:
                continue
            allowed = set(definition_for(mention.concept).quantity_kinds) | {
                QuantityKind.MONEY,
                QuantityKind.PERCENT,
                QuantityKind.BASIS_POINTS,
                QuantityKind.COUNT,
            }
            compatible = tuple(item for item in quantities if item.kind in allowed and abs(item.char_start - mention.char_start) <= 700)
            if not compatible:
                continue
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:{mention.char_start}:{mention.char_end}:v285".encode()
            ).hexdigest()[:20]
            output.append(
                RecallCandidate(
                    candidate_id=candidate_id,
                    block=block,
                    metric=MetricAnchor(mention.concept, mention.alias, mention.char_start, mention.char_end),
                    quantities=compatible,
                    origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                    rule_ids=("v285.spacy_generalized_financial_role_candidate",),
                )
            )
            seen.add(signature)
    return tuple(output)


def _new_frame(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    *,
    rule_id: str,
    concept: str,
    semantic: SemanticFrame,
    value,
    change=None,
    lower=None,
    upper=None,
    positive: bool = True,
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
    trace.update({
        "binding_eligibility": "V285_SPACY_GENERALIZED_FINANCIAL_ROLE",
        "parent_numeric_inheritance": False,
        "rule_program_sha256": rule.source_sha256,
    })
    return replace(frame, rule_id=rule_id, rule_version=rule.version, verified_by="V285_SPACY_GENERALIZED_FINANCIAL_ROLE_VERIFIER", context_trace=trace)


def _make(document, block, candidates, rule_id, concept, semantic, value, **kwargs):
    return _new_frame(document, block, candidates, rule_id=rule_id, concept=concept, semantic=semantic, value=value, **kwargs)


def _phrase_bounds(backend, text: str, phrase: str):
    matches = backend.phrase_mentions(text, (phrase,))
    return matches[0][1:] if matches else None


def _growth_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    tokens = _tokens(backend, block.text)
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    output = []
    if money and ("revenue growth" in folded or ("product sales" in folded and "annualized revenue growth" in folded)):
        frame = _make(document, block, candidates, "v285.growth_components", "REVENUE", SemanticFrame.CHANGE_BY, money[0], positive=True)
        if frame is not None:
            output.append(frame)
    revenue = next((item for item in concepts if item.concept == "REVENUE"), None)
    if revenue is not None and money and percents and "revenue increased" in folded and "organic growth" in folded:
        main = _make(document, block, candidates, "v285.growth_components", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=percents[0], positive=True)
        if main is not None:
            output.append(main)
        for phrase in ("organic growth", "acquisition growth"):
            bounds = _phrase_bounds(backend, block.text, phrase)
            if bounds is None:
                continue
            value = next((item for item in percents if item.char_start >= bounds[1]), None)
            if value is not None:
                frame = _make(document, block, candidates, "v285.growth_components", "REVENUE", SemanticFrame.CHANGE_BY, value, positive=_polarity(tokens, bounds[0], value.char_end))
                if frame is not None:
                    output.append(frame)
    return tuple(output)


def _financing_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    if not money:
        return ()
    negative = "prepay" in folded and "term loan" in folded
    positive = "incremental borrowings" in folded and "additional" in folded
    if not (negative or positive):
        return ()
    frame = _make(document, block, candidates, "v285.financing_action", "DEBT", SemanticFrame.CHANGE_BY, money[0], positive=not negative)
    return (frame,) if frame is not None else ()


def _segment_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if "adjusted segment ebitda" not in folded or "margin expanded" not in folded:
        return ()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    basis = tuple(item for item in quantities if item.kind is QuantityKind.BASIS_POINTS)
    if not money or len(percents) < 2 or not basis:
        return ()
    frames = (
        _make(document, block, candidates, "v285.segment_performance", "ADJUSTED_EBITDA", SemanticFrame.CHANGE_TO, money[0], change=percents[0]),
        _make(document, block, candidates, "v285.segment_performance", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.CHANGE_TO, percents[-1], change=basis[0]),
    )
    return tuple(frame for frame in frames if frame is not None)


def _comparison_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    tokens = _tokens(backend, block.text)
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    revenue = any(item.concept == "REVENUE" for item in concepts)
    compared = "compared to" in folded or "compared with" in folded or "as compared to" in folded
    if not revenue or not compared:
        return ()
    output = []
    if len(money) >= 3 and len(percents) >= 2:
        for concept, value in (("REVENUE", money[0]), ("PRIOR_YEAR_REVENUE", money[1]), ("PRIOR_YEAR_REVENUE", money[2])):
            frame = _make(document, block, candidates, "v285.comparison_basis", concept, SemanticFrame.COMPARATIVE, value)
            if frame is not None:
                output.append(frame)
    elif len(money) >= 2 and percents and _has(tokens, 0, len(block.text), {"increase", "up", "grow"}):
        frame = _make(document, block, candidates, "v285.comparison_basis", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=percents[0], positive=True)
        if frame is not None:
            output.append(frame)
    return tuple(output)


def _guidance_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    output = []
    if "gross margin" in folded and "expect" in folded and "range" in folded and len(percents) >= 2:
        low, high = percents[:2]
        midpoint = replace(low, value=(low.value + high.value) / 2)
        frame = _make(document, block, candidates, "v285.forward_economics", "GROSS_MARGIN_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, midpoint, lower=low, upper=high)
        if frame is not None:
            output.append(frame)
    if money and "long-term ambition" in folded and "annual net sales" in folded:
        frame = _make(document, block, candidates, "v285.forward_economics", "REVENUE_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, money[0])
        if frame is not None:
            output.append(frame)
    if "targeting" in folded and "revenue" in folded and "ebitda" in folded and len(money) >= 4:
        for concept, low, high in (
            ("REVENUE_GUIDANCE", money[0], money[1]),
            ("ADJUSTED_EBITDA_GUIDANCE", money[2], money[3]),
        ):
            midpoint = replace(low, value=(low.value + high.value) / 2)
            frame = _make(document, block, candidates, "v285.forward_economics", concept, SemanticFrame.RANGE_GUIDANCE, midpoint, lower=low, upper=high)
            if frame is not None:
                output.append(frame)
    return tuple(output)


def _highlight_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    if "highlights" not in folded or "revenue" not in folded:
        return ()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    output = []
    revenue = next((item for item in concepts if item.concept == "REVENUE"), None)
    if revenue is not None:
        value = next((item for item in money if item.char_start >= revenue.char_end), None)
        if value is not None:
            made = _make(document, block, candidates, "v285.highlight_list", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, value)
            if made is not None:
                output.append(made)
    for concept in ("GROSS_MARGIN", "OPERATING_MARGIN"):
        for mention in _mentions(concepts, {concept}):
            value = next((item for item in percents if item.char_start >= mention.char_end), None)
            if value is not None:
                made = _make(document, block, candidates, "v285.highlight_list", concept, SemanticFrame.ABSOLUTE_VALUE, value)
                if made is not None:
                    output.append(made)
    return tuple(output)


def _absolute_metric_frames(document, block, candidates, concepts, quantities, backend):
    folded = block.text.casefold()
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    if not percents:
        return ()
    output = []
    if "otif performance" in folded:
        frame = _make(document, block, candidates, "v285.absolute_operating_metric", "ACTIVITY_VOLUME", SemanticFrame.ABSOLUTE_VALUE, percents[0])
        if frame is not None:
            output.append(frame)
    if "ebitda margin" in folded and "adjusted segment ebitda" not in folded:
        frame = _make(document, block, candidates, "v285.absolute_operating_metric", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.ABSOLUTE_VALUE, percents[0])
        if frame is not None:
            output.append(frame)
    return tuple(output)


def recover_v285_frames(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...], allowed_spans: set[tuple[int, int]]):
    backend = semantic_backend_v285()
    blocks = {(item.block.char_start, item.block.char_end): item.block for item in candidates}
    output = []
    binders = (_growth_frames, _financing_frames, _segment_frames, _comparison_frames, _guidance_frames, _highlight_frames, _absolute_metric_frames)
    for span, block in blocks.items():
        if span not in allowed_spans:
            continue
        concepts = semantic_concepts_v285(block.text, backend)
        quantities = semantic_quantities_v285(block.text, backend)
        for binder in binders:
            output.extend(binder(document, block, candidates, concepts, quantities, backend))
    unique = {}
    for frame in output:
        signature = (frame.concept, frame.frame, round(frame.value, 6), None if frame.change is None else round(frame.change, 6), frame.lower_value, frame.upper_value, frame.polarity.positive, frame.source.sha256, frame.source_span.char_start)
        unique[signature] = frame
    return tuple(unique.values())


def resolve_frame_conflicts_v285(existing, recovered):
    first = prior_semantics.resolve_frame_conflicts_v284(existing, ())

    def values(frame):
        return tuple(value for value in (frame.value, frame.change, frame.lower_value, frame.upper_value) if value is not None)

    def overlaps(frame, item):
        return item.source.sha256 == frame.source.sha256 and item.source_span.char_start <= frame.source_span.char_start and frame.source_span.char_end <= item.source_span.char_end

    def close(left, right):
        return any(isclose(a, b, rel_tol=1e-10, abs_tol=1e-6) for a in values(left) for b in values(right))

    def superseded(frame):
        literal = frame.source_span.literal.casefold()
        replacements = tuple(item for item in recovered if overlaps(frame, item))
        rules = {item.rule_id for item in replacements}
        same = any(_base(item.concept) == _base(frame.concept) and close(item, frame) for item in replacements)
        full_revenue = bool(rules & {"v285.growth_components", "v285.comparison_basis"}) and _base(frame.concept) == "REVENUE"
        forward = "v285.forward_economics" in rules and _base(frame.concept) in {"REVENUE", "GROSS_MARGIN", "ADJUSTED_EBITDA"}
        segment = "v285.segment_performance" in rules and _base(frame.concept) in {"ADJUSTED_EBITDA", "ADJUSTED_EBITDA_MARGIN", "ACTIVITY_VOLUME"}
        financing = "v285.financing_action" in rules and _base(frame.concept) in {"DEBT", "CASH"}
        highlight = "v285.highlight_list" in rules and _base(frame.concept) in {"REVENUE", "GROSS_MARGIN", "OPERATING_MARGIN"}
        absolute = "v285.absolute_operating_metric" in rules and (
            _base(frame.concept) in {"ACTIVITY_VOLUME", "ADJUSTED_EBITDA_MARGIN"}
            or (_base(frame.concept) == "REVENUE" and "ebitda margin" in literal)
        )
        all_cash = _base(frame.concept) == "CASH" and "all-cash transaction" in literal and "per share" in literal
        damaged = _base(frame.concept) in {"REVENUE", "ADJUSTED_EBITDA"} and "ebitda ttm increase" in literal and "ttm revenue ttm increase" in literal
        return same or full_revenue or forward or segment or financing or highlight or absolute or all_cash or damaged

    merged = (*(frame for frame in first if not superseded(frame)), *recovered)
    unique = {}
    for frame in merged:
        signature = (frame.concept, frame.frame, round(frame.value, 4), None if frame.change is None else round(frame.change, 4), None if frame.lower_value is None else round(frame.lower_value, 4), None if frame.upper_value is None else round(frame.upper_value, 4), frame.polarity.positive, frame.source.sha256, frame.source_span.char_start)
        current = unique.get(signature)
        if current is None or frame.rule_id.startswith("v285."):
            unique[signature] = frame
    return tuple(unique.values())
