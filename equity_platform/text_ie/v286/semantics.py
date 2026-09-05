from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..document import document_text_blocks
from ..dsl import compile_text_rule_file
from ..model import ConceptMention, QuantityKind, QuantityMention, SemanticFrame, TextBlock
from ..ontology import definition_for
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v280 import semantics as frame_factory
from ..v283 import semantics as upper_semantics
from ..v285 import semantics as prior_semantics


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v286_strict_adjudication.arc"
V286_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V286_RULES}


def _base(concept: str) -> str:
    return prior_semantics._base(concept)


@lru_cache(maxsize=1)
def semantic_backend_v286():
    return prior_semantics.semantic_backend_v285()


def semantic_quantities_v286(text: str, backend=None):
    selected = backend or semantic_backend_v286()
    output = list(prior_semantics.semantic_quantities_v285(text, selected))
    seen_spans = {(item.char_start, item.char_end) for item in output}
    tokens = tuple(token for token in selected.parse(text) if not token.is_space)
    activity_units = {"test", "tests", "unit", "units", "shipment", "shipments", "ton", "tons"}
    scales = {"thousand": 1_000.0, "million": 1_000_000.0, "billion": 1_000_000_000.0}
    for index, token in enumerate(tokens[:-1]):
        if not token.like_num:
            continue
        scale = scales.get(tokens[index + 1].lower_)
        unit_index = index + 2 if scale is not None else index + 1
        if unit_index >= len(tokens) or tokens[unit_index].lower_ not in activity_units:
            continue
        try:
            value = float(token.text.replace(",", "")) * (scale or 1.0)
        except ValueError:
            continue
        end_token = tokens[unit_index]
        span = (int(token.idx), int(end_token.idx + len(end_token.text)))
        if any(start <= span[0] and span[1] <= end for start, end in seen_spans):
            continue
        output.append(QuantityMention(
            kind=QuantityKind.COUNT,
            value=value,
            unit="COUNT",
            raw=text[span[0]:span[1]],
            char_start=span[0],
            char_end=span[1],
        ))
        seen_spans.add(span)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end, item.kind.value)))


def semantic_concepts_v286(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v286()
    output = list(prior_semantics.semantic_concepts_v285(text, selected))
    folded = text.casefold()

    def add(phrase: str, concept: str) -> None:
        output.extend(ConceptMention(concept, literal, start, end) for literal, start, end in selected.phrase_mentions(text, (phrase,)))

    add("ebitda", "ADJUSTED_EBITDA")
    add("ebitda margin", "ADJUSTED_EBITDA_MARGIN")
    add("ebitda margins", "ADJUSTED_EBITDA_MARGIN")
    add("test volume", "ACTIVITY_VOLUME")
    add("product sales volumes", "ACTIVITY_VOLUME")
    add("weighted-average diluted shares outstanding", "SHARES")
    if "adjusted ebitda" in folded and any(item.kind is QuantityKind.PERCENT for item in semantic_quantities_v286(text, selected)):
        add("adjusted ebitda", "ADJUSTED_EBITDA_MARGIN")
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept)))


def augment_candidates_v286(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...]) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v286()
    output = list(candidates)
    seen = {(item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end) for item in output}
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v286(block.text, backend)
        if not quantities:
            continue
        for mention in semantic_concepts_v286(block.text, backend):
            signature = (block.char_start, mention.concept, mention.char_start, mention.char_end)
            if signature in seen:
                continue
            allowed = set(definition_for(mention.concept).quantity_kinds) | {QuantityKind.MONEY, QuantityKind.PERCENT, QuantityKind.BASIS_POINTS, QuantityKind.COUNT}
            compatible = tuple(item for item in quantities if item.kind in allowed and abs(item.char_start - mention.char_start) <= 800)
            if not compatible:
                continue
            candidate_id = sha256(f"{document.source.sha256}:{block.char_start}:{mention.concept}:{mention.char_start}:{mention.char_end}:v286".encode()).hexdigest()[:20]
            output.append(RecallCandidate(
                candidate_id=candidate_id,
                block=block,
                metric=MetricAnchor(mention.concept, mention.alias, mention.char_start, mention.char_end),
                quantities=compatible,
                origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                rule_ids=("v286.spacy_strict_adjudication_candidate",),
            ))
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
    trace.update({"binding_eligibility": "V286_SPACY_STRICT_ADJUDICATION", "parent_numeric_inheritance": False, "rule_program_sha256": rule.source_sha256})
    return replace(frame, rule_id=rule_id, rule_version=rule.version, verified_by="V286_SPACY_STRICT_ADJUDICATION_VERIFIER", context_trace=trace)


