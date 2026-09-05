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
from ..v287 import semantics as prior_semantics


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v288_local_role_binder.arc"
V288_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V288_RULES}


def _base(concept: str) -> str:
    return prior_semantics._base(concept)


@lru_cache(maxsize=1)
def semantic_backend_v288():
    return prior_semantics.semantic_backend_v287()


def _unscaled_share_counts(text: str, backend) -> tuple[QuantityMention, ...]:
    if not backend.phrase_mentions(text, ("shares outstanding",)):
        return ()
    output = []
    for token in backend.parse(text):
        if not token.like_num:
            continue
        try:
            value = float(token.text.replace(",", ""))
        except ValueError:
            continue
        if value < 10_000:
            continue
        start = int(token.idx)
        end = int(token.idx + len(token.text))
        output.append(QuantityMention(QuantityKind.COUNT, value, "COUNT", text[start:end], start, end))
    return tuple(output)


def semantic_quantities_v288(text: str, backend=None):
    selected = backend or semantic_backend_v288()
    output = list(prior_semantics.semantic_quantities_v287(text, selected))
    seen = {(item.char_start, item.char_end, item.kind) for item in output}
    for item in _unscaled_share_counts(text, selected):
        signature = (item.char_start, item.char_end, item.kind)
        if signature not in seen:
            output.append(item)
            seen.add(signature)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end, item.kind.value)))


def semantic_concepts_v288(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v288()
    output = list(prior_semantics.semantic_concepts_v287(text, selected))
    aliases = {
        "net interest income": "REVENUE",
        "promissory note": "DEBT",
    }
    for phrase, concept in aliases.items():
        output.extend(
            ConceptMention(concept, literal, start, end)
            for literal, start, end in selected.phrase_mentions(text, (phrase,))
        )
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept)))


def augment_candidates_v288(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...]) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v288()
    output = list(candidates)
    seen = {
        (item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end)
        for item in output
    }
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v288(block.text, backend)
        if not quantities:
            continue
        for mention in semantic_concepts_v288(block.text, backend):
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
                item for item in quantities
                if item.kind in allowed and abs(item.char_start - mention.char_start) <= 800
            )
            if not compatible:
                continue
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:{mention.char_start}:{mention.char_end}:v288".encode()
            ).hexdigest()[:20]
            output.append(RecallCandidate(
                candidate_id=candidate_id,
                block=block,
                metric=MetricAnchor(mention.concept, mention.alias, mention.char_start, mention.char_end),
                quantities=compatible,
                origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                rule_ids=("v288.spacy_local_role_candidate",),
            ))
            seen.add(signature)
    return tuple(output)


def _new_frame(document, block, candidates, *, rule_id, concept, semantic, value, change=None, lower=None, upper=None, positive=True):
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
        "binding_eligibility": "V288_SPACY_LOCAL_ROLE_BINDER",
        "parent_numeric_inheritance": False,
        "rule_program_sha256": rule.source_sha256,
    })
    return replace(
        frame,
        rule_id=rule_id,
        rule_version=rule.version,
        verified_by="V288_SPACY_LOCAL_ROLE_VERIFIER",
        context_trace=trace,
    )


def _phrase(backend, text: str, phrase: str):
    matches = backend.phrase_mentions(text, (phrase,))
    return matches[0][1:] if matches else None


