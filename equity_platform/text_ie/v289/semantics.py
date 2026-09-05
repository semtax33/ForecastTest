from __future__ import annotations

from dataclasses import dataclass, replace
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
from ..v288 import semantics as prior_semantics


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v289_clause_transducer.arc"
V289_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V289_RULES}

_EXTRA_ALIASES = {
    "cash": "CASH",
    "cash resources": "CASH",
    "debt": "DEBT",
    "operating loss": "OPERATING_INCOME",
    "capital investment": "CAPEX",
    "cash capital investment": "CAPEX",
}
_NON_TARGET_PHRASES = (
    "cogs",
    "cost of goods sold",
    "free cash flow",
    "operating cash flow",
    "cash flow",
    "net cash from operating activities",
    "net cash from investing activities",
    "net cash from financing activities",
    "net income",
    "earnings per share",
    "loss per share",
    "working capital",
    "attendance",
    "net leverage",
    "cash dividend",
    "gross proceeds",
    "cash from operating activities",
    "cash provided by operating activities",
    "cash generated from operations",
)
_NEGATIVE_CUES = {"decrease", "decline", "fall", "fell", "drop", "reduce", "eliminate", "repay", "retire", "loss", "negative"}
_POSITIVE_CUES = {"increase", "grow", "climb", "rise", "rose", "improve", "expand", "up"}


def _base(concept: str) -> str:
    return prior_semantics._base(concept)


@dataclass(frozen=True)
class _Anchor:
    start: int
    end: int
    concept: str | None


@lru_cache(maxsize=1)
def semantic_backend_v289():
    return prior_semantics.semantic_backend_v288()


def semantic_quantities_v289(text: str, backend=None):
    selected = backend or semantic_backend_v289()
    quantities = list(prior_semantics.semantic_quantities_v288(text, selected))
    tokens = tuple(token for token in selected.parse(text) if not token.is_space)
    output = []
    for quantity in quantities:
        scaled = quantity
        if (
            quantity.kind is QuantityKind.MONEY
            and quantity.value < 1_000_000
            and "million" not in quantity.raw.casefold()
            and "billion" not in quantity.raw.casefold()
        ):
            token_index = next(
                (
                    index
                    for index, token in enumerate(tokens)
                    if quantity.char_start <= token.idx < quantity.char_end and token.like_num
                ),
                None,
            )
            if token_index is not None:
                suffix = tuple(token.lower_ for token in tokens[token_index + 1:token_index + 4])
                multiplier = 1_000_000_000 if "billion" in suffix else 1_000_000 if "million" in suffix else None
                if multiplier is not None and quantity.value < multiplier:
                    scaled = replace(quantity, value=quantity.value * multiplier)
        output.append(scaled)
    return tuple(output)


def _inside(start: int, end: int, outer_start: int, outer_end: int) -> bool:
    return outer_start <= start and end <= outer_end


def semantic_concepts_v289(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v289()
    barriers = tuple(
        (start, end)
        for _, start, end in selected.phrase_mentions(text, _NON_TARGET_PHRASES)
    )
    output = [
        mention
        for mention in prior_semantics.semantic_concepts_v288(text, selected)
        if not (
            _base(mention.concept) == "CASH"
            and any(_inside(mention.char_start, mention.char_end, left, right) for left, right in barriers)
        )
    ]
    for phrase, concept in _EXTRA_ALIASES.items():
        for literal, start, end in selected.phrase_mentions(text, (phrase,)):
            if phrase in {"cash", "debt"} and any(_inside(start, end, left, right) for left, right in barriers):
                continue
            output.append(ConceptMention(concept, literal, start, end))
    ordered = sorted(output, key=lambda item: (item.char_start, -(item.char_end - item.char_start), item.concept))
    selected_mentions: list[ConceptMention] = []
    for mention in ordered:
        if any(
            _base(existing.concept) == _base(mention.concept)
            and not (mention.char_end <= existing.char_start or mention.char_start >= existing.char_end)
            for existing in selected_mentions
        ):
            continue
        selected_mentions.append(mention)
    return tuple(sorted(selected_mentions, key=lambda item: (item.char_start, item.char_end, item.concept)))


def augment_candidates_v289(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...]) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v289()
    output = list(candidates)
    seen = {
        (item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end)
        for item in output
    }
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v289(block.text, backend)
        if not quantities:
            continue
        for mention in semantic_concepts_v289(block.text, backend):
            signature = (block.char_start, mention.concept, mention.char_start, mention.char_end)
            if signature in seen:
                continue
            allowed = set(definition_for(_base(mention.concept)).quantity_kinds) | {
                QuantityKind.MONEY,
                QuantityKind.PERCENT,
                QuantityKind.BASIS_POINTS,
                QuantityKind.COUNT,
                QuantityKind.RATE,
            }
            compatible = tuple(item for item in quantities if item.kind in allowed)
            if not compatible:
                continue
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:{mention.char_start}:{mention.char_end}:v289".encode()
            ).hexdigest()[:20]
            output.append(RecallCandidate(
                candidate_id=candidate_id,
                block=block,
                metric=MetricAnchor(mention.concept, mention.alias, mention.char_start, mention.char_end),
                quantities=compatible,
                origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                rule_ids=("v289.spacy_clause_candidate",),
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
        "binding_eligibility": "V289_SPACY_CLAUSE_TRANSDUCER",
        "parent_numeric_inheritance": False,
        "rule_program_sha256": rule.source_sha256,
    })
    return replace(
        frame,
        rule_id=rule_id,
        rule_version=rule.version,
        verified_by="V289_SPACY_CLAUSE_ROLE_VERIFIER",
        context_trace=trace,
    )


