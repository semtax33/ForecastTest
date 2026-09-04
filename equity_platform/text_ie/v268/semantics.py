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
    QuantityKind,
    QuantityMention,
    SemanticFrame,
    TextBlock,
)
from ..ontology import definition_for, resolve_scope
from ..quantities import extract_quantities
from ..runtime import _match_rule
from ..spacy_backend import SpacySemanticBackend
from ..validation import FrameValidationError
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v267.semantics import resolve_frame_conflicts_v267, semantic_concepts_v267


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v268_semantic_laws.arc"
V268_RULES = compile_text_rule_file(RULE_PATH)

_SEMANTIC_ALIASES = {
    "income from railway operations": "OPERATING_INCOME",
    "railway operating income": "OPERATING_INCOME",
}


@lru_cache(maxsize=1)
def semantic_backend_v268() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v268(
    text: str,
    backend: SpacySemanticBackend | None = None,
) -> tuple[ConceptMention, ...]:
    selected_backend = backend or semantic_backend_v268()
    candidates = list(semantic_concepts_v267(text, selected_backend))
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


def _rate_quantities(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    """Read ``x-to-1`` ratios from spaCy token topology without regex."""

    doc = backend.parse(text)
    tokens = tuple(token for token in doc if not token.is_space)
    output: list[QuantityMention] = []
    for index, token in enumerate(tokens):
        if not token.like_num:
            continue
        try:
            numerator = float(token.text.replace(",", ""))
        except ValueError:
            continue
        tail = tokens[index + 1 : index + 6]
        to_index = next(
            (
                offset
                for offset, item in enumerate(tail)
                if item.lower_ == "to" or item.lower_.startswith("to-")
            ),
            None,
        )
        if to_index is None:
            continue
        to_token = tail[to_index]
        denominator = next(
            (item for item in tail[to_index + 1 :] if item.like_num),
            None,
        )
        denominator_text = (
            denominator.text
            if denominator is not None
            else to_token.lower_.removeprefix("to-")
            if to_token.lower_.startswith("to-")
            else ""
        )
        try:
            denominator_value = float(denominator_text.replace(",", ""))
        except ValueError:
            continue
        if denominator_value != 1.0:
            continue
        end_token = denominator or to_token
        end = int(end_token.idx + len(end_token.text))
        output.append(
            QuantityMention(
                kind=QuantityKind.RATE,
                value=numerator,
                unit="X",
                raw=text[int(token.idx) : end],
                char_start=int(token.idx),
                char_end=end,
            )
        )
    return tuple(output)


def semantic_quantities_v268(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    output = list(extract_quantities(text))
    seen = {(item.char_start, item.char_end, item.kind) for item in output}
    for item in _rate_quantities(text, backend):
        signature = (item.char_start, item.char_end, item.kind)
        if signature not in seen:
            output.append(item)
            seen.add(signature)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end)))


def augment_candidates_v268(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    selected_backend = backend or semantic_backend_v268()
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
        (item.block.char_start, item.block.char_end): item.block
        for item in candidates
    }
    blocks.update(
        {
            (block.char_start, block.char_end): block
            for block in document_text_blocks(document)
        }
    )
    for block in blocks.values():
        quantities = semantic_quantities_v268(block.text, selected_backend)
        for mention in semantic_concepts_v268(block.text, selected_backend):
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
                and abs(quantity.char_start - mention.char_start) <= 260
            )
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:"
                f"{mention.char_start}:{mention.char_end}:v268".encode()
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
                    rule_ids=("v268.spacy_phrase_alias",),
                )
            )
            seen.add(signature)
    return tuple(output)


def _base(concept: str) -> str:
    result = concept.removeprefix("PRIOR_YEAR_")
    for suffix in ("_GUIDANCE", "_CHANGE"):
        result = result.removesuffix(suffix)
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
    if frame.rule_id == "v268.revenue_growth_range":
        return replace(frame, concept="REVENUE_CHANGE_GUIDANCE")
    if _base(frame.concept) == "ACTIVITY_VOLUME" and frame.value is not None:
        return replace(frame, tier=FactTier.CRITICAL)
    return frame


