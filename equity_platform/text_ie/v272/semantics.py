from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..dsl import TextRuleIR, compile_text_rule_file
from ..model import (
    KPIFrame,
    PeriodSemantics,
    Polarity,
    QuantityKind,
    QuantityMention,
    SemanticFrame,
)
from ..spacy_backend import SpacySemanticBackend
from ..v24.model import RecallCandidate
from ..v271.semantics import (
    augment_candidates_v271,
    recover_v271_frames,
    resolve_frame_conflicts_v271,
    semantic_concepts_v271,
    semantic_quantities_v271,
)


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v272_semantic_laws.arc"
V272_RULES = compile_text_rule_file(RULE_PATH)


@lru_cache(maxsize=1)
def semantic_backend_v272() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v272(text: str, backend: SpacySemanticBackend | None = None):
    return semantic_concepts_v271(text, backend or semantic_backend_v272())


def _number(token: object) -> float | None:
    try:
        return float(str(token.text).replace(",", ""))
    except ValueError:
        return None


def _repaired_percent_quantities(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    """Recover abbreviated ranges and split ``percent`` typography via tokens."""

    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    output: list[QuantityMention] = []
    for index, token in enumerate(tokens):
        value = _number(token) if token.like_num else None
        if value is None:
            continue
        # Filing typography often writes ``48 - 49%``.  The right unit scopes
        # both endpoints, so materialize the left endpoint as a percent.
        if (
            index + 3 < len(tokens)
            and tokens[index + 1].text in {"-", "–", "—"}
            and tokens[index + 2].like_num
            and tokens[index + 3].text == "%"
        ):
            output.append(
                QuantityMention(
                    kind=QuantityKind.PERCENT,
                    value=value,
                    unit="PERCENT",
                    raw=text[int(token.idx) : int(token.idx + len(token.text))],
                    char_start=int(token.idx),
                    char_end=int(token.idx + len(token.text)),
                )
            )
        # HTML/text extraction can split ``percent`` into ``perce nt`` or
        # ``per cent``.  Join lexical tokens rather than matching raw text.
        if (
            index + 2 < len(tokens)
            and tokens[index + 1].is_alpha
            and tokens[index + 2].is_alpha
            and (tokens[index + 1].lower_ + tokens[index + 2].lower_) == "percent"
        ):
            end = int(tokens[index + 2].idx + len(tokens[index + 2].text))
            output.append(
                QuantityMention(
                    kind=QuantityKind.PERCENT,
                    value=value,
                    unit="PERCENT",
                    raw=text[int(token.idx) : end],
                    char_start=int(token.idx),
                    char_end=end,
                )
            )
    return tuple(output)


def semantic_quantities_v272(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    output = list(semantic_quantities_v271(text, backend))
    seen = {(item.char_start, item.char_end, item.kind) for item in output}
    for item in _repaired_percent_quantities(text, backend):
        signature = (item.char_start, item.char_end, item.kind)
        if signature not in seen:
            output.append(item)
            seen.add(signature)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end, item.kind)))