def _clause_ranges(text: str, backend) -> tuple[tuple[int, int], ...]:
    doc = backend.parse(text)
    boundaries = {0, len(text)}
    for sentence in doc.sents:
        boundaries.add(int(sentence.start_char))
        boundaries.add(int(sentence.end_char))
    for token in doc:
        if token.text in {"●", ";"}:
            boundaries.add(int(token.idx))
            boundaries.add(int(token.idx + len(token.text)))
    ordered = sorted(boundaries)
    output = []
    for left, right in zip(ordered, ordered[1:]):
        while left < right and (text[left].isspace() or text[left] in {"●", ";"}):
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if right > left:
            output.append((left, right))
    return tuple(output)


def _anchors(text: str, concepts: tuple[ConceptMention, ...], backend) -> tuple[_Anchor, ...]:
    output = [_Anchor(item.char_start, item.char_end, _base(item.concept)) for item in concepts]
    for _, start, end in backend.phrase_mentions(text, _NON_TARGET_PHRASES):
        if any(_inside(start, end, item.char_start, item.char_end) for item in concepts):
            continue
        output.append(_Anchor(start, end, None))
    unique = {(item.start, item.end, item.concept): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.start, item.end, item.concept or "")))


def _distance(quantity: QuantityMention, anchor: _Anchor) -> int:
    if quantity.char_end <= anchor.start:
        return anchor.start - quantity.char_end
    if quantity.char_start >= anchor.end:
        return quantity.char_start - anchor.end
    return 0


def _owned_quantities(quantities, anchors, concept: str, text: str):
    output = []
    for quantity in quantities:
        def ownership_key(item: _Anchor):
            following_penalty = 0
            if quantity.char_end <= item.start:
                bridge = text[quantity.char_end:item.start].casefold()
                if "of" not in {token.lemma_.casefold() for token in semantic_backend_v289().parse(bridge)}:
                    following_penalty = 100
            return (_distance(quantity, item) + following_penalty, 0 if item.concept is None else 1, item.start)

        owner = min(
            anchors,
            key=ownership_key,
            default=None,
        )
        if owner is not None and owner.concept == concept:
            output.append(quantity)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end)))


def _cue_positions(text: str, backend, phrases: tuple[str, ...]) -> tuple[int, ...]:
    return tuple(start for _, start, _ in backend.phrase_mentions(text, phrases))


def _has_cue(text: str, backend, phrases: tuple[str, ...]) -> bool:
    return bool(_cue_positions(text, backend, phrases))


def _polarity(text: str, backend, *, default: bool = True) -> bool:
    direction = default
    for token in backend.parse(text):
        cue = token.lemma_.casefold()
        if cue in _NEGATIVE_CUES or token.lower_ in _NEGATIVE_CUES:
            direction = False
        elif cue in _POSITIVE_CUES or token.lower_ in _POSITIVE_CUES:
            direction = True
    return direction


def _parenthesized(text: str, quantity: QuantityMention) -> bool:
    left = text[max(0, quantity.char_start - 2):quantity.char_start]
    right = text[quantity.char_end:quantity.char_end + 2]
    return "(" in left and ")" in right


def _after_cue(items, text: str, backend, phrases: tuple[str, ...]):
    positions = _cue_positions(text, backend, phrases)
    if not positions:
        return ()
    position = positions[-1]
    return tuple(item for item in items if item.char_start > position)


