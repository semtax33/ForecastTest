from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..context_validation import ContextBindingError
from ..document import document_text_blocks
from ..dsl import TextRuleIR, compile_text_rule_file
from ..model import ConceptMention, FactTier, KPIFrame, SemanticFrame, TextBlock
from ..ontology import definition_for, resolve_scope
from ..quantities import extract_quantities
from ..runtime import _match_rule
from ..spacy_backend import SpacySemanticBackend
from ..validation import FrameValidationError
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v266.semantics import (
    resolve_frame_conflicts_v266,
    semantic_concepts_v266,
)


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v267_semantic_laws.arc"
V267_RULES = compile_text_rule_file(RULE_PATH)

_SEMANTIC_ALIASES = {
    "cash, cash equivalents, and marketable securities": "CASH",
    "gross capital expenditures": "CAPEX",
}


@lru_cache(maxsize=1)
def semantic_backend_v267() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v267(
    text: str,
    backend: SpacySemanticBackend | None = None,
) -> tuple[ConceptMention, ...]:
    selected_backend = backend or semantic_backend_v267()
    candidates = list(semantic_concepts_v266(text, selected_backend))
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


def augment_candidates_v267(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    selected_backend = backend or semantic_backend_v267()
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
        for mention in semantic_concepts_v267(block.text, selected_backend):
            signature = (
                block.char_start,
                mention.concept,
                mention.char_start,
                mention.char_end,
            )
            if signature in seen or mention.alias.casefold() not in _SEMANTIC_ALIASES:
                continue
            allowed = set(definition_for(mention.concept).quantity_kinds)
            quantities = tuple(
                quantity
                for quantity in extract_quantities(block.text)
                if quantity.kind in allowed
                and abs(quantity.char_start - mention.char_start) <= 240
            )
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:"
                f"{mention.char_start}:{mention.char_end}:v267".encode()
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
                    quantities=quantities,
                    origins=(
                        CandidateOrigin.SENTENCE_WINDOW,
                        CandidateOrigin.DEPENDENCY,
                    ),
                    rule_ids=("v267.spacy_phrase_alias",),
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
    if frame.rule_id == "v267.organic_sales_word_range_guidance":
        return replace(frame, concept="REVENUE_CHANGE_GUIDANCE")
    return frame


def recover_v267_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V267_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v267()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v267(block.text, selected_backend)
        quantities = extract_quantities(block.text)
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
                            "binding_eligibility": "V267_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V267_SPACY_SEMANTIC_LAW_VERIFIER",
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


def resolve_frame_conflicts_v267(
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v267()
    prior = resolve_frame_conflicts_v266(existing, (), selected_backend)
    combined = (*prior, *recovered)

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

    def discard(frame: KPIFrame) -> bool:
        peers = tuple(
            other for other in combined if other is not frame and same_block(frame, other)
        )
        semantic_peers = tuple(
            other for other in peers if other.rule_id.startswith("v267.")
        )
        if frame.rule_id.startswith("v267."):
            return False
        if frame.tier is FactTier.NARRATIVE and frame.value is not None:
            return True
        if frame.frame is SemanticFrame.CHANGE_BY and any(
            other.concept == frame.concept
            and other.frame is SemanticFrame.CHANGE_TO
            and other.change == frame.value
            for other in peers
        ):
            return True
        if any(
            _base(other.concept) == _base(frame.concept)
            and (
                other.value == frame.value
                or other.change == frame.value
                or other.value == frame.change
            )
            for other in semantic_peers
        ):
            return True
        if any(
            other.rule_id == "v267.metric_money_change"
            and _base(frame.concept) == "REVENUE"
            for other in semantic_peers
        ):
            return True
        if (
            _base(frame.concept) == "OPERATING_INCOME"
            and any(
                other.rule_id == "v267.resulting_operating_margin"
                and other.value == frame.change
                for other in semantic_peers
            )
        ):
            return True
        text = frame.source_span.literal
        if (
            _base(frame.concept) == "DEBT"
            and selected_backend.phrase_mentions(
                text, ("payments on debt", "repayment of debt")
            )
        ):
            return True
        if (
            _base(frame.concept) == "REVENUE"
            and frame.frame is SemanticFrame.CHANGE_TO
            and frame.value is not None
            and not frame.rule_id.startswith("v267.")
        ):
            values = tuple(
                item
                for item in extract_quantities(text)
                if abs(item.value - frame.value)
                <= max(1e-9, abs(frame.value) * 1e-9)
            )
            concepts = tuple(
                item
                for item in semantic_concepts_v267(text, selected_backend)
                if item.concept == "REVENUE"
            )
            if values and concepts and all(
                concept.char_start > value.char_end
                for concept in concepts
                for value in values
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
        if current is None or frame.rule_id.startswith("v267."):
            unique[signature] = frame
    return tuple(unique.values())
