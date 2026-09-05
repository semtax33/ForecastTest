from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from hashlib import sha256

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..document import document_text_blocks
from ..dsl import compile_text_rule_file
from ..model import ConceptMention, QuantityKind, QuantityMention, SemanticFrame
from ..ontology import definition_for
from ..role_graph import build_frame_role_intent, materialize_role_intent
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v280 import semantics as frame_factory
from ..v289 import semantics as prior


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v290_semantic_role_graph.arc"
V290_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V290_RULES}

_EXTRA_ALIASES = {
    "unit sales": "ACTIVITY_VOLUME",
    "membership": "ACTIVITY_VOLUME",
    "memberships": "ACTIVITY_VOLUME",
    "members": "ACTIVITY_VOLUME",
    "hotels": "ACTIVITY_VOLUME",
    "guest rooms": "ACTIVITY_VOLUME",
    "rooms": "ACTIVITY_VOLUME",
    "revpar": "REVENUE",
    "ebit margin": "OPERATING_MARGIN",
    "royalties": "REVENUE",
    "royalty": "REVENUE",
    "shares": "SHARES",
}
_CONCEPT_EXCLUSIONS = (
    "non-cash",
    "non cash",
    "cash flow",
    "cash from operations",
    "cash from operating activities",
    "cash used in operating activities",
    "cash generated from operations",
    "cash provided by operating activities",
    "excluding restricted cash",
    "sales and marketing expense",
    "sales and marketing",
    "selling and marketing expense",
    "selling and marketing",
    "sales, general and administrative expense",
    "cost of revenues",
    "cost of revenue",
    "revenue base",
    "gross sales price",
    "sales price",
    "peak sales guidance",
)
_OWNERSHIP_BARRIERS = _CONCEPT_EXCLUSIONS + (
    "liquidity",
    "availability",
    "accounts receivable",
    "loans receivable",
    "operating expenses",
    "marketing expense",
    "compensation expense",
    "cost of services",
    "cogs",
    "cost of goods sold",
    "gross proceeds",
    "equity offering",
    "equity offerings",
    "attendance",
    "reflecting",
    "markets",
    "states",
    "countries",
)
_NEGATIVE = (
    "decrease", "decreased", "decline", "declined", "fall", "fell", "drop", "dropped",
    "reduce", "reduced", "reduction", "loss", "negative", "repay", "repaid", "retire", "retired",
    "eliminate", "eliminated", "elimination", "eliminations",
)
_POSITIVE = (
    "increase", "increased", "grow", "growth", "grew", "up", "rise", "rose", "higher",
    "increasing", "growing", "improve", "improved", "expand", "expanded", "climb", "climbed",
)
_DIRECTIONAL = _NEGATIVE + _POSITIVE
_COMPARATORS = ("compared to", "compared with", "prior year", "prior-year", "last year", "versus", "vs")
_FUTURE = (
    "expect",
    "expects",
    "expected",
    "guidance",
    "outlook",
    "forecast",
    "full year",
    "annualized",
    "in the range",
    "range between",
)


def _base(concept: str) -> str:
    return prior._base(concept)


@dataclass(frozen=True)
class _Anchor:
    start: int
    end: int
    concept: str | None


@dataclass(frozen=True)
class _OwnershipBinding:
    concept: str
    concept_char_start: int
    concept_char_end: int
    quantity: QuantityMention


@lru_cache(maxsize=1)
def semantic_backend_v290():
    return prior.semantic_backend_v289()


def _inside(start: int, end: int, left: int, right: int) -> bool:
    return left <= start and end <= right


def _phrase_spans(text: str, backend, phrases: tuple[str, ...]):
    return tuple((start, end) for _, start, end in backend.phrase_mentions(text, phrases))


def _parse_numeric(raw: str) -> float | None:
    normalized = raw.replace(",", "").replace("%", "").strip().strip("()")
    try:
        return float(normalized)
    except ValueError:
        return None


