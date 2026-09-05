from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
from math import isclose

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..document import document_text_blocks
from ..dsl import compile_text_rule_file
from ..model import ConceptMention, QuantityKind, SemanticFrame
from ..ontology import definition_for
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v280 import semantics as frame_factory
from ..v282 import semantics as prior_semantics


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v283_bounded_upper_context.arc"
V283_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V283_RULES}
_ALIASES = {
    "segment comparable operating earnings": "OPERATING_INCOME",
    "comparable operating earnings": "OPERATING_INCOME",
    "adjusted operating income rate": "OPERATING_MARGIN",
    "operating income rate": "OPERATING_MARGIN",
    "capital expenditures": "CAPEX",
    "comparable sales": "REVENUE",
}
_FUTURE_PHRASES = (
    "guidance",
    "business outlook",
    "financial outlook",
    "expects",
    "expected to be",
    "forecast",
    "projected",
)
_BOUNDARY_PHRASES = (
    "conference call information",
    "quarterly financial results",
    "non-gaap financial measures",
)
_FUTURE = {"expect", "guide", "forecast", "project", "outlook", "raise", "reiterate"}


def _base(concept: str) -> str:
    return prior_semantics._base(concept)


@lru_cache(maxsize=1)
def semantic_backend_v283():
    return prior_semantics.semantic_backend_v282()


def _tokens(backend, text: str):
    return tuple(token for token in backend.parse(text) if not token.is_space)


def _has(tokens, start: int, end: int, cues: set[str]) -> bool:
    return any(
        start <= token.idx < end
        and (token.lemma_.casefold() in cues or token.lower_ in cues)
        for token in tokens
    )


def _mentions(concepts, names: set[str]):
    return prior_semantics._mentions(concepts, names)


def semantic_quantities_v283(text: str, backend=None):
    return prior_semantics.semantic_quantities_v282(
        text, backend or semantic_backend_v283()
    )


def semantic_concepts_v283(text: str, backend=None) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v283()
    output = list(prior_semantics.semantic_concepts_v282(text, selected))
    for alias, concept in _ALIASES.items():
        output.extend(
            ConceptMention(concept, literal, start, end)
            for literal, start, end in selected.phrase_mentions(text, (alias,))
        )
    folded = text.casefold()
    percent_count = sum(
        item.kind is QuantityKind.PERCENT
        for item in semantic_quantities_v283(text, selected)
    )
    if percent_count >= 2 and ("of net sales" in folded or "of revenue" in folded):
        for mention in tuple(output):
            if mention.concept == "ADJUSTED_EBITDA":
                output.append(
                    ConceptMention(
                        "ADJUSTED_EBITDA_MARGIN",
                        mention.alias,
                        mention.char_start,
                        mention.char_end,
                    )
                )
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(
        sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept))
    )


def augment_candidates_v283(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v283()
    output = list(candidates)
    seen = {
        (
            item.block.char_start,
            item.metric.concept,
            item.metric.char_start,
            item.metric.char_end,
        )
        for item in output
    }
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v283(block.text, backend)
        for mention in semantic_concepts_v283(block.text, backend):
            signature = (
                block.char_start,
                mention.concept,
                mention.char_start,
                mention.char_end,
            )
            is_new_role = (
                mention.alias.casefold() in _ALIASES
                or mention.concept == "ADJUSTED_EBITDA_MARGIN"
            )
            if signature in seen or not is_new_role:
                continue
            allowed = set(definition_for(mention.concept).quantity_kinds) | {
                QuantityKind.MONEY,
                QuantityKind.PERCENT,
                QuantityKind.BASIS_POINTS,
            }
            compatible = tuple(
                item
                for item in quantities
                if item.kind in allowed
                and abs(item.char_start - mention.char_start) <= 360
            )
            if not compatible:
                continue
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:"
                f"{mention.char_start}:{mention.char_end}:v283".encode()
            ).hexdigest()[:20]
            output.append(
                RecallCandidate(
                    candidate_id=candidate_id,
                    block=block,
                    metric=MetricAnchor(
                        mention.concept,
                        mention.alias,
                        mention.char_start,
                        mention.char_end,
                    ),
                    quantities=compatible,
                    origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                    rule_ids=("v283.spacy_bounded_upper_context_alias",),
                )
            )
            seen.add(signature)
    return tuple(output)


