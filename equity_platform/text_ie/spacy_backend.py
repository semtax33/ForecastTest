from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from .dsl import PatternExprIR, TextRuleIR
from .matcher import LabeledSpan
from .model import ConceptMention, QuantityMention


class SemanticMatcherBackend(Protocol):
    name: str
    model: str

    def match_pattern(
        self,
        rule: TextRuleIR,
        text: str,
        concepts: tuple[ConceptMention, ...],
        quantities: tuple[QuantityMention, ...],
    ) -> tuple[LabeledSpan, ...] | None: ...

    def dependency_relation(
        self,
        text: str,
        concepts: tuple[ConceptMention, ...],
    ) -> bool: ...


class SpacySemanticBackend:
    """spaCy execution backend kept behind the backend-neutral TextRuleIR."""

    name = "SPACY"

    def __init__(self, model: str = "en_core_web_sm") -> None:
        import spacy

        self.model = model
        self._nlp = spacy.load(model)

    @staticmethod
    def _token_matches(expression: PatternExprIR, token: object) -> bool:
        if expression.operator == "ANY":
            return any(SpacySemanticBackend._token_matches(child, token) for child in expression.children)
        if expression.operator == "ALL":
            return all(SpacySemanticBackend._token_matches(child, token) for child in expression.children)
        if expression.operator == "NOT":
            return not SpacySemanticBackend._token_matches(expression.children[0], token)
        if expression.operator != "TOKEN":
            return False
        attribute, value = expression.attribute, expression.value
        if attribute == "lower":
            return str(getattr(token, "lower_", "")) == str(value).casefold()
        if attribute == "lemma":
            return str(getattr(token, "lemma_", "")).casefold() == str(value).casefold()
        if attribute == "pos":
            return str(getattr(token, "pos_", "")) == str(value)
        if attribute == "ent_type":
            return str(getattr(token, "ent_type_", "")) == str(value)
        if attribute == "shape":
            return str(getattr(token, "shape_", "")) == str(value)
        if attribute == "like_num":
            return bool(getattr(token, "like_num", False)) is bool(value)
        return False

    def _spans(
        self,
        expression: PatternExprIR,
        doc: object,
        concepts: tuple[ConceptMention, ...],
        quantities: tuple[QuantityMention, ...],
    ) -> tuple[tuple[int, int, str], ...]:
        if expression.operator == "TOKEN" and expression.attribute == "concept":
            return tuple(
                (item.char_start, item.char_end, item.concept)
                for item in concepts
                if expression.value == "*" or item.concept == expression.value
            )
        if expression.operator == "TOKEN" and expression.attribute == "quantity":
            return tuple(
                (item.char_start, item.char_end, item.raw)
                for item in quantities
                if item.kind.value == expression.value
            )
        if expression.operator == "ANY":
            return tuple(sorted({span for child in expression.children for span in self._spans(child, doc, concepts, quantities)}))
        if (
            expression.operator == "TOKEN"
            and expression.attribute == "lower"
            and isinstance(expression.value, str)
            and " " in expression.value
        ):
            from spacy.matcher import PhraseMatcher

            matcher = PhraseMatcher(self._nlp.vocab, attr="LOWER")
            matcher.add("DSL_PHRASE", [self._nlp.make_doc(expression.value)])
            return tuple(
                (int(doc[start].idx), int(doc[end - 1].idx + len(doc[end - 1].text)), expression.value)
                for _, start, end in matcher(doc)
            )
        token_patterns = self._matcher_patterns(expression)
        if token_patterns:
            from spacy.matcher import Matcher

            matcher = Matcher(self._nlp.vocab)
            matcher.add("DSL_TOKEN", [[pattern] for pattern in token_patterns])
            return tuple(
                (int(doc[start].idx), int(doc[end - 1].idx + len(doc[end - 1].text)), str(doc[start:end]))
                for _, start, end in matcher(doc)
            )
        return tuple(
            (int(token.idx), int(token.idx + len(token.text)), str(token.text))
            for token in doc
            if self._token_matches(expression, token)
        )

    @staticmethod
    def _matcher_patterns(expression: PatternExprIR) -> tuple[dict[str, object], ...]:
        attributes = {
            "lower": "LOWER",
            "lemma": "LEMMA",
            "pos": "POS",
            "ent_type": "ENT_TYPE",
            "shape": "SHAPE",
            "like_num": "LIKE_NUM",
        }
        if expression.operator == "TOKEN" and expression.attribute in attributes:
            return ({attributes[str(expression.attribute)]: expression.value},)
        if expression.operator == "ANY":
            return tuple(
                pattern
                for child in expression.children
                for pattern in SpacySemanticBackend._matcher_patterns(child)
            )
        if expression.operator == "ALL":
            merged: dict[str, object] = {}
            for child in expression.children:
                patterns = SpacySemanticBackend._matcher_patterns(child)
                if len(patterns) != 1:
                    return ()
                merged.update(patterns[0])
            return (merged,)
        return ()

    def match_pattern(
        self,
        rule: TextRuleIR,
        text: str,
        concepts: tuple[ConceptMention, ...],
        quantities: tuple[QuantityMention, ...],
    ) -> tuple[LabeledSpan, ...] | None:
        if not rule.pattern:
            return ()
        doc = self._nlp(text)
        cursor = 0
        result: list[LabeledSpan] = []
        for step in rule.pattern:
            candidates = tuple(
                span
                for span in self._spans(step.expression, doc, concepts, quantities)
                if span[0] >= cursor
            )
            if not candidates:
                if step.optional or step.minimum == 0:
                    continue
                return None
            start, end, value = min(candidates, key=lambda item: (item[0], item[1]))
            result.append(LabeledSpan(step.label, start, end, value))
            cursor = end
        return tuple(result)

    def dependency_relation(
        self,
        text: str,
        concepts: tuple[ConceptMention, ...],
    ) -> bool:
        if len(concepts) < 2:
            return False
        doc = self._nlp(text)
        tokens = []
        for mention in (concepts[0], concepts[-1]):
            span = doc.char_span(mention.char_start, mention.char_end, alignment_mode="expand")
            if span is None:
                return False
            tokens.append(span.root)
        first, second = tokens
        first_ancestors = {first, *first.ancestors}
        second_ancestors = {second, *second.ancestors}
        common = first_ancestors & second_ancestors
        if not common:
            return False
        distance = min(
            list(first.ancestors).index(node) + list(second.ancestors).index(node) + 2
            if node is not first and node is not second
            else 1
            for node in common
        )
        return distance <= 8


@lru_cache(maxsize=1)
def default_spacy_backend() -> SpacySemanticBackend | None:
    try:
        return SpacySemanticBackend()
    except (ImportError, OSError):
        return None