def _local_range_bridge(bridge: str) -> bool:
    normalized = bridge.casefold()
    for punctuation in ("(", ")", "[", "]", ","):
        normalized = normalized.replace(punctuation, " ")
    words = tuple(normalized.split())
    if not words or len(bridge) > 30:
        return False
    if len(words) == 1:
        return words[0] in {"-", "–", "—", "to"}
    return "to" in words and all(
        word in {"to", "thousand", "million", "billion"}
        for word in words
    )


def semantic_quantities_v290(text: str, backend=None) -> tuple[QuantityMention, ...]:
    selected = backend or semantic_backend_v290()
    output = list(prior.semantic_quantities_v289(text, selected))
    occupied = [(item.char_start, item.char_end) for item in output]
    activity_spans = _phrase_spans(text, selected, tuple(_EXTRA_ALIASES))
    tokens = tuple(token for token in selected.parse(text) if not token.is_space)

    for token in tokens:
        raw = token.text
        value = _parse_numeric(raw)
        if value is None:
            continue
        start = int(token.idx)
        end = int(token.idx + len(raw))
        if any(not (end <= left or start >= right) for left, right in occupied):
            continue
        if "%" in raw:
            output.append(QuantityMention(QuantityKind.PERCENT, value, "PERCENT", raw, start, end))
            occupied.append((start, end))
            continue
        if not token.like_num or 1900 <= value <= 2100:
            continue
        if not any(abs(start - left) <= 55 or abs(start - right) <= 55 for left, right in activity_spans):
            continue
        output.append(QuantityMention(QuantityKind.COUNT, value, "COUNT", raw, start, end))
        occupied.append((start, end))

    # Remove count-shaped duplicates of money and calendar day/year tokens.
    # This prevents "$457 million" from becoming a share count and "June 30"
    # from becoming hotel capacity.
    money_spans = tuple(
        (item.char_start, item.char_end)
        for item in output
        if item.kind is QuantityKind.MONEY
    )
    month_names = (
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    )
    cleaned = []
    for item in output:
        if item.kind is QuantityKind.COUNT:
            overlaps_money = any(
                not (item.char_end <= left or item.char_start >= right)
                for left, right in money_spans
            )
            calendar_prefix = text[max(0, item.char_start - 14):item.char_start].casefold()
            if overlaps_money or 1900 <= item.value <= 2100 or any(month in calendar_prefix for month in month_names):
                continue
        cleaned.append(item)
    output = cleaned

    # Older quantity recovery can interpret the percent immediately before a
    # later "basis points" phrase as both PERCENT and BASIS_POINTS.  Preserve
    # the explicit percent token and discard only that overlapping phantom.
    percents = tuple(item for item in output if item.kind is QuantityKind.PERCENT)
    output = [
        item for item in output
        if not (
            item.kind is QuantityKind.BASIS_POINTS
            and any(
                item.value == percent.value
                and not (item.char_end <= percent.char_start or item.char_start >= percent.char_end)
                for percent in percents
            )
        )
    ]
    ordered = sorted(output, key=lambda item: (item.char_start, item.char_end, item.kind.value))
    # A range often carries the scale only on its second endpoint: "$285 -
    # $300 million".  Propagate that local unit across the separator, never
    # across an arbitrary parent/sibling context.
    harmonized = list(ordered)
    money_indices = [i for i, item in enumerate(harmonized) if item.kind is QuantityKind.MONEY]
    for left_index, right_index in zip(money_indices, money_indices[1:]):
        left = harmonized[left_index]
        right = harmonized[right_index]
        bridge = text[left.char_end:right.char_start].casefold().strip()
        if not _local_range_bridge(bridge):
            continue
        # In "increased by $3,000 to $6.6 million", the first amount is an
        # explicit delta, not the unit-less lower endpoint of a range.
        left_prefix = text[max(0, left.char_start - 18):left.char_start].casefold().rstrip()
        if left_prefix.endswith("by"):
            continue
        multiplier = 1_000_000_000 if right.value >= 1_000_000_000 else 1_000_000 if right.value >= 1_000_000 else None
        if multiplier is not None and left.value < 1_000_000:
            harmonized[left_index] = replace(left, value=left.value * multiplier)
    return tuple(harmonized)