def _new_frame(
    document,
    block,
    candidates,
    *,
    rule_id,
    concept,
    semantic,
    value,
    change=None,
    lower=None,
    upper=None,
    positive=True,
):
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
    trace.update(
        {
            "binding_eligibility": "V283_SPACY_BOUNDED_UPPER_CONTEXT",
            "upper_context_role": "BOOLEAN_GUIDANCE_ONLY",
            "parent_numeric_inheritance": False,
            "rule_program_sha256": rule.source_sha256,
        }
    )
    return replace(
        frame,
        rule_id=rule_id,
        rule_version=rule.version,
        verified_by="V283_SPACY_BOUNDED_UPPER_CONTEXT_VERIFIER",
        context_trace=trace,
    )


def _range(document, block, candidates, concept, low, high):
    midpoint = replace(low, value=(low.value + high.value) / 2.0)
    return _new_frame(
        document,
        block,
        candidates,
        rule_id="v283.metric_range_roles",
        concept=concept,
        semantic=SemanticFrame.RANGE_GUIDANCE,
        value=midpoint,
        lower=low,
        upper=high,
    )


def _phrase(backend, text: str, phrases: tuple[str, ...]) -> bool:
    return bool(backend.phrase_mentions(text, phrases))


def _upper_future_context(block, blocks, backend) -> bool:
    local_context = " ".join(
        value
        for value in (block.section, block.nearest_heading)
        if value
    )
    if _phrase(backend, local_context, _FUTURE_PHRASES):
        return True
    index = next(
        (position for position, item in enumerate(blocks) if item.char_start == block.char_start),
        None,
    )
    if index is None:
        return False
    for prior in reversed(blocks[max(0, index - 5) : index]):
        if block.char_start - prior.char_end > 900:
            break
        if _phrase(backend, prior.text, _BOUNDARY_PHRASES):
            break
        if _phrase(backend, prior.text, _FUTURE_PHRASES):
            return True
    return False


def _linked(tokens, low, high, start: int) -> bool:
    return _has(tokens, start, low.char_start, {"between", "range"}) or _has(
        tokens, low.char_end, high.char_start, {"to", "through"}
    )


def _role_windows(concepts):
    mentions = _mentions(
        concepts,
        {"REVENUE", "ADJUSTED_EBITDA", "GROSS_MARGIN", "OPERATING_MARGIN", "CAPEX"},
    )
    return tuple(
        (mention, mentions[index + 1].char_start if index + 1 < len(mentions) else None)
        for index, mention in enumerate(mentions)
    )


