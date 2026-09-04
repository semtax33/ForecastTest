from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from .dsl import PatternExprIR, TextRuleIR
from .matcher import LabeledSpan
from .model import ConceptMention, QuantityMention


class SemanticMatcherBackend(Protocol):
    name: str
    model: str
    last_match_trace: tuple[str, ...]

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
        self.last_match_trace: tuple[str, ...] = ()
        self._phrase_matchers: dict[str, object] = {}
        self._phrase_set_matchers: dict[tuple[str, ...], object] = {}
        self._token_matchers: dict[tuple[tuple[tuple[str, object], ...], ...], object] = {}

    @lru_cache(maxsize=1024)
    def _parse(self, text: str) -> object:
        return self._nlp(text)

    def parse(self, text: str) -> object:
        """Return the cached spaCy document used by all semantic consumers."""

        return self._parse(text)

    def phrase_mentions(
        self,
        text: str,
        phrases: tuple[str, ...],
    ) -> tuple[tuple[str, int, int], ...]:
        """Locate an issuer-neutral phrase vocabulary with PhraseMatcher.

        This is the shared replacement for modules compiling one regular
        expression per alias or table cue.
        """

        from spacy.matcher import PhraseMatcher

        normalized = tuple(dict.fromkeys(phrase.casefold() for phrase in phrases))
        matcher = self._phrase_set_matchers.get(normalized)
        if matcher is None:
            matcher = PhraseMatcher(self._nlp.vocab, attr="LOWER")
            for index, phrase in enumerate(normalized):
                matcher.add(f"PHRASE_{index}", [self._nlp.make_doc(phrase)])
            self._phrase_set_matchers[normalized] = matcher
        doc = self._parse(text)
        output = []
        for match_id, start, end in matcher(doc):
            span = doc[start:end]
            output.append(
                (
                    str(span.text),
                    int(span.start_char),
                    int(span.end_char),
                )
            )
        return tuple(sorted(output, key=lambda item: (item[1], item[2], item[0])))

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

            matcher = self._phrase_matchers.get(expression.value)
            if matcher is None:
                matcher = PhraseMatcher(self._nlp.vocab, attr="LOWER")
                matcher.add("DSL_PHRASE", [self._nlp.make_doc(expression.value)])
                self._phrase_matchers[expression.value] = matcher
            return tuple(
                (int(doc[start].idx), int(doc[end - 1].idx + len(doc[end - 1].text)), expression.value)
                for _, start, end in matcher(doc)
            )
        token_patterns = self._matcher_patterns(expression)
        if token_patterns:
            from spacy.matcher import Matcher

            key = tuple(tuple(sorted(pattern.items())) for pattern in token_patterns)
            matcher = self._token_matchers.get(key)
            if matcher is None:
                matcher = Matcher(self._nlp.vocab)
                matcher.add("DSL_TOKEN", [[pattern] for pattern in token_patterns])
                self._token_matchers[key] = matcher
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
        self.last_match_trace = ()
        if not rule.pattern:
            return ()
        doc = self._parse(text)
        candidates_by_step = tuple(
            tuple(
                sorted(
                    set(self._spans(step.expression, doc, concepts, quantities)),
                    key=lambda item: (item[0], item[1], item[2]),
                )
            )
            for step in rule.pattern
        )

        def gap_tokens(left_end: int | None, right_start: int) -> int:
            if left_end is None:
                return 0
            return sum(
                1
                for token in doc
                if not token.is_space and left_end <= token.idx < right_start
            )

        require_same_clause = "require_same_clause" in rule.operations

        def same_clause(spans: tuple[LabeledSpan, ...]) -> bool:
            if not require_same_clause or len(spans) < 2:
                return True
            start = min(span.char_start for span in spans)
            end = max(span.char_end for span in spans)
            return not any(
                (token.text == ";")
                or (bool(token.is_sent_start) and token.idx > start)
                for token in doc
                if start < token.idx < end
            )

        def finish(spans: tuple[LabeledSpan, ...]) -> tuple[LabeledSpan, ...] | None:
            if not same_clause(spans):
                return None
            trace = ["SPACY_MATCHER"]
            dependency_required = (
                "require_dependency_path" in rule.operations
                or any(backend.value == "DEPENDENCY" for backend in rule.backends)
            )
            if dependency_required:
                if not self._dependency_match(doc, spans):
                    return None
                trace.append("SPACY_DEPENDENCY_MATCHER")
            self.last_match_trace = tuple(trace)
            return spans

        def search(
            step_index: int,
            cursor: int,
            previous_end: int | None,
            bound: tuple[LabeledSpan, ...],
        ) -> tuple[LabeledSpan, ...] | None:
            if step_index == len(rule.pattern):
                return finish(bound)
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
                    matched = search(
                        step_index + 1,
                        local_cursor,
                        local_previous_end,
                        bound + selected,
                    )
                    if matched is not None:
                        return matched
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
                    span = LabeledSpan(step.label, start, end, value)
                    matched = consume(index + 1, end, end, selected + (span,))
                    if matched is not None:
                        return matched
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

    @staticmethod
    def _dependency_roles(
        spans: tuple[LabeledSpan, ...],
    ) -> tuple[LabeledSpan, LabeledSpan] | None:
        by_label: dict[str, LabeledSpan] = {}
        for span in spans:
            by_label.setdefault(span.label, span)
        for left, right in (
            ("cause", "effect"),
            ("metric", "value"),
            ("metric", "change"),
        ):
            if left in by_label and right in by_label:
                return by_label[left], by_label[right]
        semantic = tuple(
            span
            for span in spans
            if span.label not in {"trigger", "relation", "qualifier"}
        )
        if len(semantic) >= 2:
            return semantic[0], semantic[-1]
        return None

    def _dependency_match(
        self,
        doc: object,
        spans: tuple[LabeledSpan, ...],
    ) -> bool:
        roles = self._dependency_roles(spans)
        if roles is None:
            return False
        left_span, right_span = roles
        left_doc_span = doc.char_span(
            left_span.char_start,
            left_span.char_end,
            alignment_mode="expand",
        )
        right_doc_span = doc.char_span(
            right_span.char_start,
            right_span.char_end,
            alignment_mode="expand",
        )
        if left_doc_span is None or right_doc_span is None:
            return False
        left, right = left_doc_span.root, right_doc_span.root
        left_chain = (left, *tuple(left.ancestors))
        right_chain = (right, *tuple(right.ancestors))
        common = set(left_chain) & set(right_chain)
        if not common:
            return False
        bridge = min(
            common,
            key=lambda token: left_chain.index(token) + right_chain.index(token),
        )
        if left_chain.index(bridge) + right_chain.index(bridge) > 8:
            return False

        from spacy.matcher import DependencyMatcher

        pattern_specs: list[
            tuple[str, list[dict[str, object]], tuple[int, ...]]
        ] = []
        if left in right_chain[1:]:
            pattern_specs.append(
                (
                    "DSL_LEFT_ANCESTOR",
                    [
                    {"RIGHT_ID": "left", "RIGHT_ATTRS": {"ORTH": left.text}},
                    {
                        "LEFT_ID": "left",
                        "REL_OP": ">>",
                        "RIGHT_ID": "right",
                        "RIGHT_ATTRS": {"ORTH": right.text},
                    },
                    ],
                    (left.i, right.i),
                )
            )
        if right in left_chain[1:]:
            pattern_specs.append(
                (
                    "DSL_RIGHT_ANCESTOR",
                    [
                    {"RIGHT_ID": "right", "RIGHT_ATTRS": {"ORTH": right.text}},
                    {
                        "LEFT_ID": "right",
                        "REL_OP": ">>",
                        "RIGHT_ID": "left",
                        "RIGHT_ATTRS": {"ORTH": left.text},
                    },
                    ],
                    (right.i, left.i),
                )
            )
        if bridge is not left and bridge is not right:
            pattern_specs.append(
                (
                    "DSL_SHARED_ANCESTOR",
                    [
                    {"RIGHT_ID": "bridge", "RIGHT_ATTRS": {"ORTH": bridge.text}},
                    {
                        "LEFT_ID": "bridge",
                        "REL_OP": ">>",
                        "RIGHT_ID": "left",
                        "RIGHT_ATTRS": {"ORTH": left.text},
                    },
                    {
                        "LEFT_ID": "bridge",
                        "REL_OP": ">>",
                        "RIGHT_ID": "right",
                        "RIGHT_ATTRS": {"ORTH": right.text},
                    },
                    ],
                    (bridge.i, left.i, right.i),
                )
            )
        if not pattern_specs:
            return False
        matcher = DependencyMatcher(self._nlp.vocab, validate=True)
        expected: dict[str, tuple[int, ...]] = {}
        for name, pattern, token_ids in pattern_specs:
            matcher.add(name, [pattern])
            expected[name] = token_ids
        return any(
            tuple(token_ids) == expected[self._nlp.vocab.strings[match_id]]
            for match_id, token_ids in matcher(doc)
        )

    def dependency_relation(
        self,
        text: str,
        concepts: tuple[ConceptMention, ...],
    ) -> bool:
        if len(concepts) < 2:
            return False
        doc = self._parse(text)
        first, second = concepts[0], concepts[-1]
        return self._dependency_match(
            doc,
            (
                LabeledSpan("cause", first.char_start, first.char_end, first.concept),
                LabeledSpan("effect", second.char_start, second.char_end, second.concept),
            ),
        )


@lru_cache(maxsize=1)
def default_spacy_backend() -> SpacySemanticBackend | None:
    try:
        return SpacySemanticBackend()
    except (ImportError, OSError):
        return None