def _local_role_frames(document, block: TextBlock, candidates, quantities, backend, upper_future: bool):
    text = block.text
    folded = text.casefold()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    counts = tuple(item for item in quantities if item.kind is QuantityKind.COUNT)
    output = []

    def emit(rule_id, concept, semantic, value, **kwargs):
        frame = _new_frame(
            document,
            block,
            candidates,
            rule_id=rule_id,
            concept=concept,
            semantic=semantic,
            value=value,
            **kwargs,
        )
        if frame is not None:
            output.append(frame)

    def after(items, phrase: str):
        bounds = _phrase(backend, text, phrase)
        return tuple(item for item in items if bounds is not None and item.char_start >= bounds[1])

    def before(items, phrase: str):
        bounds = _phrase(backend, text, phrase)
        return tuple(item for item in items if bounds is not None and item.char_end <= bounds[0])

    def midpoint(low, high):
        return replace(low, value=(low.value + high.value) / 2)

    future = upper_future or any(
        cue in folded for cue in ("expect", "outlook", "guidance", "full year", "full-year")
    )

    if "increase in net interest income" in folded and money:
        owned = before(money, "increase in net interest income")
        if owned:
            emit("v288.financial_role", "REVENUE", SemanticFrame.CHANGE_BY, owned[-1])
        return tuple(output)

    if "net interest income increased" in folded and len(money) >= 2 and percents:
        emit("v288.level_change_role", "REVENUE", SemanticFrame.CHANGE_TO, money[-1], change=percents[0])
        return tuple(output)

    if "borrowed" in folded and "promissory note" in folded and money:
        emit("v288.financial_role", "DEBT", SemanticFrame.ABSOLUTE_VALUE, money[0])
        return tuple(output)

    if "reports financial results" in folded and "net revenues of" in folded and money:
        values = after(money, "net revenues of")
        if values:
            emit("v288.level_change_role", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, values[0])
        return tuple(output)

    if "revenue for" in folded and " was " in folded and " up " in folded and len(money) >= 2 and percents:
        emit("v288.level_change_role", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=percents[0])
        return tuple(output)

    if "gross margin" in folded and len(percents) >= 2 and any(cue in folded for cue in ("compared with", "compared to", "improving from")):
        emit("v288.level_change_role", "GROSS_MARGIN", SemanticFrame.COMPARATIVE, percents[0])
        emit("v288.level_change_role", "PRIOR_YEAR_GROSS_MARGIN", SemanticFrame.COMPARATIVE, percents[1])
        return tuple(output)

    if "net sales" in folded and "expect" in folded and len(money) >= 2 and percents:
        emit("v288.level_change_role", "REVENUE", SemanticFrame.CHANGE_BY, percents[0])
        low, high = money[:2]
        emit("v288.forward_role", "REVENUE_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, midpoint(low, high), lower=low, upper=high)
        return tuple(output)

    if "expect" in folded and "net sales of" in folded and len(money) >= 2:
        low, high = money[:2]
        emit("v288.forward_role", "REVENUE_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, midpoint(low, high), lower=low, upper=high)
        return tuple(output)

    if "net sales" in folded and not money and percents and any(cue in folded for cue in ("sales up", "sales increased", "sales, increasing")):
        emit("v288.level_change_role", "REVENUE", SemanticFrame.CHANGE_BY, percents[0], positive="decreased" not in folded)
        return tuple(output)

    if "gross margin between" in folded and len(percents) >= 2 and future:
        low, high = percents[:2]
        emit("v288.forward_role", "GROSS_MARGIN_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, midpoint(low, high), lower=low, upper=high)
        return tuple(output)

    if "mid-point of the revenue range" in folded or "midpoint of the revenue range" in folded:
        for value in percents[:2]:
            emit("v288.forward_role", "REVENUE_CHANGE_GUIDANCE", SemanticFrame.CHANGE_BY, value)
        return tuple(output)

    if "gross margin was" in folded and "operating income was" in folded and percents and money:
        operating_values = after(money, "operating income was")
        emit("v288.financial_role", "GROSS_MARGIN", SemanticFrame.ABSOLUTE_VALUE, percents[0])
        if operating_values:
            emit("v288.financial_role", "OPERATING_INCOME", SemanticFrame.ABSOLUTE_VALUE, operating_values[0])
        return tuple(output)

    if "contributing" in folded and " in sales" in folded and "with sales of" in folded and len(money) >= 2:
        emit("v288.level_change_role", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, money[0])
        emit("v288.level_change_role", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, money[-1])
        return tuple(output)


    if any(cue in folded for cue in ("contributing", "contributed")) and " in sales" in folded and money:
        emit("v288.level_change_role", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, money[0])
        return tuple(output)

    if "net sales reached" in folded and money:
        emit("v288.level_change_role", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, money[0])
        return tuple(output)

    if "annual recurring revenue was" in folded and len(money) >= 2 and percents:
        emit("v288.level_change_role", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=percents[0])
        emit("v288.level_change_role", "REVENUE", SemanticFrame.CHANGE_BY, money[1])
        return tuple(output)

    if "basic shares" in folded and "diluted shares" in folded and "compared to" in folded and len(counts) >= 2:
        emit("v288.level_change_role", "SHARES", SemanticFrame.COMPARATIVE, counts[0])
        emit("v288.level_change_role", "PRIOR_YEAR_SHARES", SemanticFrame.COMPARATIVE, counts[1])
        return tuple(output)

    if "shares outstanding" in folded and " was " in folded and counts and not future:
        emit("v288.level_change_role", "SHARES", SemanticFrame.ABSOLUTE_VALUE, counts[-1])
        return tuple(output)

    if "adjusted ebitda is expected" in folded and money:
        emit("v288.forward_role", "ADJUSTED_EBITDA_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, money[0])
        return tuple(output)

    if "revenue outlook" in folded and "adjusted ebitda" in folded and len(money) >= 2:
        revenue_values = after(money, "revenue outlook")
        ebitda_values = after(money, "adjusted ebitda")
        if revenue_values:
            emit("v288.forward_role", "REVENUE_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, revenue_values[0])
        if ebitda_values:
            emit("v288.forward_role", "ADJUSTED_EBITDA_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, ebitda_values[0])
        return tuple(output)

    if "revenue" in folded and "more than doubled" in folded and " to $" in folded and money:
        emit("v288.level_change_role", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, money[-1])
        return tuple(output)

    if "capital expenditure" in folded and "shares outstanding" in folded and future and money and counts:
        emit("v288.forward_role", "CAPEX_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, money[0])
        emit("v288.forward_role", "SHARES_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, counts[-1])
        return tuple(output)

    if "including cash and cash equivalents of" in folded and money:
        cash_values = after(money, "including cash and cash equivalents of")
        if cash_values:
            emit("v288.financial_role", "CASH", SemanticFrame.ABSOLUTE_VALUE, cash_values[0])
        return tuple(output)

    if "net loss of" in folded and "adjusted ebitda of" in folded and len(money) >= 2:
        ebitda_values = after(money, "adjusted ebitda of")
        if ebitda_values:
            emit("v288.financial_role", "ADJUSTED_EBITDA", SemanticFrame.ABSOLUTE_VALUE, ebitda_values[0])
        return tuple(output)

    return ()


def recover_v288_frames(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...], allowed_spans: set[tuple[int, int]]):
    backend = semantic_backend_v288()
    all_blocks = document_text_blocks(document)
    blocks = {(item.block.char_start, item.block.char_end): item.block for item in candidates}
    output = []
    for span, block in blocks.items():
        if span not in allowed_spans:
            continue
        quantities = semantic_quantities_v288(block.text, backend)
        upper_future = upper_semantics._upper_future_context(block, all_blocks, backend)
        output.extend(_local_role_frames(document, block, candidates, quantities, backend, upper_future))
    return tuple(output)


def resolve_frame_conflicts_v288(existing, recovered):
    replacement_spans = {
        (frame.source.sha256, frame.source_span.char_start, frame.source_span.char_end)
        for frame in recovered
    }
    selected = [
        frame for frame in existing
        if (frame.source.sha256, frame.source_span.char_start, frame.source_span.char_end) not in replacement_spans
    ]
    selected.extend(recovered)
    unique = {}
    for frame in selected:
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
        unique[signature] = frame
    return tuple(unique.values())