def _range_role_frames(
    document,
    block,
    candidates,
    concepts,
    quantities,
    backend,
    upper_future,
):
    tokens = _tokens(backend, block.text)
    folded = block.text.casefold()
    local_future = _has(tokens, 0, len(block.text), _FUTURE)
    output = []
    for mention, next_start in _role_windows(concepts):
        end = next_start if next_start is not None else len(block.text)
        money = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.MONEY
            and mention.char_end <= item.char_start < end
        )
        percents = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT
            and mention.char_end <= item.char_start < end
        )
        guidance = upper_future or local_future or "guidance" in folded or "outlook" in folded
        made = None
        if mention.concept == "REVENUE" and percents:
            if len(percents) >= 2 and _linked(tokens, percents[0], percents[1], mention.char_end) and guidance:
                made = _range(
                    document,
                    block,
                    candidates,
                    "REVENUE_CHANGE_GUIDANCE",
                    percents[0],
                    percents[1],
                )
            elif not any(item.char_start < percents[0].char_start for item in money) and _has(
                tokens,
                mention.char_end,
                percents[0].char_start,
                {"increase", "decrease", "growth", "up"},
            ):
                made = _new_frame(
                    document,
                    block,
                    candidates,
                    rule_id="v283.metric_range_roles",
                    concept="REVENUE",
                    semantic=SemanticFrame.CHANGE_BY,
                    value=percents[0],
                    positive=not _has(tokens, mention.char_end, percents[0].char_start, {"decrease"}),
                )
        elif mention.concept == "REVENUE" and money and len(money) >= 2:
            if _linked(tokens, money[0], money[1], mention.char_end) and guidance:
                made = _range(
                    document,
                    block,
                    candidates,
                    "REVENUE_GUIDANCE",
                    money[0],
                    money[1],
                )
        elif mention.concept == "ADJUSTED_EBITDA" and len(money) >= 2:
            implied = "range" in folded or "expected" in folded
            if _linked(tokens, money[0], money[1], mention.char_end) and (guidance or implied):
                made = _range(
                    document,
                    block,
                    candidates,
                    "ADJUSTED_EBITDA_GUIDANCE",
                    money[0],
                    money[1],
                )
        elif mention.concept in {"GROSS_MARGIN", "OPERATING_MARGIN"} and len(percents) >= 2:
            if _linked(tokens, percents[0], percents[1], mention.char_end) and guidance:
                made = _range(
                    document,
                    block,
                    candidates,
                    f"{mention.concept}_GUIDANCE",
                    percents[0],
                    percents[1],
                )
        elif mention.concept == "CAPEX" and money:
            capex_guidance = guidance or "approximately" in folded or "full year" in folded
            if len(money) >= 2 and _linked(tokens, money[0], money[1], mention.char_end) and capex_guidance:
                made = _range(
                    document,
                    block,
                    candidates,
                    "CAPEX_GUIDANCE",
                    money[0],
                    money[1],
                )
            elif capex_guidance:
                made = _new_frame(
                    document,
                    block,
                    candidates,
                    rule_id="v283.metric_range_roles",
                    concept="CAPEX_GUIDANCE",
                    semantic=SemanticFrame.ABSOLUTE_VALUE,
                    value=money[0],
                )
        if made is not None:
            output.append(made)
    return tuple(output)


def _ebitda_margin_pair_frames(
    document, block, candidates, concepts, quantities, backend, upper_future
):
    folded = block.text.casefold()
    if (
        "adjusted ebitda" not in folded
        or ("of net sales" not in folded and "of revenue" not in folded)
        or "compared" not in folded
    ):
        return ()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
    if len(money) < 2 or len(percents) < 2:
        return ()
    specs = (
        ("ADJUSTED_EBITDA", money[0]),
        ("PRIOR_YEAR_ADJUSTED_EBITDA", money[1]),
        ("ADJUSTED_EBITDA_MARGIN", percents[0]),
        ("PRIOR_YEAR_ADJUSTED_EBITDA_MARGIN", percents[1]),
    )
    return tuple(
        frame
        for concept, value in specs
        if (
            frame := _new_frame(
                document,
                block,
                candidates,
                rule_id="v283.ebitda_margin_pair",
                concept=concept,
                semantic=SemanticFrame.COMPARATIVE,
                value=value,
            )
        )
        is not None
    )


def _operating_sales_pair_frames(
    document, block, candidates, concepts, quantities, backend, upper_future
):
    folded = block.text.casefold()
    if "comparable operating earnings" not in folded or "on sales" not in folded or "compared" not in folded:
        return ()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    if len(money) < 4:
        return ()
    specs = (
        ("OPERATING_INCOME", money[0]),
        ("REVENUE", money[1]),
        ("PRIOR_YEAR_OPERATING_INCOME", money[2]),
        ("PRIOR_YEAR_REVENUE", money[3]),
    )
    return tuple(
        frame
        for concept, value in specs
        if (
            frame := _new_frame(
                document,
                block,
                candidates,
                rule_id="v283.operating_sales_pair",
                concept=concept,
                semantic=SemanticFrame.COMPARATIVE,
                value=value,
            )
        )
        is not None
    )


def _multi_comparison_frames(
    document, block, candidates, concepts, quantities, backend, upper_future
):
    folded = block.text.casefold()
    if "operating income" not in folded or "previous quarter" not in folded or "prior year" not in folded:
        return ()
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    if len(money) < 3:
        return ()
    specs = (
        ("OPERATING_INCOME", money[0]),
        ("PRIOR_YEAR_OPERATING_INCOME", money[1]),
        ("PRIOR_YEAR_OPERATING_INCOME", money[2]),
    )
    return tuple(
        frame
        for concept, value in specs
        if (
            frame := _new_frame(
                document,
                block,
                candidates,
                rule_id="v283.multi_period_comparison",
                concept=concept,
                semantic=SemanticFrame.COMPARATIVE,
                value=value,
            )
        )
        is not None
    )