def recover_v268_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V268_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v268()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v268(block.text, selected_backend)
        quantities = semantic_quantities_v268(block.text, selected_backend)
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
                            "binding_eligibility": "V268_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V268_SPACY_SEMANTIC_LAW_VERIFIER",
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


def resolve_frame_conflicts_v268(
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    """Prefer locally proven V268 roles and fail closed on known ownership traps."""

    selected_backend = backend or semantic_backend_v268()
    def same_block(left: KPIFrame, right: KPIFrame) -> bool:
        return (
            left.source.sha256 == right.source.sha256
            and (
                (
                    left.source_span.char_start <= right.source_span.char_start
                    and right.source_span.char_end <= left.source_span.char_end
                )
                or (
                    right.source_span.char_start <= left.source_span.char_start
                    and left.source_span.char_end <= right.source_span.char_end
                )
            )
        )

    prior = resolve_frame_conflicts_v267(existing, (), selected_backend)
    recovered = tuple(
        frame
        for frame in recovered
        if not (
            frame.frame is SemanticFrame.ABSOLUTE_VALUE
            and any(
                same_block(frame, old)
                and _base(frame.concept) == _base(old.concept)
                and old.frame is SemanticFrame.CHANGE_TO
                and old.value == frame.value
                and old.change is not None
                for old in prior
            )
            or (
                frame.rule_id == "v268.revenue_level_amount_change"
                and any(
                    same_block(frame, other)
                    and other.rule_id == "v268.revenue_level_percent_change"
                    for other in recovered
                )
            )
        )
    )
    combined = (*prior, *recovered)

    def discard(frame: KPIFrame) -> bool:
        if frame.rule_id.startswith("v268."):
            return frame.frame is SemanticFrame.ABSOLUTE_VALUE and any(
                other is not frame
                and same_block(frame, other)
                and _base(frame.concept) == _base(other.concept)
                and other.frame is SemanticFrame.CHANGE_TO
                and other.value == frame.value
                for other in recovered
            )
        peers = tuple(
            other
            for other in recovered
            if same_block(frame, other) and _base(other.concept) == _base(frame.concept)
        )
        if peers:
            if (
                frame.frame is SemanticFrame.RANGE_GUIDANCE
                and frame.concept.endswith("_GUIDANCE")
                and not any(peer.frame is SemanticFrame.RANGE_GUIDANCE for peer in peers)
            ):
                return False
            return True
        text = frame.source_span.literal
        if frame.rule_id == "v264.compact_operating_income":
            return True
        operating_peers = tuple(
            other
            for other in recovered
            if same_block(frame, other) and _base(other.concept) == "OPERATING_INCOME"
        )
        if _base(frame.concept) == "OPERATING_MARGIN" and operating_peers:
            if selected_backend.phrase_mentions(text, ("operating margin rate",)):
                return True
        if _base(frame.concept) == "REVENUE":
            if (
                selected_backend.phrase_mentions(
                    text, ("income from railway operations",)
                )
                and not selected_backend.phrase_mentions(
                    text, ("operating revenues", "revenue was", "revenues were")
                )
            ):
                return True
            if operating_peers and not any(
                _base(other.concept) == "REVENUE"
                for other in recovered
                if same_block(frame, other)
            ):
                return True
            if (
                selected_backend.phrase_mentions(text, ("earnings per share",))
                and not selected_backend.phrase_mentions(text, ("revenue", "revenues"))
            ):
                return True
        if (
            _base(frame.concept) == "OPERATING_MARGIN"
            and frame.frame is SemanticFrame.CHANGE_TO
            and frame.change is None
            and selected_backend.phrase_mentions(text, ("pts to", "points to"))
        ):
            return True
        return False

    unique: dict[tuple[object, ...], KPIFrame] = {}
    for frame in combined:
        if discard(frame):
            continue
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
        if current is None or frame.rule_id.startswith("v268."):
            unique[signature] = frame
    return tuple(unique.values())