def _phrase(backend, text: str, phrase: str):
    matches = backend.phrase_mentions(text, (phrase,))
    return matches[0][1:] if matches else None


def _strict_block_frames(document, block: TextBlock, candidates, concepts, quantities, backend, upper_future: bool):
    text = block.text
    folded = text.casefold()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    basis = tuple(item for item in quantities if item.kind is QuantityKind.BASIS_POINTS)
    counts = tuple(item for item in quantities if item.kind is QuantityKind.COUNT)
    output = []

    def emit(rule_id, concept, semantic, value, **kwargs):
        frame = _new_frame(document, block, candidates, rule_id=rule_id, concept=concept, semantic=semantic, value=value, **kwargs)
        if frame is not None:
            output.append(frame)

    def after(items, phrase: str):
        bounds = _phrase(backend, text, phrase)
        return tuple(item for item in items if bounds is not None and item.char_start >= bounds[1])

    # Fail closed on sentences whose money belongs to losses or expense detail.
    if "consulting expenses" in folded and "transaction costs" in folded:
        return ()
    if "excluding revenue" in folded and "net loss was" in folded and "adjusted ebitda" not in folded:
        return ()
    if "expect" in folded and "net income" in folded and "of total revenue" in folded:
        return ()
    if "ebitda ttm increase" in folded and "ttm revenue ttm increase" in folded:
        return ()

    # Multi-clause current growth plus two distinct long-run revenue anchors.
    if "long-term annual revenue outlook" in folded and "annual revenue" in folded and len(money) >= 3:
        if "second quarter revenue of" not in folded:
            if percents:
                emit("v286.revenue_ownership", "REVENUE", SemanticFrame.CHANGE_BY, percents[0])
            outlook_values = after(money, "long-term annual revenue outlook")
            if outlook_values:
                emit("v286.forward_ownership", "REVENUE_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, outlook_values[0])
            secondary_value = money[-1]
            if not outlook_values or secondary_value.char_start != outlook_values[0].char_start:
                emit("v286.forward_ownership", "REVENUE_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, secondary_value)
            return tuple(output)

    # Explicit financing actions.
    if money and "prepay" in folded and "term loan" in folded:
        emit("v286.financing_ownership", "DEBT", SemanticFrame.CHANGE_BY, money[0], positive=False)
        return tuple(output)
    if money and "incremental borrowings" in folded and "additional" in folded:
        emit("v286.financing_ownership", "DEBT", SemanticFrame.CHANGE_BY, money[0])
        return tuple(output)

    # Current backlog and local cash balance clauses.
    backlog_values = after(money, "backlog")
    if backlog_values and any(cue in folded for cue in ("effective backlog", "record backlog", "backlog of", "backlog is")):
        emit("v286.balance_activity_ownership", "BACKLOG", SemanticFrame.ABSOLUTE_VALUE, backlog_values[0])
    cash_values = after(money, "total cash") or after(money, "cash balance")
    if len(cash_values) >= 2 and "compared" in folded:
        emit("v286.balance_activity_ownership", "CASH", SemanticFrame.COMPARATIVE, cash_values[0])
        emit("v286.balance_activity_ownership", "PRIOR_YEAR_CASH", SemanticFrame.COMPARATIVE, cash_values[1])
    elif cash_values:
        emit("v286.balance_activity_ownership", "CASH", SemanticFrame.ABSOLUTE_VALUE, cash_values[0])
    elif money and ("had $" in folded and " of cash" in folded):
        emit("v286.balance_activity_ownership", "CASH", SemanticFrame.ABSOLUTE_VALUE, money[0])

    # Projected revenue and growth ranges are owned by their explicit labels.
    projected_revenue = after(money, "projected fiscal 2027 revenue") or after(money, "projected revenue")
    if len(projected_revenue) >= 2:
        low, high = projected_revenue[:2]
        emit("v286.forward_ownership", "REVENUE_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, replace(low, value=(low.value + high.value) / 2), lower=low, upper=high)
        if len(percents) >= 2:
            low_p, high_p = percents[-2:]
            emit("v286.forward_ownership", "REVENUE_CHANGE_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, replace(low_p, value=(low_p.value + high_p.value) / 2), lower=low_p, upper=high_p)

    # Revenue guidance ranges and at-least growth guidance.
    future = upper_future or any(cue in folded for cue in ("outlook", "guidance", "projected", "expectation", "expected", "targeting", "raises full-year"))
    revenue_range = after(money, "total revenue range") or after(money, "total revenue to be") or after(money, "total revenue expectation") or after(money, "revenue within a range")
    if future and len(revenue_range) >= 2:
        low, high = revenue_range[:2]
        emit("v286.forward_ownership", "REVENUE_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, replace(low, value=(low.value + high.value) / 2), lower=low, upper=high)
    if future and "subscription revenue growth" in folded and percents:
        boundary = folded.find("original guidance")
        eligible = tuple(item for item in percents if boundary < 0 or item.char_start < boundary)
        if eligible:
            emit("v286.forward_ownership", "REVENUE_CHANGE_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, eligible[-1])
    if (future or "total sales growth:" in folded) and "total sales" in folded and len(percents) >= 2:
        low, high = percents[:2]
        emit("v286.forward_ownership", "REVENUE_CHANGE_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, replace(low, value=(low.value + high.value) / 2), lower=low, upper=high)
    generic_revenue_range = after(money, "revenue within a range")
    if len(generic_revenue_range) >= 2:
        low, high = generic_revenue_range[:2]
        emit("v286.forward_ownership", "REVENUE_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, replace(low, value=(low.value + high.value) / 2), lower=low, upper=high)

    # Long-run revenue point guidance outside the multi-clause form.
    if money and "long-term ambition" in folded and "annual net sales" in folded:
        emit("v286.forward_ownership", "REVENUE_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, money[0])

    # Share-count outlook is a count, never the adjacent EPS dollars.
    if counts and "shares outstanding" in folded and (future or "outlook" in folded):
        emit("v286.forward_ownership", "SHARES_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, counts[-1])

    # Revenue composition.
    if percents and "revenue constituted" in folded and "of total revenue" in folded:
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.COMPOSITION, percents[0])

    # Some IR HTML joins title lines and the opening quote into one prose block.
    # Bind each number to its local label and stop before generic revenue logic.
    if "second quarter revenue of" in folded and "adjusted ebitda margin" in folded:
        actual_revenue = after(money, "second quarter revenue of")
        if actual_revenue:
            emit("v286.revenue_ownership", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, actual_revenue[0])
        margin_bounds = _phrase(backend, text, "adjusted ebitda margin")
        local_margin = tuple(item for item in percents if margin_bounds is not None and item.char_end <= margin_bounds[0])
        if local_margin:
            emit("v286.profitability_ownership", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.ABSOLUTE_VALUE, local_margin[-1])
        return tuple(output)
    if "announces record revenue of" in folded and "raises full-year" in folded:
        actual_revenue = after(money, "announces record revenue of")
        local_margin = after(percents, "adjusted ebitda of")
        if actual_revenue:
            emit("v286.revenue_ownership", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, actual_revenue[0])
        if local_margin:
            emit("v286.profitability_ownership", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.ABSOLUTE_VALUE, local_margin[0])
        return tuple(output)

    # Revenue comparisons and changes.
    if "revenue was" in folded and "compared" in folded and len(money) >= 2 and not percents:
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.COMPARATIVE, money[0])
        emit("v286.revenue_ownership", "PRIOR_YEAR_REVENUE", SemanticFrame.COMPARATIVE, money[1])
    elif "revenue" in folded and "compared" in folded and len(money) >= 2 and percents and " to $" in folded:
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.CHANGE_TO, money[-1], change=percents[0], positive="decreased" not in folded)
    elif "revenue" in folded and "compared" in folded and len(money) >= 2 and percents and "to a record" in folded:
        current_values = after(money, "to a record")
        if current_values:
            emit("v286.revenue_ownership", "REVENUE", SemanticFrame.CHANGE_TO, current_values[0], change=percents[0], positive="decreased" not in folded)
    elif "revenue" in folded and not future and len(money) >= 2 and percents and " to $" in folded:
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.CHANGE_TO, money[-1], change=percents[0], positive="decrease" not in folded)
    elif "record revenue of" in folded and money and len(percents) >= 2:
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=percents[0])
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.CHANGE_BY, percents[1])
    elif "revenue" in folded and len(money) == 1 and percents and any(cue in folded for cue in ("representing a", "up ", "increased ")):
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=percents[0], positive="decrease" not in folded)
    elif "revenue" in folded and not future and len(money) == 1 and any(cue in folded for cue in ("revenue was", "revenue of", "revenue reached")):
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, money[0])
    explicit_current = "revenue for the current quarter increased" in folded or ("organic sales up" in folded and "to date" in folded)
    if percents and ("revenue" in folded or "sales" in folded) and (not future or explicit_current) and not money and any(cue in folded for cue in ("revenue for the current quarter increased", "organic sales up", "revenue grew")):
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.CHANGE_BY, percents[0])

    # Activity-volume levels and changes.
    if counts and "volume" in folded and percents and " to " in folded:
        emit("v286.balance_activity_ownership", "ACTIVITY_VOLUME", SemanticFrame.CHANGE_TO, counts[-1], change=percents[0], positive="decreased" not in folded)
    elif counts and "volumes were" in folded:
        emit("v286.balance_activity_ownership", "ACTIVITY_VOLUME", SemanticFrame.ABSOLUTE_VALUE, counts[0])

    # Profitability roles.
    ebitda_values = after(money, "adjusted ebitda") or after(money, "ebitda of")
    if ebitda_values and "adjusted ebitda was a loss" in folded:
        emit("v286.profitability_ownership", "ADJUSTED_EBITDA", SemanticFrame.ABSOLUTE_VALUE, ebitda_values[0], positive=False)
    elif len(ebitda_values) >= 2 and "adjusted ebitda was" in folded and "compared" in folded and percents:
        emit("v286.profitability_ownership", "ADJUSTED_EBITDA", SemanticFrame.CHANGE_TO, ebitda_values[0], change=percents[-1], positive="decrease" not in folded)
    elif len(ebitda_values) >= 2 and "adjusted ebitda" in folded and "compared" in folded:
        emit("v286.profitability_ownership", "ADJUSTED_EBITDA", SemanticFrame.COMPARATIVE, ebitda_values[0])
        emit("v286.profitability_ownership", "PRIOR_YEAR_ADJUSTED_EBITDA", SemanticFrame.COMPARATIVE, ebitda_values[1])
    elif ebitda_values and "adjusted ebitda was" in folded:
        emit("v286.profitability_ownership", "ADJUSTED_EBITDA", SemanticFrame.ABSOLUTE_VALUE, ebitda_values[0])

    operating_values = after(money, "operating income of")
    plain_ebitda = after(money, "ebitda of")
    if operating_values and plain_ebitda and percents and "operating income of" in folded:
        emit("v286.profitability_ownership", "OPERATING_INCOME", SemanticFrame.ABSOLUTE_VALUE, operating_values[0])
        emit("v286.profitability_ownership", "ADJUSTED_EBITDA", SemanticFrame.CHANGE_TO, plain_ebitda[0], change=percents[-1])

    if percents and "adjusted ebitda of" in folded and not money:
        emit("v286.profitability_ownership", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.ABSOLUTE_VALUE, percents[0])
    if basis and "ebitda margin" in folded and any(cue in folded for cue in ("expanded", "increase", "improved")):
        emit("v286.profitability_ownership", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.CHANGE_BY, basis[0])
    elif percents and "adjusted ebitda margin" in folded:
        emit("v286.profitability_ownership", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.ABSOLUTE_VALUE, percents[-1])

    if "gross margin was" in folded and "compared" in folded and len(percents) >= 2:
        emit("v286.profitability_ownership", "GROSS_MARGIN", SemanticFrame.COMPARATIVE, percents[0])
        emit("v286.profitability_ownership", "PRIOR_YEAR_GROSS_MARGIN", SemanticFrame.COMPARATIVE, percents[1])
    elif percents and "gross margin" in folded:
        value = percents[-1] if "representing" in folded else percents[0]
        if future and "approximately" in folded:
            emit("v286.forward_ownership", "GROSS_MARGIN_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, value)
        elif "range" not in folded:
            emit("v286.profitability_ownership", "GROSS_MARGIN", SemanticFrame.ABSOLUTE_VALUE, value)
    if percents and "operating margin" in folded and "gross margin" not in folded:
        emit("v286.profitability_ownership", "OPERATING_MARGIN", SemanticFrame.ABSOLUTE_VALUE, percents[0])

    # Strict absolute levels used across sectors.
    if money and "total revenue was" in folded and not any(item.concept == "REVENUE" for item in output):
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, money[0])
    if money and "subscription revenue was" in folded:
        emit("v286.revenue_ownership", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, money[0])

    # Exact semantic deduplication inside the adjudicated block.
    unique = {}
    for frame in output:
        signature = (frame.concept, frame.frame, frame.value, frame.change, frame.lower_value, frame.upper_value, frame.polarity.positive)
        unique[signature] = frame
    return tuple(unique.values())


def recover_v286_frames(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...], allowed_spans: set[tuple[int, int]]):
    backend = semantic_backend_v286()
    all_blocks = document_text_blocks(document)
    blocks = {(item.block.char_start, item.block.char_end): item.block for item in candidates}
    output = []
    for span, block in blocks.items():
        if span not in allowed_spans:
            continue
        concepts = semantic_concepts_v286(block.text, backend)
        quantities = semantic_quantities_v286(block.text, backend)
        upper_future = upper_semantics._upper_future_context(block, all_blocks, backend)
        output.extend(_strict_block_frames(document, block, candidates, concepts, quantities, backend, upper_future))
    return tuple(output)


def resolve_frame_conflicts_v286(existing, recovered):
    # Strict adjudication intentionally emits only V286-verified frames. This is
    # the precision boundary: inherited frames remain available as diagnostics
    # in the parent result but cannot auto-emit without a V286 local decision.
    unique = {}
    for frame in recovered:
        signature = (
            frame.concept, frame.frame, round(frame.value, 4),
            None if frame.change is None else round(frame.change, 4),
            None if frame.lower_value is None else round(frame.lower_value, 4),
            None if frame.upper_value is None else round(frame.upper_value, 4),
            frame.polarity.positive, frame.source.sha256, frame.source_span.char_start,
        )
        unique[signature] = frame
    return tuple(unique.values())