def recover_v283_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
):
    backend = semantic_backend_v283()
    all_blocks = document_text_blocks(document)
    blocks = {(item.block.char_start, item.block.char_end): item.block for item in candidates}
    output = []
    binders = (
        _range_role_frames,
        _ebitda_margin_pair_frames,
        _operating_sales_pair_frames,
        _multi_comparison_frames,
    )
    for span, block in blocks.items():
        if span not in allowed_spans:
            continue
        concepts = semantic_concepts_v283(block.text, backend)
        quantities = semantic_quantities_v283(block.text, backend)
        upper_future = _upper_future_context(block, all_blocks, backend)
        for binder in binders:
            output.extend(
                binder(
                    document,
                    block,
                    candidates,
                    concepts,
                    quantities,
                    backend,
                    upper_future,
                )
            )
    unique = {}
    for frame in output:
        signature = (
            frame.concept,
            frame.frame,
            round(frame.value, 6),
            None if frame.change is None else round(frame.change, 6),
            frame.lower_value,
            frame.upper_value,
            frame.polarity.positive,
            frame.source.sha256,
            frame.source_span.char_start,
        )
        unique[signature] = frame
    return tuple(unique.values())


def resolve_frame_conflicts_v283(existing, recovered):
    first = prior_semantics.resolve_frame_conflicts_v282(existing, recovered)

    def numbers(frame):
        return tuple(
            value
            for value in (frame.value, frame.change, frame.lower_value, frame.upper_value)
            if value is not None
        )

    def overlaps(frame, item):
        return (
            item.source.sha256 == frame.source.sha256
            and item.source_span.char_start <= frame.source_span.char_start
            and frame.source_span.char_end <= item.source_span.char_end
        )

    def close_values(left, right):
        return any(
            isclose(a, b, rel_tol=1e-10, abs_tol=1e-6)
            for a in numbers(left)
            for b in numbers(right)
        )

    def superseded(frame):
        literal = frame.source_span.literal.casefold()
        replacements = tuple(item for item in recovered if overlaps(frame, item))
        same = any(
            _base(item.concept) == _base(frame.concept) and close_values(item, frame)
            for item in replacements
        )
        range_role = any(
            item.frame is SemanticFrame.RANGE_GUIDANCE
            and _base(item.concept) == _base(frame.concept)
            for item in replacements
        )
        non_cash = _base(frame.concept) == "CASH" and "non-cash" in literal
        expense_ratio = (
            _base(frame.concept) == "REVENUE"
            and "expenses as a percentage of" in literal
        )
        per_share_retyping = (
            _base(frame.concept) in {"CASH", "REVENUE"}
            and "per diluted share" in literal
            and ("non-cash" in literal or "higher revenues" in literal)
        )
        ebitda_pair = (
            _base(frame.concept) in {"ADJUSTED_EBITDA", "REVENUE"}
            and "adjusted ebitda" in literal
            and "of net sales" in literal
            and any(item.rule_id == "v283.ebitda_margin_pair" for item in replacements)
        )
        operating_sales_pair = (
            _base(frame.concept) in {"OPERATING_INCOME", "REVENUE"}
            and "comparable operating earnings" in literal
            and any(item.rule_id == "v283.operating_sales_pair" for item in replacements)
        )
        cross_metric = any(
            _base(item.concept) in {"OPERATING_MARGIN", "ADJUSTED_EBITDA_MARGIN"}
            and _base(frame.concept) in {"REVENUE", "ADJUSTED_EBITDA"}
            and close_values(item, frame)
            for item in replacements
        )
        return (
            same
            or range_role
            or non_cash
            or expense_ratio
            or per_share_retyping
            or ebitda_pair
            or operating_sales_pair
            or cross_metric
        )

    merged = (*(frame for frame in first if not superseded(frame)), *recovered)
    unique = {}
    for frame in merged:
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
        current = unique.get(signature)
        if current is None or frame.rule_id.startswith("v283."):
            unique[signature] = frame
    return tuple(unique.values())