def augment_candidates_v272(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    return augment_candidates_v271(
        document,
        candidates,
        backend or semantic_backend_v272(),
    )


def _role_quantity(
    frame: KPIFrame,
    quantities: tuple[QuantityMention, ...],
    label: str,
) -> QuantityMention | None:
    roles = dict(frame.context_trace.get("semantic_roles", {})).get(label, ())
    if len(roles) != 1:
        return None
    role = roles[0]
    return next(
        (
            item
            for item in quantities
            if int(role["start"]) <= item.char_start
            and item.char_end <= int(role["end"])
        ),
        None,
    )


def _change_by(frame: KPIFrame, quantity: QuantityMention, pair_index: int) -> KPIFrame:
    return replace(
        frame,
        frame=SemanticFrame.CHANGE_BY,
        value=quantity.value,
        unit=quantity.unit,
        change=None,
        change_unit=None,
        comparator="PRIOR_PERIOD",
        context_trace={**frame.context_trace, "semantic_pair_index": pair_index},
    )


def _postprocess_rule_frames(
    frame: KPIFrame,
    quantities: tuple[QuantityMention, ...],
) -> tuple[KPIFrame, ...]:
    if frame.rule_id == "v272.debt_reduced_approximately":
        roles = dict(frame.context_trace.get("semantic_roles", {})).get("trigger", ())
        cue = roles[0] if roles else None
        return (
            replace(
                frame,
                polarity=Polarity(
                    positive=False,
                    cue=str(cue["value"]) if cue else "reduce",
                    cue_start=int(cue["start"]) if cue else None,
                    cue_end=int(cue["end"]) if cue else None,
                ),
            ),
        )
    if frame.rule_id == "v272.revenue_money_percent_change":
        amount = _role_quantity(frame, quantities, "amount_change")
        return (frame,) if amount is None else (frame, _change_by(frame, amount, 0))
    if frame.rule_id != "v272.operating_income_respectively":
        return (frame,)
    first_delta = _role_quantity(frame, quantities, "first_delta")
    second_value = _role_quantity(frame, quantities, "second_value")
    second_delta = _role_quantity(frame, quantities, "second_delta")
    second_percent = _role_quantity(frame, quantities, "second_percent")
    if None in (first_delta, second_value, second_delta, second_percent):
        return ()
    second = replace(
        frame,
        value=second_value.value,
        unit=second_value.unit,
        change=second_percent.value,
        change_unit=second_percent.unit,
        context_trace={**frame.context_trace, "semantic_pair_index": 1},
    )
    return (
        replace(frame, context_trace={**frame.context_trace, "semantic_pair_index": 0}),
        _change_by(frame, first_delta, 0),
        second,
        _change_by(second, second_delta, 1),
    )


def recover_v272_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V272_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v272()
    # Reuse the generic DSL executor while replacing only the versioned rule
    # program and the repaired quantity stream.
    from ..v271 import semantics as v271_semantics

    original = v271_semantics.semantic_quantities_v271
    try:
        v271_semantics.semantic_quantities_v271 = semantic_quantities_v272
        raw = recover_v271_frames(
            document,
            candidates,
            allowed_spans,
            rules=rules,
            backend=selected_backend,
        )
    finally:
        v271_semantics.semantic_quantities_v271 = original

    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for frame in raw:
        block = next(
            (
                item
                for (start, end), item in blocks.items()
                if start <= frame.source_span.char_start and frame.source_span.char_end <= end
            ),
            None,
        )
        quantities = (
            semantic_quantities_v272(block.text, selected_backend) if block else ()
        )
        output.extend(_postprocess_rule_frames(frame, quantities))
    return tuple(output)


def _base(concept: str) -> str:
    result = concept.removeprefix("PRIOR_YEAR_")
    changed = True
    while changed:
        prior = result
        result = result.removesuffix("_GUIDANCE").removesuffix("_CHANGE")
        changed = result != prior
    return result


def _same_number(left: float, right: float) -> bool:
    return abs(left - right) <= max(1e-9, abs(right) * 1e-9)


_FOREIGN_OWNER_PHRASES = (
    "eps",
    "earnings per share",
    "net income per share",
    "cost",
    "costs",
    "expense",
    "expenses",
)


def _foreign_metric_owns_value(
    frame: KPIFrame,
    backend: SpacySemanticBackend,
) -> bool:
    if _base(frame.concept) != "REVENUE" or frame.value is None:
        return False
    text = frame.source_span.literal
    quantities = semantic_quantities_v272(text, backend)
    positions = [
        item.char_start for item in quantities if _same_number(item.value, frame.value)
    ]
    if not positions:
        return False
    own = [
        item.char_end
        for item in semantic_concepts_v272(text, backend)
        if item.concept == "REVENUE"
    ]
    foreign = [
        end
        for _, _, end in backend.phrase_mentions(text, _FOREIGN_OWNER_PHRASES)
    ]
    for position in positions:
        nearest_own = max((end for end in own if end <= position), default=-1)
        nearest_foreign = max((end for end in foreign if end <= position), default=-1)
        if nearest_foreign > nearest_own:
            return True
    return False


def _guidance_context(
    document: CanonicalDocument,
    frame: KPIFrame,
    backend: SpacySemanticBackend,
) -> bool:
    literal = frame.source_span.literal
    literal_tokens = tuple(token for token in backend.parse(literal) if not token.is_space)
    quantity_positions = [
        item.char_start
        for item in semantic_quantities_v272(literal, backend)
        if frame.value is not None and _same_number(item.value, frame.value)
    ]
    fact_position = min(quantity_positions, default=len(literal))
    if any(
        (
            token.lemma_.casefold() == "expect"
            or token.lower_ in {"guidance", "outlook"}
        )
        and int(token.idx) < fact_position
        for token in literal_tokens
    ):
        return True
    if sum(token.is_alpha for token in literal_tokens) > 20:
        return False
    start = frame.source_span.char_start
    preceding = document.text[max(0, start - 240) : start]
    preceding_tokens = tuple(token for token in backend.parse(preceding) if not token.is_space)
    return any(token.lemma_.casefold() == "expect" for token in preceding_tokens) and bool(
        backend.phrase_mentions(preceding, ("financial outlook", "business outlook"))
    )


def _promote_guidance(
    document: CanonicalDocument,
    frame: KPIFrame,
    backend: SpacySemanticBackend,
) -> KPIFrame:
    if frame.concept.startswith("PRIOR_YEAR_") or frame.concept.endswith("_GUIDANCE"):
        return frame
    if _base(frame.concept) not in {"REVENUE", "OPERATING_MARGIN"}:
        return frame
    if not _guidance_context(document, frame, backend):
        return frame
    return replace(
        frame,
        concept=frame.concept + "_GUIDANCE",
        period_semantics=PeriodSemantics.FORECAST,
        context_trace={**frame.context_trace, "guidance_context": "SPACY_NEARBY_OUTLOOK"},
    )


def resolve_frame_conflicts_v272(
    document: CanonicalDocument,
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v272()
    merged = resolve_frame_conflicts_v271(existing, recovered, selected_backend)
    promoted = tuple(
        _promote_guidance(document, frame, selected_backend)
        for frame in merged
        if not _foreign_metric_owns_value(frame, selected_backend)
    )
    unique: dict[tuple[object, ...], KPIFrame] = {}
    for frame in promoted:
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
        unique.setdefault(signature, frame)
    return tuple(unique.values())
