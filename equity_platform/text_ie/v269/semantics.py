from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..context_validation import ContextBindingError
from ..document import document_text_blocks
from ..dsl import TextRuleIR, compile_text_rule_file
from ..model import (
    ConceptMention,
    FactTier,
    KPIFrame,
    Polarity,
    QuantityKind,
    QuantityMention,
    SemanticFrame,
    TextBlock,
)
from ..ontology import definition_for, resolve_scope
from ..runtime import _match_rule
from ..spacy_backend import SpacySemanticBackend
from ..validation import FrameValidationError
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v268.semantics import (
    resolve_frame_conflicts_v268,
    semantic_concepts_v268,
    semantic_quantities_v268,
)


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v269_semantic_laws.arc"
V269_RULES = compile_text_rule_file(RULE_PATH)

_SEMANTIC_ALIASES = {
    "net selling price": "PRICE_REALIZATION",
    "selling price": "PRICE_REALIZATION",
    "debt outstanding": "DEBT",
    "outstanding debt": "DEBT",
    "debt": "DEBT",
    "average daily volume": "ACTIVITY_VOLUME",
    "quarterly average daily volume": "ACTIVITY_VOLUME",
    # In guidance, operating income expressed as a percentage of projected
    # revenue is economically an operating-margin forecast.
    "operating income guidance": "OPERATING_MARGIN",
}

_NUMBER_WORDS = {
    "zero": 0.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
    "eleven": 11.0,
    "twelve": 12.0,
    "thirteen": 13.0,
    "fourteen": 14.0,
    "fifteen": 15.0,
    "sixteen": 16.0,
    "seventeen": 17.0,
    "eighteen": 18.0,
    "nineteen": 19.0,
    "twenty": 20.0,
    "thirty": 30.0,
    "forty": 40.0,
    "fifty": 50.0,
    "sixty": 60.0,
    "seventy": 70.0,
    "eighty": 80.0,
    "ninety": 90.0,
}


@lru_cache(maxsize=1)
def semantic_backend_v269() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v269(
    text: str,
    backend: SpacySemanticBackend | None = None,
) -> tuple[ConceptMention, ...]:
    selected_backend = backend or semantic_backend_v269()
    candidates = list(semantic_concepts_v268(text, selected_backend))
    for literal, start, end in selected_backend.phrase_mentions(
        text, tuple(_SEMANTIC_ALIASES)
    ):
        candidates.append(
            ConceptMention(
                _SEMANTIC_ALIASES[literal.casefold()],
                text[start:end],
                start,
                end,
            )
        )
    selected: list[ConceptMention] = []
    for mention in sorted(
        candidates,
        key=lambda item: (item.char_start, -(item.char_end - item.char_start)),
    ):
        if any(
            mention.char_start < prior.char_end
            and prior.char_start < mention.char_end
            for prior in selected
        ):
            continue
        selected.append(mention)
    return tuple(selected)


def _word_percent_quantities(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    """Materialize number-word percentages from spaCy token topology."""

    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    output: list[QuantityMention] = []
    for index, token in enumerate(tokens[:-1]):
        value = _NUMBER_WORDS.get(token.lower_)
        if value is None:
            continue
        unit = tokens[index + 1]
        if unit.lower_ not in {"percent", "percentage"}:
            continue
        end = int(unit.idx + len(unit.text))
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


def _scaled_count_quantities(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    """Read scaled operational counts such as ``29.8 million contracts``."""

    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    scales = {"thousand": 1_000.0, "million": 1_000_000.0, "billion": 1_000_000_000.0}
    units = {"contract", "contracts", "unit", "units", "subscriber", "subscribers"}
    output: list[QuantityMention] = []
    for index, token in enumerate(tokens[:-2]):
        if not token.like_num or tokens[index + 1].lower_ not in scales:
            continue
        unit = tokens[index + 2]
        if unit.lower_ not in units:
            continue
        try:
            value = float(token.text.replace(",", "")) * scales[tokens[index + 1].lower_]
        except ValueError:
            continue
        end = int(unit.idx + len(unit.text))
        output.append(
            QuantityMention(
                kind=QuantityKind.COUNT,
                value=value,
                unit="COUNT",
                raw=text[int(token.idx) : end],
                char_start=int(token.idx),
                char_end=end,
            )
        )
    return tuple(output)


def semantic_quantities_v269(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    output = list(semantic_quantities_v268(text, backend))
    seen = {(item.char_start, item.char_end, item.kind) for item in output}
    for item in _word_percent_quantities(text, backend):
        signature = (item.char_start, item.char_end, item.kind)
        if signature not in seen:
            output.append(item)
            seen.add(signature)
    for item in _scaled_count_quantities(text, backend):
        signature = (item.char_start, item.char_end, item.kind)
        if signature not in seen:
            output.append(item)
            seen.add(signature)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end)))


