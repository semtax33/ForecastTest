from __future__ import annotations

from dataclasses import replace

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..dsl import compile_text_rule_file
from ..model import (
    KPIFrame,
    PeriodSemantics,
    Polarity,
    QuantityKind,
    QuantityMention,
    SemanticFrame,
)
from ..v24.model import RecallCandidate
from ..v276.semantics import (
    recover_v276_frames,
    resolve_frame_conflicts_v276,
    semantic_backend_v276,
    semantic_concepts_v276,
    semantic_quantities_v276,
)


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v277_semantic_laws.arc"
V277_RULES = compile_text_rule_file(RULE_PATH)


def _base(concept: str) -> str:
    result = concept.removeprefix("PRIOR_YEAR_")
    while True:
        prior = result
        result = result.removesuffix("_GUIDANCE").removesuffix("_CHANGE")
        if result == prior:
            return result


def _parallel_segment_guidance(template: KPIFrame) -> tuple[KPIFrame, ...]:
    text = template.source_span.literal
    backend = semantic_backend_v276()
    concepts = tuple(
        mention
        for mention in semantic_concepts_v276(text, backend)
        if _base(mention.concept) == "REVENUE"
    )
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    parenthesized_percents = []
    for index, token in enumerate(tokens):
        if index > 0 and tokens[index - 1].text == "(" and token.text.endswith(")%"):
            try:
                value = float(token.text[:-2].replace(",", ""))
            except ValueError:
                pass
            else:
                parenthesized_percents.append(
                    QuantityMention(
                        kind=QuantityKind.PERCENT,
                        value=value,
                        unit="PERCENT",
                        raw=text[tokens[index - 1].idx : token.idx + len(token.text)],
                        char_start=int(token.idx),
                        char_end=int(token.idx + len(token.text)),
                    )
                )
                continue
        if (
            not token.like_num
            or index == 0
            or index + 2 >= len(tokens)
            or tokens[index - 1].text != "("
            or tokens[index + 1].text != ")"
            or tokens[index + 2].text != "%"
        ):
            continue
        parenthesized_percents.append(
            QuantityMention(
                kind=QuantityKind.PERCENT,
                value=float(token.text.replace(",", "")),
                unit="PERCENT",
                raw=text[tokens[index - 1].idx : tokens[index + 2].idx + 1],
                char_start=int(token.idx),
                char_end=int(tokens[index + 2].idx + 1),
            )
        )
    quantities = tuple(
        sorted(
            (*semantic_quantities_v276(text, backend), *parenthesized_percents),
            key=lambda item: (item.char_start, item.char_end),
        )
    )
    output: list[KPIFrame] = []
    for index, mention in enumerate(concepts):
        boundary = concepts[index + 1].char_start if index + 1 < len(concepts) else len(text)
        money = tuple(
            item
            for item in quantities
            if item.kind.value == "MONEY"
            and mention.char_end <= item.char_start < boundary
        )
        if len(money) < 2:
            continue
        low, high = money[:2]
        output.append(
            replace(
                template,
                concept="REVENUE_GUIDANCE",
                frame=SemanticFrame.RANGE_GUIDANCE,
                value=(low.value + high.value) / 2.0,
                unit=low.unit,
                change=None,
                change_unit=None,
                lower_value=low.value,
                upper_value=high.value,
                period_semantics=PeriodSemantics.FORECAST,
            )
        )
    folded = text.casefold()
    if "reflecting midpoint growth rates" not in folded or "respectively" not in folded:
        return tuple(output)
    growth_start = folded.index("reflecting midpoint growth rates")
    percents = tuple(
        item
        for item in quantities
        if item.kind.value == "PERCENT" and item.char_start >= growth_start
    )
    for percent in percents[: len(output)]:
        preceding = tuple(
            token
            for token in tokens
            if int(token.idx + len(token.text)) <= percent.char_start
        )
        negative = bool(preceding and preceding[-1].text == "(")
        output.append(
            replace(
                template,
                concept="REVENUE_GUIDANCE",
                frame=SemanticFrame.CHANGE_BY,
                value=percent.value,
                unit=percent.unit,
                change=None,
                change_unit=None,
                lower_value=None,
                upper_value=None,
                comparator="PRIOR_PERIOD",
                polarity=Polarity(not negative, "parenthesized" if negative else None, None, None),
                period_semantics=PeriodSemantics.FORECAST,
            )
        )
    return tuple(output)


def _nearest_trend_polarity(frame: KPIFrame) -> KPIFrame:
    if frame.frame.value != "CHANGE_BY" or frame.value is None:
        return frame
    backend = semantic_backend_v276()
    quantities = tuple(
        quantity
        for quantity in semantic_quantities_v276(frame.source_span.literal, backend)
        if quantity.kind.value in {"PERCENT", "BASIS_POINTS"}
        and abs(quantity.value - frame.value) <= max(1e-9, abs(frame.value) * 1e-9)
    )
    if len(quantities) != 1:
        return frame
    quantity = quantities[0]
    trend_words = {
        "up": True,
        "increase": True,
        "rise": True,
        "improve": True,
        "tailwind": True,
        "positive": True,
        "down": False,
        "decrease": False,
        "decline": False,
        "lower": False,
        "low": False,
    }
    nearby = tuple(
        token
        for token in backend.parse(frame.source_span.literal)
        if min(
            abs(int(token.idx) - quantity.char_end),
            abs(int(token.idx + len(token.text)) - quantity.char_start),
        )
        <= 24
        and (token.lower_ in trend_words or token.lemma_.casefold() in trend_words)
    )
    if not nearby:
        return frame
    trigger = min(
        nearby,
        key=lambda token: min(
            abs(int(token.idx) - quantity.char_end),
            abs(int(token.idx + len(token.text)) - quantity.char_start),
        ),
    )
    key = trigger.lower_ if trigger.lower_ in trend_words else trigger.lemma_.casefold()
    return replace(frame, polarity=Polarity(trend_words[key], trigger.text, None, None))


