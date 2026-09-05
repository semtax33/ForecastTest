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
from ..v286 import semantics as prior_semantics


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v287_role_expansion.arc"
V287_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V287_RULES}


def _base(concept: str) -> str:
    return prior_semantics._base(concept)


@lru_cache(maxsize=1)
def semantic_backend_v287():
    return prior_semantics.semantic_backend_v286()


def _local_operational_counts(text: str, backend) -> tuple[QuantityMention, ...]:
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    phrase_bounds = []
    for phrase in ("health plan membership", "membership", "demand response events"):
        phrase_bounds.extend((start, end) for _, start, end in backend.phrase_mentions(text, (phrase,)))
    output = []
    for token in tokens:
        if not token.like_num:
            continue
        try:
            value = float(token.text.replace(",", ""))
        except ValueError:
            continue
        if 1900 <= value <= 2100:
            continue
        start = int(token.idx)
        end = int(token.idx + len(token.text))
        membership_owner = any(owner_end <= start <= owner_end + 100 for _, owner_end in phrase_bounds)
        event_owner = any(end <= owner_start and owner_start - end <= 80 for owner_start, _ in phrase_bounds)
        if not membership_owner and not event_owner:
            continue
        output.append(QuantityMention(QuantityKind.COUNT, value, "COUNT", text[start:end], start, end))
    return tuple(output)


def semantic_quantities_v287(text: str, backend=None):
    selected = backend or semantic_backend_v287()
    output = list(prior_semantics.semantic_quantities_v286(text, selected))
    seen = {(item.char_start, item.char_end, item.kind) for item in output}
    for item in _local_operational_counts(text, selected):
        signature = (item.char_start, item.char_end, item.kind)
        if signature not in seen:
            output.append(item)
            seen.add(signature)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end, item.kind.value)))


def semantic_concepts_v287(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v287()
    output = list(prior_semantics.semantic_concepts_v286(text, selected))
    aliases = {
        "health plan membership": "ACTIVITY_VOLUME",
        "membership": "ACTIVITY_VOLUME",
        "demand response events": "ACTIVITY_VOLUME",
        "consumer auto originations": "ACTIVITY_VOLUME",
        "auto originations": "ACTIVITY_VOLUME",
        "application volume": "ACTIVITY_VOLUME",
    }
    for phrase, concept in aliases.items():
        output.extend(
            ConceptMention(concept, literal, start, end)
            for literal, start, end in selected.phrase_mentions(text, (phrase,))
        )
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept)))


def augment_candidates_v287(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...]) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v287()
    output = list(candidates)
    seen = {
        (item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end)
        for item in output
    }
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v287(block.text, backend)
        if not quantities:
            continue
        for mention in semantic_concepts_v287(block.text, backend):
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
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:{mention.char_start}:{mention.char_end}:v287".encode()
            ).hexdigest()[:20]
            output.append(RecallCandidate(
                candidate_id=candidate_id,
                block=block,
                metric=MetricAnchor(mention.concept, mention.alias, mention.char_start, mention.char_end),
                quantities=compatible,
                origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                rule_ids=("v287.spacy_role_expansion_candidate",),
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
        "binding_eligibility": "V287_SPACY_ROLE_EXPANSION",
        "parent_numeric_inheritance": False,
        "rule_program_sha256": rule.source_sha256,
    })
    return replace(
        frame,
        rule_id=rule_id,
        rule_version=rule.version,
        verified_by="V287_SPACY_ROLE_EXPANSION_VERIFIER",
        context_trace=trace,
    )


def _phrase(backend, text: str, phrase: str):
    matches = backend.phrase_mentions(text, (phrase,))
    return matches[0][1:] if matches else None


