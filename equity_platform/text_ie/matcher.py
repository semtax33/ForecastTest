from __future__ import annotations

from dataclasses import dataclass
import re

from .dsl import PatternExprIR, TextRuleIR
from .model import ConceptMention, QuantityMention


@dataclass(frozen=True)
class LabeledSpan:
    label: str
    char_start: int
    char_end: int
    value: str


def _spans(
    expression: PatternExprIR,
    text: str,
    concepts: tuple[ConceptMention, ...],
    quantities: tuple[QuantityMention, ...],
) -> tuple[tuple[int, int, str], ...]:
    if expression.operator == "ANY":
        return tuple(
            sorted(
                {
                    span
                    for child in expression.children
                    for span in _spans(child, text, concepts, quantities)
                }
            )
        )
    if expression.operator == "ALL":
        groups = [_spans(child, text, concepts, quantities) for child in expression.children]
        if not groups:
            return ()
        common = set(groups[0])
        for group in groups[1:]:
            common &= set(group)
        return tuple(sorted(common))
    if expression.operator == "NOT":
        return ((0, 0, "NOT"),) if not _spans(expression.children[0], text, concepts, quantities) else ()
    if expression.operator != "TOKEN" or expression.attribute is None:
        return ()
    value = expression.value
    if expression.attribute == "concept":
        return tuple(
            (item.char_start, item.char_end, item.concept)
            for item in concepts
            if value == "*" or item.concept == value
        )
    if expression.attribute == "quantity":
        return tuple(
            (item.char_start, item.char_end, item.raw)
            for item in quantities
            if item.kind.value == value
        )
    if expression.attribute in {"lower", "lemma"} and isinstance(value, str):
        return tuple(
            (match.start(), match.end(), match.group(0))
            for match in re.finditer(
                rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])",
                text,
                flags=re.IGNORECASE,
            )
        )
    # POS/entity/shape/like_num predicates are preserved in Rule IR for a
    # spaCy-compatible backend; the dependency-free backend abstains.
    return ()


def match_sequence_pattern(
    rule: TextRuleIR,
    text: str,
    concepts: tuple[ConceptMention, ...],
    quantities: tuple[QuantityMention, ...],
) -> tuple[LabeledSpan, ...] | None:
    """Execute the bounded DSL subset without coupling rules to spaCy/HMRB."""

    if not rule.pattern:
        return ()
    cursor = 0
    matched: list[LabeledSpan] = []
    for step in rule.pattern:
        candidates = tuple(
            span
            for span in _spans(step.expression, text, concepts, quantities)
            if span[0] >= cursor
        )
        if not candidates:
            if step.optional or step.minimum == 0:
                continue
            return None
        start, end, value = min(candidates, key=lambda item: (item[0], item[1]))
        matched.append(LabeledSpan(step.label, start, end, value))
        cursor = end
    return tuple(matched)