def _level_change_distance(frame: KPIFrame) -> int | None:
    if frame.value is None or frame.change is None:
        return None
    backend = semantic_backend_v276()
    quantities = semantic_quantities_v276(frame.source_span.literal, backend)
    levels = tuple(
        item
        for item in quantities
        if item.kind.value == "PERCENT"
        and abs(item.value - frame.value) <= max(1e-9, abs(frame.value) * 1e-9)
    )
    changes = tuple(
        item
        for item in quantities
        if item.kind.value == "BASIS_POINTS"
        and abs(item.value - frame.change) <= max(1e-9, abs(frame.change) * 1e-9)
    )
    if not levels or not changes:
        return None
    return min(
        abs(change.char_start - level.char_end)
        for level in levels
        for change in changes
    )


def _is_prior_comparison_level(frame: KPIFrame) -> bool:
    if frame.frame.value != "ABSOLUTE_VALUE" or frame.value is None:
        return False
    backend = semantic_backend_v276()
    quantities = tuple(
        item
        for item in semantic_quantities_v276(frame.source_span.literal, backend)
        if item.kind.value == "PERCENT"
    )
    matches = tuple(
        item
        for item in quantities
        if abs(item.value - frame.value) <= max(1e-9, abs(frame.value) * 1e-9)
    )
    compare_tokens = tuple(
        token
        for token in backend.parse(frame.source_span.literal)
        if token.lemma_.casefold() == "compare"
    )
    return any(
        compare.idx < match.char_start
        and match.char_start - int(compare.idx + len(compare.text)) <= 24
        and any(item.char_end <= compare.idx for item in quantities)
        for match in matches
        for compare in compare_tokens
    )


def _revenue_guidance_ownership_error(frame: KPIFrame) -> bool:
    if _base(frame.concept) != "REVENUE" or "GUIDANCE" not in frame.concept:
        return False
    backend = semantic_backend_v276()
    text = frame.source_span.literal
    revenue_positions = tuple(
        mention.char_start
        for mention in semantic_concepts_v276(text, backend)
        if _base(mention.concept) == "REVENUE"
    )
    protected_positions = tuple(
        start
        for _, start, _ in backend.phrase_mentions(
            text,
            ("net income per diluted share", "share repurchases"),
        )
    )
    if not revenue_positions or not protected_positions:
        return False
    expected_values = {
        value
        for value in (frame.value, frame.lower_value, frame.upper_value)
        if value is not None
    }
    matched = tuple(
        quantity
        for quantity in semantic_quantities_v276(text, backend)
        if any(
            abs(quantity.value - value) <= max(1e-9, abs(value) * 1e-9)
            for value in expected_values
        )
    )
    for quantity in matched:
        preceding_revenue = tuple(pos for pos in revenue_positions if pos < quantity.char_start)
        preceding_protected = tuple(pos for pos in protected_positions if pos < quantity.char_start)
        if preceding_protected and (
            not preceding_revenue or max(preceding_protected) > max(preceding_revenue)
        ):
            return True
    return False


def recover_v277_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
) -> tuple[KPIFrame, ...]:
    raw_frames = recover_v276_frames(document, candidates, allowed_spans, rules=V277_RULES)
    frames = tuple(
        expanded
        for frame in raw_frames
        for expanded in (
            _parallel_segment_guidance(frame)
            if frame.rule_id == "v277.segment_property_revenue_range"
            else (frame,)
        )
    )
    backend = semantic_backend_v276()
    output = []
    for frame in frames:
        if frame.rule_id == "v277.operating_income_percent_lower" and any(
            token.lower_ == "lower" or token.lemma_.casefold() == "low"
            for token in backend.parse(frame.source_span.literal)
        ):
            frame = replace(frame, polarity=Polarity(False, "lower", None, None))
        output.append(frame)
    return tuple(output)


def resolve_frame_conflicts_v277(
    document: CanonicalDocument,
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
) -> tuple[KPIFrame, ...]:
    merged = resolve_frame_conflicts_v276(document, existing, recovered)
    backend = semantic_backend_v276()
    output = []
    for frame in merged:
        if _revenue_guidance_ownership_error(frame):
            continue
        if (
            _base(frame.concept) in {"GROSS_MARGIN", "OPERATING_MARGIN"}
            and _is_prior_comparison_level(frame)
        ):
            continue
        if (
            _base(frame.concept) == "GROSS_MARGIN"
            and frame.frame.value == "CHANGE_TO"
            and frame.change is not None
        ):
            peers = tuple(
                other
                for other in merged
                if _base(other.concept) == "GROSS_MARGIN"
                and other.frame == frame.frame
                and other.value == frame.value
                and other.source.sha256 == frame.source.sha256
                and other.source_span.char_start == frame.source_span.char_start
                and _level_change_distance(other) is not None
            )
            own_distance = _level_change_distance(frame)
            if peers and own_distance is not None and own_distance > min(
                _level_change_distance(other) for other in peers
            ):
                continue
        if frame.rule_id == "v277.operating_income_percent_lower" and any(
            token.lower_ == "lower" or token.lemma_.casefold() == "low"
            for token in backend.parse(frame.source_span.literal)
        ):
            frame = replace(frame, polarity=Polarity(False, "lower", None, None))
        if _base(frame.concept) in {"REVENUE", "GROSS_MARGIN", "OPERATING_INCOME"}:
            frame = _nearest_trend_polarity(frame)
        output.append(frame)
    return tuple(output)