def _expanded_block_frames(document, block: TextBlock, candidates, quantities, backend, upper_future: bool):
    text = block.text
    folded = text.casefold()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    basis = tuple(item for item in quantities if item.kind is QuantityKind.BASIS_POINTS)
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

    def midpoint(low, high):
        return replace(low, value=(low.value + high.value) / 2)

    future = upper_future or any(
        cue in folded for cue in ("expect", "outlook", "guidance", "full year", "full-year")
    )

    if "total debt was" in folded and "net debt was" in folded and "respectively" in folded and len(money) >= 4:
        for concept, value in (
            ("DEBT", money[0]),
            ("DEBT", money[1]),
            ("PRIOR_YEAR_DEBT", money[2]),
            ("PRIOR_YEAR_DEBT", money[3]),
        ):
            emit("v287.comparative_ownership", concept, SemanticFrame.COMPARATIVE, value)
        return tuple(output)

    if "adjusted ebitda of" in folded and "respectively" in folded and len(money) >= 4:
        values = after(money, "adjusted ebitda of")
        if len(values) >= 2:
            emit("v287.comparative_ownership", "ADJUSTED_EBITDA", SemanticFrame.COMPARATIVE, values[0])
            emit("v287.comparative_ownership", "PRIOR_YEAR_ADJUSTED_EBITDA", SemanticFrame.COMPARATIVE, values[1])
        return tuple(output)

    if "health plan membership" in folded and "total revenue was" in folded and "income from operations was" in folded:
        membership = counts[0] if counts else None
        revenue_values = after(money, "total revenue was")
        revenue_changes = after(percents, "total revenue was")
        income_values = after(money, "income from operations was")
        if membership is not None and percents:
            emit("v287.activity_ownership", "ACTIVITY_VOLUME", SemanticFrame.CHANGE_TO, membership, change=percents[0])
        if revenue_values and revenue_changes:
            emit("v287.performance_ownership", "REVENUE", SemanticFrame.CHANGE_TO, revenue_values[0], change=revenue_changes[0])
        if income_values:
            emit("v287.performance_ownership", "OPERATING_INCOME", SemanticFrame.ABSOLUTE_VALUE, income_values[0])
        return tuple(output)

    if "adjusted ebitda" in folded and "adjusted ebitda margin" in folded and "grew" in folded and money and len(percents) >= 2:
        ebitda_values = after(money, "adjusted ebitda")
        margin_values = after(percents, "adjusted ebitda margin")
        growth_values = after(percents, "grew")
        if ebitda_values and growth_values:
            emit("v287.performance_ownership", "ADJUSTED_EBITDA", SemanticFrame.CHANGE_TO, ebitda_values[0], change=growth_values[0])
        if margin_values:
            emit("v287.performance_ownership", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.ABSOLUTE_VALUE, margin_values[0])
        return tuple(output)

    if "revenue is now expected to be in the range" in folded and len(money) >= 3:
        low, high = money[:2]
        emit("v287.guidance_ownership", "REVENUE_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, midpoint(low, high), lower=low, upper=high)
        emit("v287.guidance_ownership", "REVENUE_GUIDANCE", SemanticFrame.CHANGE_BY, money[2])
        return tuple(output)

    if future and "revenue growth" in folded and len(percents) >= 2:
        low, high = percents[:2]
        emit(
            "v287.guidance_ownership",
            "REVENUE_CHANGE_GUIDANCE",
            SemanticFrame.RANGE_GUIDANCE,
            midpoint(low, high),
            lower=low,
            upper=high,
            positive="down" not in folded,
        )
        return tuple(output)

    if future and "gross margin" in folded and basis:
        explicit_basis = next((item for item in basis if "basis" in item.raw.casefold()), None)
        if explicit_basis is not None:
            emit("v287.guidance_ownership", "GROSS_MARGIN_CHANGE_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, explicit_basis, positive="down" not in folded)
        return tuple(output)

    if future and "volume growth" in folded and percents:
        emit("v287.guidance_ownership", "ACTIVITY_VOLUME_CHANGE_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, percents[0], positive="down" not in folded)
        return tuple(output)

    if "revenues were" in folded and money and len(percents) >= 2 and "sequentially" in folded and "year-over-year" in folded:
        emit("v287.performance_ownership", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=percents[0])
        emit("v287.performance_ownership", "REVENUE", SemanticFrame.CHANGE_BY, percents[1])
        return tuple(output)

    if "sales increased by" in folded and "year-over-year" in folded and money and percents:
        emit("v287.performance_ownership", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=percents[0], positive="decreased" not in folded)
        return tuple(output)

    if "operating income" in folded and "yielding" in folded and "operating margin" in folded and money and percents:
        emit("v287.performance_ownership", "OPERATING_INCOME", SemanticFrame.ABSOLUTE_VALUE, money[0])
        emit("v287.performance_ownership", "OPERATING_MARGIN", SemanticFrame.ABSOLUTE_VALUE, percents[0])
        return tuple(output)

    if "adjusted ebitda" in folded and "yielding" in folded and "adjusted ebitda margin" in folded and money and percents:
        emit("v287.performance_ownership", "ADJUSTED_EBITDA", SemanticFrame.ABSOLUTE_VALUE, money[0])
        emit("v287.performance_ownership", "ADJUSTED_EBITDA_MARGIN", SemanticFrame.ABSOLUTE_VALUE, percents[0])
        return tuple(output)

    if "adjusted ebitda in the range of" in folded and len(money) >= 2 and future:
        low, high = money[:2]
        emit("v287.guidance_ownership", "ADJUSTED_EBITDA_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, midpoint(low, high), lower=low, upper=high)
        return tuple(output)

    if "share count" in folded and "shares outstanding" in folded and future and len(counts) >= 2:
        for value in counts[-2:]:
            emit("v287.guidance_ownership", "SHARES_GUIDANCE", SemanticFrame.ABSOLUTE_VALUE, value)
        return tuple(output)

    if "gross margin of" in folded and "compared to" in folded and len(percents) >= 2:
        emit("v287.comparative_ownership", "GROSS_MARGIN", SemanticFrame.COMPARATIVE, percents[0])
        emit("v287.comparative_ownership", "PRIOR_YEAR_GROSS_MARGIN", SemanticFrame.COMPARATIVE, percents[1])
        return tuple(output)

    if "consumer auto originations" in folded and "included" in folded and len(money) >= 4 and percents:
        for value in money[:4]:
            emit("v287.activity_ownership", "ACTIVITY_VOLUME", SemanticFrame.ABSOLUTE_VALUE, value)
        emit("v287.activity_ownership", "ACTIVITY_VOLUME", SemanticFrame.COMPOSITION, percents[0])
        return tuple(output)

    if "net financing revenue of" in folded and "was up" in folded and len(money) >= 2:
        emit("v287.performance_ownership", "REVENUE", SemanticFrame.CHANGE_TO, money[0], change=money[1])
        return tuple(output)

    if "application volume" in folded and "originations" in folded and money and percents:
        emit("v287.activity_ownership", "ACTIVITY_VOLUME", SemanticFrame.CHANGE_TO, money[0], change=percents[0])
        return tuple(output)

    if "demand response events" in folded and counts:
        emit("v287.activity_ownership", "ACTIVITY_VOLUME", SemanticFrame.ABSOLUTE_VALUE, counts[-1])
        return tuple(output)

    if "revenue" in folded and "for the quarter were" in folded and money:
        emit("v287.performance_ownership", "REVENUE", SemanticFrame.ABSOLUTE_VALUE, money[-1])
        return tuple(output)

    if "total revenue in the range of" in folded and len(money) >= 2 and future:
        low, high = money[:2]
        emit("v287.guidance_ownership", "REVENUE_GUIDANCE", SemanticFrame.RANGE_GUIDANCE, midpoint(low, high), lower=low, upper=high)
        return tuple(output)

    return ()


def recover_v287_frames(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...], allowed_spans: set[tuple[int, int]]):
    backend = semantic_backend_v287()
    all_blocks = document_text_blocks(document)
    blocks = {(item.block.char_start, item.block.char_end): item.block for item in candidates}
    output = []
    for span, block in blocks.items():
        if span not in allowed_spans:
            continue
        quantities = semantic_quantities_v287(block.text, backend)
        upper_future = upper_semantics._upper_future_context(block, all_blocks, backend)
        output.extend(_expanded_block_frames(document, block, candidates, quantities, backend, upper_future))
    return tuple(output)


def resolve_frame_conflicts_v287(existing, recovered):
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