def semantic_concepts_v290(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v290()
    excluded = _phrase_spans(text, selected, _CONCEPT_EXCLUSIONS)
    output = []
    for mention in prior.semantic_concepts_v289(text, selected):
        if any(_inside(mention.char_start, mention.char_end, left, right) for left, right in excluded):
            continue
        output.append(mention)
    for phrase, concept in _EXTRA_ALIASES.items():
        for literal, start, end in selected.phrase_mentions(text, (phrase,)):
            if any(_inside(start, end, left, right) for left, right in excluded):
                continue
            output.append(ConceptMention(concept, literal, start, end))
    ordered = sorted(output, key=lambda item: (item.char_start, -(item.char_end - item.char_start), item.concept))
    kept: list[ConceptMention] = []
    for mention in ordered:
        if any(
            _base(other.concept) == _base(mention.concept)
            and not (mention.char_end <= other.char_start or mention.char_start >= other.char_end)
            for other in kept
        ):
            continue
        kept.append(mention)
    return tuple(sorted(kept, key=lambda item: (item.char_start, item.char_end, item.concept)))


def augment_candidates_v290(document: CanonicalDocument, candidates: tuple[RecallCandidate, ...]) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v290()
    output = list(candidates)
    seen = {(item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end) for item in output}
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v290(block.text, backend)
        if not quantities:
            continue
        for mention in semantic_concepts_v290(block.text, backend):
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
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:{mention.char_start}:{mention.char_end}:v290".encode()
            ).hexdigest()[:20]
            output.append(RecallCandidate(
                candidate_id=candidate_id,
                block=block,
                metric=MetricAnchor(mention.concept, mention.alias, mention.char_start, mention.char_end),
                quantities=compatible,
                origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                rule_ids=("v290.spacy_role_graph_candidate",),
            ))
            seen.add(signature)
    return tuple(output)


def _new_frame(document, block, candidates, *, concept, semantic, value, change=None, lower=None, upper=None, positive=True):
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
    rule = _RULE_BY_ID["v290.range_graph" if semantic is SemanticFrame.RANGE_GUIDANCE else "v290.role_graph"]
    trace = dict(frame.context_trace)
    trace.update({
        "binding_eligibility": "V290_SPACY_SEMANTIC_ROLE_GRAPH",
        "parent_numeric_inheritance": False,
        "rule_program_sha256": rule.source_sha256,
    })
    return replace(
        frame,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        verified_by="V290_SPACY_ROLE_GRAPH_VERIFIER",
        context_trace=trace,
    )


def _has(text: str, backend, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _positions(text: str, backend, phrases: tuple[str, ...]) -> tuple[int, ...]:
    return tuple(start for _, start, _ in backend.phrase_mentions(text, phrases))


def _polarity(text: str, backend) -> bool:
    direction = True
    for token in backend.parse(text):
        cue = token.lemma_.casefold()
        if cue in _NEGATIVE or token.lower_ in _NEGATIVE:
            direction = False
        elif cue in _POSITIVE or token.lower_ in _POSITIVE:
            direction = True
    return direction


def _anchors(text: str, concepts: tuple[ConceptMention, ...], backend) -> tuple[_Anchor, ...]:
    output = [_Anchor(item.char_start, item.char_end, _base(item.concept)) for item in concepts]
    output.extend(_Anchor(start, end, None) for start, end in _phrase_spans(text, backend, _OWNERSHIP_BARRIERS))
    unique = {(item.start, item.end, item.concept): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.start, item.end, item.concept or "")))


def _distance(quantity: QuantityMention, anchor: _Anchor) -> int:
    if quantity.char_end <= anchor.start:
        return anchor.start - quantity.char_end
    if quantity.char_start >= anchor.end:
        return quantity.char_start - anchor.end
    return 0


