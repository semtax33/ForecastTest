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
    PeriodSemantics,
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
from ..v270.semantics import (
    augment_candidates_v270,
    semantic_concepts_v270,
    semantic_quantities_v270,
)


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v271_semantic_laws.arc"
V271_RULES = compile_text_rule_file(RULE_PATH)


@lru_cache(maxsize=1)
def semantic_backend_v271() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v271(
    text: str,
    backend: SpacySemanticBackend | None = None,
) -> tuple[ConceptMention, ...]:
    selected_backend = backend or semantic_backend_v271()
    output = list(semantic_concepts_v270(text, selected_backend))
    for literal, start, end in selected_backend.phrase_mentions(
        text, ("core net new assets",)
    ):
        output.append(ConceptMention("ACTIVITY_VOLUME", literal, start, end))

    # "operating income of $X or Y% of revenue" explicitly reports both
    # operating income and its revenue ratio.  Give the ratio a distinct
    # semantic concept while retaining the shared source phrase.
    percent_of_revenue = selected_backend.phrase_mentions(text, ("percent of revenue",))
    if percent_of_revenue:
        for literal, start, end in selected_backend.phrase_mentions(
            text, ("operating income",)
        ):
            if any(start < ratio_start <= start + 100 for _, ratio_start, _ in percent_of_revenue):
                output.append(
                    ConceptMention("OPERATING_MARGIN", literal + " ratio", start, end)
                )

    unique: dict[tuple[str, int, int], ConceptMention] = {}
    for mention in output:
        unique.setdefault(
            (mention.concept, mention.char_start, mention.char_end), mention
        )
    return tuple(
        sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept))
    )