def augment_candidates_v269(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    selected_backend = backend or semantic_backend_v269()
    output = list(candidates)
    seen = {
        (
            item.block.char_start,
            item.metric.concept,
            item.metric.char_start,
            item.metric.char_end,
        )
        for item in candidates
    }
    blocks = {
        (item.block.char_start, item.block.char_end): item.block for item in candidates
    }
    blocks.update(
        {
            (block.char_start, block.char_end): block
            for block in document_text_blocks(document)
        }
    )
    for block in blocks.values():
        quantities = semantic_quantities_v269(block.text, selected_backend)
        for mention in semantic_concepts_v269(block.text, selected_backend):
            signature = (
                block.char_start,
                mention.concept,
                mention.char_start,
                mention.char_end,
            )
            if signature in seen or mention.alias.casefold() not in _SEMANTIC_ALIASES:
                continue
            allowed = set(definition_for(mention.concept).quantity_kinds)
            local = tuple(
                quantity
                for quantity in quantities
                if quantity.kind in allowed
                and abs(quantity.char_start - mention.char_start) <= 320
            )
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:"
                f"{mention.char_start}:{mention.char_end}:v269".encode()
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
                    quantities=local,
                    origins=(CandidateOrigin.SENTENCE_WINDOW, CandidateOrigin.DEPENDENCY),
                    rule_ids=("v269.spacy_phrase_alias",),
                )
            )
            seen.add(signature)
    return tuple(output)


def _base(concept: str) -> str:
    result = concept.removeprefix("PRIOR_YEAR_")
    changed = True
    while changed:
        prior = result
        result = result.removesuffix("_GUIDANCE").removesuffix("_CHANGE")
        changed = result != prior
    return result


def _candidate_id(
    frame: KPIFrame,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
) -> str | None:
    matching = tuple(
        candidate
        for candidate in candidates
        if candidate.block.char_start == block.char_start
        and candidate.metric.concept == _base(frame.concept)
    )
    if not matching:
        return None
    return min(matching, key=lambda candidate: candidate.metric.char_start).candidate_id


def _postprocess_rule_frame(frame: KPIFrame) -> KPIFrame:
    if frame.rule_id in {
        "v269.revenue_growth_guidance_range",
        "v269.organic_cc_growth_guidance_range",
    }:
        frame = replace(frame, concept="REVENUE_CHANGE_GUIDANCE")
    if frame.rule_id == "v269.multi_margin_guidance_levels" or (
        frame.rule_id == "v269.multi_margin_levels"
        and "guidance" in frame.source_span.literal.casefold()
    ):
        frame = replace(frame, concept="OPERATING_MARGIN_GUIDANCE")
    if _base(frame.concept) in {"ACTIVITY_VOLUME", "PRICE_REALIZATION"}:
        frame = replace(frame, tier=FactTier.CRITICAL)
    if frame.rule_id in {
        "v269.price_change_component",
        "v269.signed_revenue_change",
    } and any(
        cue in frame.source_span.literal.casefold()
        for cue in (" lower ", " down ", " decreased ", " declined ")
    ):
        frame = replace(frame, polarity=Polarity(False, "semantic_negative_cue"))
    return frame