def _emit_comparison(document, block, candidates, concept, values, text, backend):
    if len(values) < 2:
        return ()
    first, second = values[:2]
    first_positive = not (_base(concept) == "OPERATING_INCOME" and _has_cue(text[: first.char_end], backend, ("operating loss",)))
    second_positive = first_positive
    if _base(concept) == "OPERATING_INCOME":
        tail = text[first.char_end:]
        if _has_cue(tail, backend, ("operating income", "operating profit")):
            second_positive = True
        elif _has_cue(tail, backend, ("operating loss",)):
            second_positive = False
    output = []
    for output_concept, value, positive in (
        (_base(concept), first, first_positive),
        (f"PRIOR_YEAR_{_base(concept)}", second, second_positive),
    ):
        frame = _new_frame(
            document,
            block,
            candidates,
            rule_id="v289.comparative_role",
            concept=output_concept,
            semantic=SemanticFrame.COMPARATIVE,
            value=value,
            positive=positive,
        )
        if frame is not None:
            output.append(frame)
    return tuple(output)


def _transduce_clause(document, block, candidates, clause_start, clause_end, concepts, quantities, backend):
    text = block.text[clause_start:clause_end]
    local_concepts = tuple(
        replace(item, char_start=item.char_start - clause_start, char_end=item.char_end - clause_start)
        for item in concepts
        if _inside(item.char_start, item.char_end, clause_start, clause_end)
    )
    local_quantities = tuple(
        replace(item, char_start=item.char_start - clause_start, char_end=item.char_end - clause_start)
        for item in quantities
        if _inside(item.char_start, item.char_end, clause_start, clause_end)
    )
    if not local_concepts or not local_quantities:
        return (), False
    anchors = _anchors(text, local_concepts, backend)
    output = []
    adjudicated = False
    concepts_by_base: dict[str, list[ConceptMention]] = {}
    for mention in local_concepts:
        concepts_by_base.setdefault(_base(mention.concept), []).append(mention)

    comparative = _has_cue(text, backend, ("compared with", "compared to", "prior year", "prior-year", "last year"))
    range_cue = _has_cue(text, backend, ("in the range", "range of", "range between", "guidance range"))
    future = range_cue or _has_cue(text, backend, ("expects", "expected", "guidance", "outlook", "q3", "q4", "full year"))
    directional = _has_cue(
        text,
        backend,
        (
            "increased", "decreased", "grew", "grow", "growth", "climbed", "fell",
            "declined", "up by", "rose", "eliminated", "reduced", "repaid", "retired",
        ),
    )
    positive = _polarity(text, backend)

    for concept in concepts_by_base:
        owned = _owned_quantities(local_quantities, anchors, concept, text)
        if not owned:
            continue
        money = tuple(item for item in owned if item.kind is QuantityKind.MONEY)
        percents = tuple(item for item in owned if item.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS})
        rates = tuple(item for item in owned if item.kind is QuantityKind.RATE)
        concept_comparative = comparative or (
            concept == "GROSS_MARGIN" and _has_cue(text, backend, ("from",))
        )

        if concept == "BOOK_TO_BILL" and rates:
            adjudicated = True
            for value in rates:
                frame = _new_frame(document, block, candidates, rule_id="v289.absolute_role", concept=concept, semantic=SemanticFrame.ABSOLUTE_VALUE, value=value)
                if frame is not None:
                    output.append(frame)
            continue

        if range_cue and future and concept in {"REVENUE", "ADJUSTED_EBITDA", "GROSS_MARGIN", "CAPEX", "SHARES"}:
            values = money if money else percents
            if len(values) >= 2:
                selected = values[:2]
                low, high = sorted(selected, key=lambda item: item.value)
                midpoint = replace(low, value=(low.value + high.value) / 2)
                negative = all(_parenthesized(text, item) for item in selected)
                frame = _new_frame(
                    document,
                    block,
                    candidates,
                    rule_id="v289.forward_range_role",
                    concept=f"{concept}_GUIDANCE",
                    semantic=SemanticFrame.RANGE_GUIDANCE,
                    value=midpoint,
                    lower=low,
                    upper=high,
                    positive=not negative,
                )
                adjudicated = True
                if frame is not None:
                    output.append(frame)
                continue

        to_positions = _cue_positions(text, backend, ("to",))
        comparator_positions = _cue_positions(text, backend, ("compared to", "compared with"))
        comparator_start = comparator_positions[0] if comparator_positions else len(text)
        current_to = next((position for position in to_positions if position < comparator_start), None)
        to_values = tuple(
            item for item in money
            if current_to is not None and current_to < item.char_start < comparator_start
        )
        if directional and to_values:
            current = to_values[0]
            before_current_percent = tuple(item for item in percents if item.char_end <= current.char_start)
            by_values = _after_cue(money, text, backend, ("by", "up by"))
            change = before_current_percent[-1] if before_current_percent else next(
                (item for item in by_values if item.char_end <= current.char_start),
                None,
            )
            if change is not None:
                frame = _new_frame(document, block, candidates, rule_id="v289.change_to_role", concept=concept, semantic=SemanticFrame.CHANGE_TO, value=current, change=change, positive=positive)
                adjudicated = True
                if frame is not None:
                    output.append(frame)
                continue
            if concept_comparative and len(money) >= 2:
                output.extend(_emit_comparison(document, block, candidates, concept, (current, money[-1]), text, backend))
                adjudicated = True
                continue
            frame = _new_frame(document, block, candidates, rule_id="v289.absolute_role", concept=concept, semantic=SemanticFrame.ABSOLUTE_VALUE, value=current, positive=positive)
            adjudicated = True
            if frame is not None:
                output.append(frame)
            continue

        if (
            directional
            and money
            and percents
            and _has_cue(text, backend, ("was", "were"))
            and _has_cue(text, backend, ("up by", "increased by", "decreased by"))
        ):
            frame = _new_frame(
                document,
                block,
                candidates,
                rule_id="v289.change_to_role",
                concept=concept,
                semantic=SemanticFrame.CHANGE_TO,
                value=money[0],
                change=percents[-1],
                positive=positive,
            )
            adjudicated = True
            if frame is not None:
                output.append(frame)
            continue

        if concept_comparative and concept in {"REVENUE", "GROSS_MARGIN", "OPERATING_INCOME", "CASH"}:
            values = percents if concept == "GROSS_MARGIN" else money
            if len(values) >= 2:
                output.extend(_emit_comparison(document, block, candidates, concept, values, text, backend))
                adjudicated = True
                continue

        if directional and concept in {"REVENUE", "CASH", "ADJUSTED_EBITDA", "DEBT"}:
            if money and concept == "DEBT":
                value = money[-1]
                frame = _new_frame(document, block, candidates, rule_id="v289.change_to_role", concept=concept, semantic=SemanticFrame.CHANGE_BY, value=value, positive=positive)
                adjudicated = True
                if frame is not None:
                    output.append(frame)
                continue
            if percents and not money:
                value = percents[-1]
                frame = _new_frame(document, block, candidates, rule_id="v289.change_to_role", concept=concept, semantic=SemanticFrame.CHANGE_BY, value=value, positive=positive)
                adjudicated = True
                if frame is not None:
                    output.append(frame)
                continue
            if money:
                current = money[0]
                change = percents[-1] if percents else None
                if change is not None:
                    frame = _new_frame(document, block, candidates, rule_id="v289.change_to_role", concept=concept, semantic=SemanticFrame.CHANGE_TO, value=current, change=change, positive=positive)
                    adjudicated = True
                    if frame is not None:
                        output.append(frame)
                    continue

        if concept in {"REVENUE", "CASH", "DEBT", "CAPEX", "ADJUSTED_EBITDA", "BACKLOG", "ORDERS"} and money:
            value = money[0]
            frame = _new_frame(document, block, candidates, rule_id="v289.absolute_role", concept=concept, semantic=SemanticFrame.ABSOLUTE_VALUE, value=value, positive=positive)
            adjudicated = True
            if frame is not None:
                output.append(frame)

    non_target_owned = any(anchor.concept is None for anchor in anchors) and not output
    return tuple(output), adjudicated or non_target_owned


def recover_v289_frames(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...], allowed_spans: set[tuple[int, int]]):
    backend = semantic_backend_v289()
    blocks = {(item.block.char_start, item.block.char_end): item.block for item in candidates}
    output = []
    adjudicated_spans = set()
    for span, block in blocks.items():
        if span not in allowed_spans:
            continue
        concepts = semantic_concepts_v289(block.text, backend)
        quantities = semantic_quantities_v289(block.text, backend)
        for left, right in _clause_ranges(block.text, backend):
            frames, adjudicated = _transduce_clause(
                document,
                block,
                candidates,
                left,
                right,
                concepts,
                quantities,
                backend,
            )
            output.extend(frames)
            if adjudicated:
                adjudicated_spans.add(span)
    return tuple(output), adjudicated_spans


def resolve_frame_conflicts_v289(existing, recovered, adjudicated_spans):
    selected = [
        frame for frame in existing
        if (frame.source_span.char_start, frame.source_span.char_end) not in adjudicated_spans
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
