from __future__ import annotations

from functools import lru_cache
from dataclasses import dataclass

from equity_platform.paths import PROJECT_ROOT

from ..dsl import compile_text_rule_file
from ..model import ConceptMention, QuantityKind, QuantityMention
from ..v290.semantics import semantic_backend_v290


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v292_semantic_context.arc"
V292_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V292_RULES}


@lru_cache(maxsize=1)
def semantic_backend_v292():
    return semantic_backend_v290()


def is_share_transaction_event_scope(text, concepts, quantities) -> bool:
    """Return whether SHARES is an event object, not an outstanding-state fact."""

    rule = _RULE_BY_ID["v292.share_transaction_event_scope"]
    return semantic_backend_v292().match_pattern(rule, text, concepts, quantities) is not None


@dataclass(frozen=True)
class ActivityPredicateArgument:
    concept: ConceptMention
    quantity: QuantityMention


_SCALE = {"thousand": 1_000.0, "million": 1_000_000.0, "billion": 1_000_000_000.0}
_ARGUMENT_DEPS = {"dobj", "obj", "attr", "oprd", "nsubjpass"}


def _direct_argument_of(number_token, predicate_token) -> bool:
    current = number_token
    while current.i != predicate_token.i and current.head.i != current.i:
        if current.dep_ in _ARGUMENT_DEPS and current.head.i == predicate_token.i:
            return True
        current = current.head
    return False


def _count_quantity(number_token, doc) -> QuantityMention | None:
    try:
        value = float(number_token.text.replace(",", ""))
    except ValueError:
        return None
    if 1900 <= value <= 2100:
        return None
    end = int(number_token.idx + len(number_token.text))
    scale = 1.0
    following = doc[number_token.i + 1] if number_token.i + 1 < len(doc) else None
    if following is not None and following.lemma_.casefold() in _SCALE:
        scale = _SCALE[following.lemma_.casefold()]
        end = int(following.idx + len(following.text))
    return QuantityMention(
        QuantityKind.COUNT,
        value * scale,
        "COUNT",
        doc.text[number_token.idx:end],
        int(number_token.idx),
        end,
    )


def activity_predicate_arguments(text: str) -> tuple[ActivityPredicateArgument, ...]:
    """Recover typed activity facts from predicate-to-argument dependencies."""

    backend = semantic_backend_v292()
    rule = _RULE_BY_ID["v292.activity_predicate_argument"]
    predicate_lemmas = frozenset(rule.triggers)
    doc = backend.parse(text)
    output = []
    for predicate in doc:
        if predicate.pos_ != "VERB" or predicate.lemma_.casefold() not in predicate_lemmas:
            continue
        concept = ConceptMention(
            "ACTIVITY_VOLUME",
            predicate.text,
            int(predicate.idx),
            int(predicate.idx + len(predicate.text)),
        )
        for token in doc:
            if not token.like_num or not _direct_argument_of(token, predicate):
                continue
            quantity = _count_quantity(token, doc)
            if quantity is None:
                continue
            if backend.match_pattern(rule, text, (concept,), (quantity,)) is None:
                continue
            output.append(ActivityPredicateArgument(concept, quantity))
    unique = {
        (item.concept.char_start, item.quantity.char_start, item.quantity.char_end): item
        for item in output
    }
    return tuple(unique[key] for key in sorted(unique))


def impact_delta_arguments(
    text: str,
    concepts: tuple[ConceptMention, ...],
    quantities: tuple[QuantityMention, ...],
) -> tuple[ActivityPredicateArgument, ...]:
    """Bind impact/effect constructions to percentage DELTA roles."""

    backend = semantic_backend_v292()
    rule = _RULE_BY_ID["v292.impact_on_metric_delta"]
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    output = []
    for concept in concepts:
        if concept.concept != "ACTIVITY_VOLUME":
            continue
        if backend.match_pattern(rule, text, (concept,), percents) is None:
            continue
        output.extend(ActivityPredicateArgument(concept, quantity) for quantity in percents)
    return tuple(output)


__all__ = [
    "ActivityPredicateArgument",
    "RULE_PATH",
    "V292_RULES",
    "activity_predicate_arguments",
    "impact_delta_arguments",
    "is_share_transaction_event_scope",
    "semantic_backend_v292",
]
