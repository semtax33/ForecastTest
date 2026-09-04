from __future__ import annotations

from dataclasses import dataclass

from .dsl import PatternExprIR, TextRuleIR
from .model import ConceptMention, QuantityMention


@dataclass(frozen=True)
class LabeledSpan:
    label: str
    char_start: int
    char_end: int
    value: str


def _literal_spans(text: str, literal: str) -> tuple[tuple[int, int, str], ...]:
    folded = text.casefold()
    needle = literal.casefold()
    cursor = 0
    output: list[tuple[int, int, str]] = []
    while (start := folded.find(needle, cursor)) >= 0:
        end = start + len(needle)
        left_ok = start == 0 or not folded[start - 1].isalnum()
        right_ok = end == len(folded) or not folded[end].isalnum()
        if left_ok and right_ok:
            output.append((start, end, text[start:end]))
        cursor = start + 1
    return tuple(output)


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
    if expression.attribute == "lower" and isinstance(value, str):
        return _literal_spans(text, value)
    if expression.attribute == "lemma":
        # Lemmatization is a linguistic operation. The dependency-free
        # fallback abstains instead of pretending surface text is a lemma.
        return ()
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
    candidates_by_step = tuple(
        tuple(sorted(set(_spans(step.expression, text, concepts, quantities))))
        for step in rule.pattern
    )

    def gap_tokens(left_end: int | None, right_start: int) -> int:
        if left_end is None:
            return 0
        return len(text[left_end:right_start].split())

    def search(
        step_index: int,
        cursor: int,
        previous_end: int | None,
        bound: tuple[LabeledSpan, ...],
    ) -> tuple[LabeledSpan, ...] | None:
        if step_index == len(rule.pattern):
            if "require_same_clause" in rule.operations and bound:
                literal = text[
                    min(span.char_start for span in bound) :
                    max(span.char_end for span in bound)
                ]
                if ";" in literal:
                    return None
            return bound
        step = rule.pattern[step_index]
        candidates = candidates_by_step[step_index]

        def consume(
            candidate_index: int,
            local_cursor: int,
            local_previous_end: int | None,
            selected: tuple[LabeledSpan, ...],
        ) -> tuple[LabeledSpan, ...] | None:
            count = len(selected)
            if count > 0 and count >= step.minimum:
                result = search(
                    step_index + 1,
                    local_cursor,
                    local_previous_end,
                    bound + selected,
                )
                if result is not None:
                    return result
            if count >= step.maximum:
                return None
            for index in range(candidate_index, len(candidates)):
                start, end, value = candidates[index]
                if start < local_cursor:
                    continue
                if (
                    step.max_gap_tokens is not None
                    and gap_tokens(local_previous_end, start) > step.max_gap_tokens
                ):
                    continue
                result = consume(
                    index + 1,
                    end,
                    end,
                    selected + (LabeledSpan(step.label, start, end, value),),
                )
                if result is not None:
                    return result
            if count == 0 and step.minimum == 0:
                return search(
                    step_index + 1,
                    local_cursor,
                    local_previous_end,
                    bound,
                )
            return None

        return consume(0, cursor, previous_end, ())

    return search(0, 0, None, ())