def _owned(quantities, anchors, concept: str, text: str):
    ordered = tuple(sorted(quantities, key=lambda item: (item.char_start, item.char_end)))
    def ownership_key(quantity: QuantityMention, item: _Anchor):
        compatibility_penalty = 0
        if item.concept is not None:
            allowed = set(definition_for(item.concept).quantity_kinds)
            relation_kind = quantity.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
            if allowed and quantity.kind not in allowed and not relation_kind:
                compatibility_penalty = 1_000
        syntax_bonus = 0
        if quantity.char_end <= item.start:
            bridge = text[quantity.char_end:item.start].casefold()
            if len(bridge) <= 12 and bridge.strip() in {"of", "in"}:
                syntax_bonus = -35
        elif item.end <= quantity.char_start:
            bridge = text[item.end:quantity.char_start].casefold()
            if len(bridge) <= 35 and any(cue in bridge for cue in (" of ", " was ", " were ", " totaled ")):
                syntax_bonus = -35
        return (
            _distance(quantity, item) + compatibility_penalty + syntax_bonus,
            0 if item.concept is None else 1,
            item.start,
        )

    owners = [min(anchors, key=lambda item: ownership_key(quantity, item), default=None) for quantity in ordered]
    # A directional predicate assigns its following value to the closest
    # preceding subject/metric.  This outranks proximity to the next
    # comma-separated metric ("loans increased $X, capex was $Y").
    for index, quantity in enumerate(ordered):
        preceding = [anchor for anchor in anchors if anchor.end <= quantity.char_start]
        if not preceding:
            continue
        subject = max(preceding, key=lambda item: item.end)
        bridge = text[subject.end:quantity.char_start]
        if _has(bridge, semantic_backend_v290(), _DIRECTIONAL):
            owners[index] = subject
    # A postposed nominal role such as "99% growth in memberships" is more
    # specific than the earlier causal subject "revenue growth was driven by".
    for index, quantity in enumerate(ordered):
        following = [
            anchor for anchor in anchors
            if anchor.concept is not None and anchor.start >= quantity.char_end
        ]
        for target in sorted(following, key=lambda item: item.start):
            bridge = text[quantity.char_end:target.start].casefold()
            postposed_role = (
                len(bridge) <= 12 and bridge.strip() in {"of", "in"}
            ) or (
                len(bridge) <= 55
                and any(cue in bridge for cue in ("growth in", "increase in", "decrease in"))
            ) or (
                len(bridge) <= 45
                and ("of outstanding" in bridge or bridge.strip().endswith("of"))
            )
            if postposed_role:
                owners[index] = target
                break
    # The unit-bearing second endpoint of a range is often closer to the next
    # metric label.  A local range edge has stronger semantic ownership than
    # raw character distance, so it inherits the first endpoint's owner.
    for index in range(1, len(ordered)):
        if _is_range_pair(text, ordered[index - 1], ordered[index]):
            owners[index] = owners[index - 1]
    # Basis-point deltas modify the nearest preceding margin, even when a
    # later causal phrase mentions pricing or revenue.
    for index, quantity in enumerate(ordered):
        if quantity.kind is not QuantityKind.BASIS_POINTS:
            continue
        margins = [
            anchor for anchor in anchors
            if anchor.concept in {"GROSS_MARGIN", "OPERATING_MARGIN", "ADJUSTED_EBITDA_MARGIN"}
            and anchor.end <= quantity.char_start
        ]
        if margins:
            owners[index] = max(margins, key=lambda item: item.end)
    return tuple(
        _OwnershipBinding(concept, owner.start, owner.end, quantity)
        for quantity, owner in zip(ordered, owners)
        if owner is not None and owner.concept == concept
    )


def _append_role_intent(output, **kwargs) -> None:
    output.append(build_frame_role_intent(**kwargs))


def _materialize_role_intents(document, block, candidates, intents):
    output = []
    for intent in intents:
        item = materialize_role_intent(intent)
        frame = _new_frame(
            document,
            block,
            candidates,
            concept=item.concept,
            semantic=item.semantic,
            value=item.value,
            change=item.change,
            lower=item.lower,
            upper=item.upper,
            positive=item.positive,
        )
        if frame is not None:
            output.append(frame)
    return output