def recover_v269_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V269_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v269()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v269(block.text, selected_backend)
        quantities = semantic_quantities_v269(block.text, selected_backend)
        for rule in rules:
            try:
                matched = _match_rule(
                    document,
                    block,
                    rule,
                    concepts,
                    quantities,
                    inherited=False,
                    scope=resolve_scope(block.text, block.nearest_heading),
                    backend=selected_backend,
                )
            except (ContextBindingError, FrameValidationError, KeyError, ValueError):
                continue
            for raw_frame in matched or ():
                frame = _postprocess_rule_frame(raw_frame)
                output.append(
                    replace(
                        frame,
                        context_trace={
                            **frame.context_trace,
                            "candidate_id": _candidate_id(frame, block, candidates),
                            "binding_eligibility": "V269_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V269_SPACY_SEMANTIC_LAW_VERIFIER",
                    )
                )
    unique: dict[tuple[object, ...], KPIFrame] = {}
    for frame in output:
        unique.setdefault(
            (
                frame.concept,
                frame.frame,
                frame.value,
                frame.change,
                frame.lower_value,
                frame.upper_value,
                frame.polarity.positive,
                frame.source_span.char_start,
            ),
            frame,
        )
    return tuple(unique.values())


def resolve_frame_conflicts_v269(
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    """Give locally proven semantic roles ownership over legacy proximity binds."""

    selected_backend = backend or semantic_backend_v269()
    prior = resolve_frame_conflicts_v268(existing, (), selected_backend)

    def same_block(left: KPIFrame, right: KPIFrame) -> bool:
        return left.source.sha256 == right.source.sha256 and (
            (
                left.source_span.char_start <= right.source_span.char_start
                and right.source_span.char_end <= left.source_span.char_end
            )
            or (
                right.source_span.char_start <= left.source_span.char_start
                and left.source_span.char_end <= right.source_span.char_end
            )
        )

    def overlaps(left: KPIFrame, right: KPIFrame) -> bool:
        left_values = {
            value
            for value in (left.value, left.change, left.lower_value, left.upper_value)
            if value is not None
        }
        right_values = {
            value
            for value in (right.value, right.change, right.lower_value, right.upper_value)
            if value is not None
        }
        return bool(left_values & right_values)

    comparative_blocks = tuple(
        frame
        for frame in prior
        if frame.frame is SemanticFrame.COMPARATIVE and _base(frame.concept) == "REVENUE"
    )

    def discard_prior(frame: KPIFrame) -> bool:
        peers = tuple(other for other in recovered if same_block(frame, other))
        same_metric = tuple(
            other for other in peers if _base(other.concept) == _base(frame.concept)
        )
        if any(overlaps(frame, other) for other in same_metric):
            return True
        if _base(frame.concept) == "CAPEX" and any(
            other.rule_id in {"v269.capex_spent_level", "v269.capex_was_level"}
            for other in same_metric
        ):
            return True
        if _base(frame.concept) == "REVENUE" and frame.frame is SemanticFrame.CHANGE_BY:
            if any(
                _base(other.concept) in {"PRICE_REALIZATION", "ACTIVITY_VOLUME"}
                and frame.value == other.value
                for other in peers
            ):
                return True
            if any(same_block(frame, other) for other in comparative_blocks):
                return True
        if (
            _base(frame.concept) == "REVENUE"
            and frame.frame is SemanticFrame.CHANGE_TO
            and any(
                other.rule_id == "v269.constant_currency_secondary_change"
                and frame.change == other.value
                for other in same_metric
            )
        ):
            return True
        if frame.concept.endswith("_GUIDANCE") and any(
            other.frame is SemanticFrame.RANGE_GUIDANCE
            and overlaps(frame, other)
            for other in same_metric
        ):
            return True
        return False

    combined = tuple(frame for frame in prior if not discard_prior(frame)) + recovered
    unique: dict[tuple[object, ...], KPIFrame] = {}
    for frame in combined:
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
        current = unique.get(signature)
        if current is None or frame.rule_id.startswith("v269."):
            unique[signature] = frame
    return tuple(unique.values())