def semantic_quantities_v271(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    return semantic_quantities_v270(text, backend)


def augment_candidates_v271(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    selected_backend = backend or semantic_backend_v271()
    output = list(augment_candidates_v270(document, candidates, selected_backend))
    seen = {
        (
            item.block.char_start,
            item.metric.concept,
            item.metric.char_start,
            item.metric.char_end,
        )
        for item in output
    }
    blocks = {
        (item.block.char_start, item.block.char_end): item.block for item in output
    }
    blocks.update(
        {
            (block.char_start, block.char_end): block
            for block in document_text_blocks(document)
        }
    )
    for block in blocks.values():
        quantities = semantic_quantities_v271(block.text, selected_backend)
        for mention in semantic_concepts_v271(block.text, selected_backend):
            signature = (
                block.char_start,
                mention.concept,
                mention.char_start,
                mention.char_end,
            )
            if signature in seen:
                continue
            if mention.concept not in {"ACTIVITY_VOLUME", "OPERATING_MARGIN"}:
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
                f"{mention.char_start}:{mention.char_end}:v271".encode()
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
                    rule_ids=("v271.spacy_semantic_concept",),
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


_TOLERANCE_RULES = {
    "v271.revenue_absolute_tolerance_guidance",
    "v271.gross_margin_relative_tolerance_guidance",
}


def _postprocess_rule_frame(
    frame: KPIFrame,
    quantities: tuple[QuantityMention, ...],
    backend: SpacySemanticBackend,
) -> KPIFrame:
    if frame.rule_id not in _TOLERANCE_RULES:
        return frame
    trace = dict(frame.context_trace.get("semantic_roles", {}))
    tolerance_roles = list(trace.get("tolerance", ()))
    if len(tolerance_roles) != 1 or frame.value is None:
        return frame
    role = tolerance_roles[0]
    tolerance = next(
        (
            item
            for item in quantities
            if int(role["start"]) <= item.char_start
            and item.char_end <= int(role["end"])
        ),
        None,
    )
    if tolerance is None:
        return frame
    midpoint = frame.value
    delta = tolerance.value
    if (
        frame.unit == "USD"
        and tolerance.unit == "USD"
        and backend.phrase_mentions(frame.source_span.literal, ("in millions",))
        and midpoint < 1_000_000
    ):
        midpoint *= 1_000_000.0
        delta *= 1_000_000.0
    return replace(
        frame,
        frame=SemanticFrame.RANGE_GUIDANCE,
        period_semantics=PeriodSemantics.FORECAST,
        value=midpoint,
        lower_value=midpoint - delta,
        upper_value=midpoint + delta,
        context_trace={**frame.context_trace, "absolute_tolerance": delta},
    )


def recover_v271_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V271_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v271()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v271(block.text, selected_backend)
        quantities = semantic_quantities_v271(block.text, selected_backend)
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
                frame = _postprocess_rule_frame(raw_frame, quantities, selected_backend)
                if _base(frame.concept) == "ACTIVITY_VOLUME":
                    frame = replace(frame, tier=FactTier.CRITICAL)
                output.append(
                    replace(
                        frame,
                        context_trace={
                            **frame.context_trace,
                            "candidate_id": _candidate_id(frame, block, candidates),
                            "binding_eligibility": "V271_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V271_SPACY_SEMANTIC_LAW_VERIFIER",
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


def resolve_frame_conflicts_v271(
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v271()

    def same_block(left: KPIFrame, right: KPIFrame) -> bool:
        return left.source.sha256 == right.source.sha256 and (
            left.source_span.char_start <= right.source_span.char_start
            and right.source_span.char_end <= left.source_span.char_end
            or right.source_span.char_start <= left.source_span.char_start
            and left.source_span.char_end <= right.source_span.char_end
        )

    def values(frame: KPIFrame) -> set[float]:
        return {
            value
            for value in (frame.value, frame.change, frame.lower_value, frame.upper_value)
            if value is not None
        }

    def discard_prior(frame: KPIFrame) -> bool:
        peers = tuple(other for other in recovered if same_block(frame, other))
        same_metric = tuple(
            other for other in peers if _base(other.concept) == _base(frame.concept)
        )
        if any(values(frame) & values(other) for other in same_metric):
            return True
        if any(
            other.frame is SemanticFrame.RANGE_GUIDANCE for other in same_metric
        ) and frame.frame is not SemanticFrame.RANGE_GUIDANCE:
            return True
        if any(
            other.frame is SemanticFrame.CHANGE_TO
            and frame.frame is SemanticFrame.ABSOLUTE_VALUE
            and other.value == frame.value
            for other in same_metric
        ):
            return True
        if (
            _base(frame.concept) == "REVENUE"
            and frame.value is not None
            and abs(frame.value) < 100.0
            and selected_backend.phrase_mentions(
                frame.source_span.literal,
                ("eps", "earnings per share", "diluted earnings per share"),
            )
            and selected_backend.phrase_mentions(
                frame.source_span.literal,
                ("operating income", "operating margin", "gross margin"),
            )
        ):
            return True
        return False

    def discard_recovered(frame: KPIFrame) -> bool:
        peers = tuple(other for other in recovered if other is not frame and same_block(frame, other))
        same_metric = tuple(
            other for other in peers if _base(other.concept) == _base(frame.concept)
        )
        if (
            frame.frame is SemanticFrame.ABSOLUTE_VALUE
            and any(other.frame is SemanticFrame.RANGE_GUIDANCE for other in same_metric)
            and any(values(frame) & values(other) for other in same_metric)
        ):
            return True
        if frame.rule_id == "v271.revenue_was_money_change" and any(
            other.rule_id == "v271.revenue_was_percent_change"
            and other.value == frame.value
            for other in same_metric
        ):
            return True
        return False

    accepted_recovered = tuple(frame for frame in recovered if not discard_recovered(frame))
    ordered = tuple(frame for frame in existing if not discard_prior(frame)) + accepted_recovered
    selected: list[KPIFrame] = []
    for frame in ordered:
        signature = (
            frame.concept,
            frame.frame,
            frame.value,
            frame.change,
            frame.lower_value,
            frame.upper_value,
            frame.polarity.positive,
            frame.source.sha256,
        )
        duplicate_index = next(
            (
                index
                for index, current in enumerate(selected)
                if (
                    current.concept,
                    current.frame,
                    current.value,
                    current.change,
                    current.lower_value,
                    current.upper_value,
                    current.polarity.positive,
                    current.source.sha256,
                )
                == signature
                and same_block(current, frame)
            ),
            None,
        )
        if duplicate_index is None:
            selected.append(frame)
        elif frame.rule_id.startswith("v271."):
            selected[duplicate_index] = frame
    return tuple(selected)