def _is_range_pair(text: str, first: QuantityMention, second: QuantityMention) -> bool:
    bridge = text[first.char_end:second.char_start].casefold().strip()
    return _local_range_bridge(bridge)


def _current_after_to(values, text: str, backend):
    positions = _positions(text, backend, ("to",))
    directional = _positions(text, backend, _DIRECTIONAL)
    if not directional:
        return None
    for position in reversed(positions):
        if not any(cue <= position for cue in directional):
            continue
        prefix = text[max(0, position - 32):position].casefold().rstrip()
        if prefix.endswith(("compared", "due", "due primarily", "related")):
            continue
        selected = next((item for item in values if item.char_start > position), None)
        if selected is not None:
            return selected
    return None


def _build_role_intents(text, concept, mentions, values, backend):
    output = []
    money = tuple(item for item in values if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in values if item.kind is QuantityKind.PERCENT)
    basis = tuple(item for item in values if item.kind is QuantityKind.BASIS_POINTS)
    counts = tuple(item for item in values if item.kind is QuantityKind.COUNT)
    rates = tuple(item for item in values if item.kind is QuantityKind.RATE)
    positive = _polarity(text, backend)
    directional = _has(text, backend, _DIRECTIONAL)
    comparative = _has(text, backend, _COMPARATORS)
    future = _has(text, backend, _FUTURE)

    if concept == "BOOK_TO_BILL" and rates:
        for value in rates:
            _append_role_intent(output, concept=concept, semantic=SemanticFrame.ABSOLUTE_VALUE, value=value)
        return output

    principal = (
        counts if concept in {"ACTIVITY_VOLUME", "SHARES"}
        else percents if concept in {"GROSS_MARGIN", "OPERATING_MARGIN", "ADJUSTED_EBITDA_MARGIN"}
        else money
    )

    if future and len(principal) >= 2 and _is_range_pair(text, principal[0], principal[1]):
        low, high = sorted(principal[:2], key=lambda item: item.value)
        _append_role_intent(
            output,
            concept=f"{concept}_GUIDANCE",
            semantic=SemanticFrame.RANGE_GUIDANCE,
            lower=low,
            upper=high,
            positive=not all(prior._parenthesized(text, item) for item in (low, high)),
        )
        return output

    if concept == "REVENUE" and percents and _has(text, backend, ("represented", "accounted for", "percentage of total", "of total revenue")):
        _append_role_intent(output, concept=concept, semantic=SemanticFrame.COMPOSITION, value=percents[0])
        if directional:
            for change in percents[1:]:
                _append_role_intent(output, concept=concept, semantic=SemanticFrame.CHANGE_BY, value=change, positive=positive)
        return output

    current = _current_after_to(principal, text, backend) or (principal[0] if principal else None)
    if current is not None:
        direct_span_start = min((mention.char_start for mention in mentions), default=0)
        direct_span = text[direct_span_start:current.char_end]
        direction_positions = _positions(text, backend, _DIRECTIONAL)
        if (
            _has(direct_span, backend, ("was", "were", "totaled"))
            and direction_positions
            and all(position < direct_span_start for position in direction_positions)
        ):
            directional = False
    numeric_change = None
    remaining_percent = list(percents)
    if current is not None and current.kind is QuantityKind.PERCENT:
        remaining_percent = [item for item in remaining_percent if item is not current]
    if basis and current is not None:
        numeric_change = basis[0]
    elif remaining_percent and current is not None and current.kind in {QuantityKind.MONEY, QuantityKind.COUNT}:
        numeric_change = remaining_percent[0]

    # Explicit monetary delta after a comparator: current, prior, then change.
    if directional and numeric_change is None and concept in {"CASH", "REVENUE"} and len(money) >= 3:
        cue_positions = _positions(text, backend, _DIRECTIONAL)
        after_cue = [item for item in money if cue_positions and item.char_start > cue_positions[-1]]
        if after_cue:
            numeric_change = after_cue[0]
            current = current or money[0]

    # "to X from Y" without an independently stated delta is a comparison,
    # including margin expansion and balance changes.
    directional_to_from = (
        directional
        and len(principal) >= 2
        and _has(text, backend, ("to",))
        and _has(text, backend, ("from",))
    )
    if (comparative or directional_to_from) and len(principal) >= 2 and numeric_change is None:
        comparison_values = list(principal)
        current_value = _current_after_to(principal, text, backend) or comparison_values[0]
        comparison_values.remove(current_value)
        first_positive = positive
        if "loss" in text.casefold() and concept in {"OPERATING_INCOME", "ADJUSTED_EBITDA"}:
            first_positive = False
        _append_role_intent(output, concept=concept, semantic=SemanticFrame.COMPARATIVE, value=current_value, positive=first_positive)
        for prior_value in comparison_values:
            _append_role_intent(output, concept=f"PRIOR_YEAR_{concept}", semantic=SemanticFrame.COMPARATIVE, value=prior_value, positive=first_positive)
        return output

    if directional and current is not None and numeric_change is not None:
        _append_role_intent(output, concept=concept, semantic=SemanticFrame.CHANGE_TO, value=current, change=numeric_change, positive=positive)
        if concept == "REVENUE" and numeric_change.kind is QuantityKind.PERCENT:
            for component in remaining_percent[1:]:
                _append_role_intent(output, concept=concept, semantic=SemanticFrame.CHANGE_BY, value=component, positive=_polarity(text[max(0, component.char_start - 45):component.char_end + 20], backend))
        return output

    if directional and not principal and percents and concept in {"REVENUE", "CASH", "DEBT", "ADJUSTED_EBITDA", "ACTIVITY_VOLUME", "SHARES"}:
        for change in percents:
            _append_role_intent(output, concept=concept, semantic=SemanticFrame.CHANGE_BY, value=change, positive=positive)
        return output

    if directional and len(principal) == 1 and concept in {"DEBT", "CAPEX", "SHARES"}:
        _append_role_intent(output, concept=concept, semantic=SemanticFrame.CHANGE_BY, value=principal[0], positive=positive)
        return output

    if future and principal:
        _append_role_intent(output, concept=f"{concept}_GUIDANCE", semantic=SemanticFrame.ABSOLUTE_VALUE, value=principal[0], positive=positive)
        return output

    if principal:
        emit_all = concept == "ACTIVITY_VOLUME" or _has(text, backend, ("include", "includes", "consist", "consists")) or len(mentions) > 1
        for value in principal if emit_all else principal[:1]:
            _append_role_intent(output, concept=concept, semantic=SemanticFrame.ABSOLUTE_VALUE, value=value, positive=positive)
    return output


def _suppression_cue(text: str, backend) -> bool:
    folded = text.casefold().lstrip()
    return _has(text, backend, _CONCEPT_EXCLUSIONS) or (folded.startswith("based in ") and "annual sales" in folded)


def _transduce_clause(
    document,
    block,
    candidates,
    clause_start,
    clause_end,
    concepts,
    quantities,
    backend,
    observer=None,
):
    text = block.text[clause_start:clause_end]
    folded = text.casefold().lstrip()
    candidate_ids = tuple(
        candidate.candidate_id
        for candidate in candidates
        if candidate.block.char_start == block.char_start
        and candidate.block.char_end == block.char_end
        and clause_start <= candidate.metric.char_start < clause_end
    )

    def observe(
        *,
        local_concepts=(),
        local_quantities=(),
        bindings=(),
        role_intents=(),
        frames=(),
        adjudicated=False,
        primary_root_cause: str,
    ) -> None:
        if observer is None:
            return
        observer({
            "block": block,
            "clause_start": clause_start,
            "clause_end": clause_end,
            "candidate_ids": candidate_ids,
            "concepts": tuple(local_concepts),
            "quantities": tuple(local_quantities),
            "bindings": tuple(bindings),
            "role_intents": tuple(role_intents),
            "frames": tuple(frames),
            "adjudicated": adjudicated,
            "primary_root_cause": primary_root_cause,
        })

    if folded.startswith("based in ") and "annual sales" in folded:
        observe(primary_root_cause="SUPPRESSED_NON_TARGET")
        return (), True
    if "shares" in folded and "excluded from" in folded:
        observe(primary_root_cause="SUPPRESSED_NON_TARGET")
        return (), True
    local_concepts = tuple(
        replace(item, char_start=item.char_start - clause_start, char_end=item.char_end - clause_start)
        for item in concepts
        if _inside(item.char_start, item.char_end, clause_start, clause_end)
    )
    marketing_subjects = _phrase_spans(text, backend, ("sales and marketing", "selling and marketing"))
    if (
        marketing_subjects
        and local_concepts
        and marketing_subjects[0][0] < min(item.char_start for item in local_concepts)
    ):
        observe(
            local_concepts=local_concepts,
            primary_root_cause="SUPPRESSED_NON_TARGET",
        )
        return (), True
    if "marketing" in folded and "expense" in folded:
        local_concepts = tuple(item for item in local_concepts if _base(item.concept) != "REVENUE")
    local_quantities = tuple(
        replace(item, char_start=item.char_start - clause_start, char_end=item.char_end - clause_start)
        for item in quantities
        if _inside(item.char_start, item.char_end, clause_start, clause_end)
    )
    if not local_quantities:
        observe(
            local_concepts=local_concepts,
            primary_root_cause="NO_QUANTITY_IN_CLAUSE",
        )
        return (), False
    anchors = _anchors(text, local_concepts, backend)
    by_concept: dict[str, list[ConceptMention]] = {}
    for mention in local_concepts:
        by_concept.setdefault(_base(mention.concept), []).append(mention)
    role_intents = []
    bindings = []
    for concept, mentions in by_concept.items():
        owned_bindings = _owned(local_quantities, anchors, concept, text)
        if owned_bindings:
            bindings.extend(owned_bindings)
            role_intents.extend(
                _build_role_intents(
                    text,
                    concept,
                    mentions,
                    tuple(binding.quantity for binding in owned_bindings),
                    backend,
                )
            )
    output = _materialize_role_intents(document, block, candidates, role_intents)
    adjudicated = bool(by_concept) or _suppression_cue(text, backend)
    primary_root_cause = (
        "EMITTED"
        if output
        else "NO_CONCEPT_IN_CLAUSE"
        if not by_concept
        else "NO_COMPATIBLE_OWNER_BINDING"
        if not bindings
        else "UNRESOLVED_SEMANTIC_ROLE"
    )
    observe(
        local_concepts=local_concepts,
        local_quantities=local_quantities,
        bindings=bindings,
        role_intents=role_intents,
        frames=output,
        adjudicated=adjudicated,
        primary_root_cause=primary_root_cause,
    )
    return tuple(output), adjudicated


def recover_v290_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    observer=None,
):
    backend = semantic_backend_v290()
    blocks = {(item.block.char_start, item.block.char_end): item.block for item in candidates}
    output = []
    adjudicated_spans = set()
    for span, block in blocks.items():
        if span not in allowed_spans:
            continue
        concepts = semantic_concepts_v290(block.text, backend)
        quantities = semantic_quantities_v290(block.text, backend)
        span_adjudicated = False
        for left, right in prior._clause_ranges(block.text, backend):
            frames, adjudicated = _transduce_clause(
                document,
                block,
                candidates,
                left,
                right,
                concepts,
                quantities,
                backend,
                observer,
            )
            output.extend(frames)
            span_adjudicated = span_adjudicated or adjudicated
        if span_adjudicated:
            adjudicated_spans.add(span)
    return tuple(output), adjudicated_spans


def resolve_frame_conflicts_v290(existing, recovered, adjudicated_spans):
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
