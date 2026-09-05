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
    KPIFrame,
    PeriodSemantics,
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
from ..v272.semantics import (
    augment_candidates_v272,
    resolve_frame_conflicts_v272,
    semantic_concepts_v272,
    semantic_quantities_v272,
)


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v273_semantic_laws.arc"
V273_RULES = compile_text_rule_file(RULE_PATH)


@lru_cache(maxsize=1)
def semantic_backend_v273() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v273(
    text: str,
    backend: SpacySemanticBackend | None = None,
) -> tuple[ConceptMention, ...]:
    """Extend the ontology with semantic aliases observed in issuer IR text."""

    selected_backend = backend or semantic_backend_v273()
    output = list(semantic_concepts_v272(text, selected_backend))
    for literal, start, end in selected_backend.phrase_mentions(
        text,
        ("earnings from operations",),
    ):
        output.append(ConceptMention("OPERATING_INCOME", literal, start, end))
    tokens = tuple(token for token in selected_backend.parse(text) if not token.is_space)
    for index, token in enumerate(tokens):
        if index == 0 or not token.lower_.startswith("income"):
            continue
        footnote = token.text[len("income") :]
        if not footnote.isdigit() or tokens[index - 1].lower_ != "operating":
            continue
        start = int(tokens[index - 1].idx)
        end = int(token.idx + len(token.text))
        output.append(ConceptMention("OPERATING_INCOME", text[start:end], start, end))
    unique: dict[tuple[str, int, int], ConceptMention] = {}
    for mention in output:
        unique.setdefault((mention.concept, mention.char_start, mention.char_end), mention)
    return tuple(
        sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept))
    )


def semantic_quantities_v273(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    return semantic_quantities_v272(text, backend)


def augment_candidates_v273(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    """Recall newly recognized operating-income aliases at the candidate seam."""

    selected_backend = backend or semantic_backend_v273()
    output = list(augment_candidates_v272(document, candidates, selected_backend))
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
        quantities = semantic_quantities_v273(block.text, selected_backend)
        for mention in semantic_concepts_v273(block.text, selected_backend):
            signature = (
                block.char_start,
                mention.concept,
                mention.char_start,
                mention.char_end,
            )
            if signature in seen or mention.concept != "OPERATING_INCOME":
                continue
            compatible = tuple(
                quantity
                for quantity in quantities
                if quantity.kind in definition_for(mention.concept).quantity_kinds
                and abs(quantity.char_start - mention.char_start) <= 320
            )
            if not compatible:
                continue
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:"
                f"{mention.char_start}:{mention.char_end}:v273".encode()
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
                    rule_ids=("v273.spacy_semantic_alias",),
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


def _regions(
    anchors: tuple[QuantityMention, ...],
    values: tuple[QuantityMention, ...],
) -> tuple[tuple[QuantityMention, tuple[QuantityMention, ...]], ...]:
    output = []
    for index, anchor in enumerate(anchors):
        boundary = anchors[index + 1].char_start if index + 1 < len(anchors) else 10**12
        output.append(
            (
                anchor,
                tuple(
                    value
                    for value in values
                    if anchor.char_end <= value.char_start < boundary
                ),
            )
        )
    return tuple(output)


def _owned_amounts(
    concepts: tuple[ConceptMention, ...],
    quantities: tuple[QuantityMention, ...],
    concept: str,
) -> tuple[QuantityMention, ...]:
    mentions = tuple(item for item in concepts if item.concept == concept)
    money = tuple(item for item in quantities if item.kind is QuantityKind.MONEY)
    output = []
    for amount in money:
        owner = max(
            (item for item in mentions if item.char_end <= amount.char_start),
            key=lambda item: item.char_end,
            default=None,
        )
        if owner is not None and amount.char_start - owner.char_end <= 80:
            output.append(amount)
    return tuple(output)


def _clone_change_to(
    template: KPIFrame,
    value: QuantityMention,
    change: QuantityMention,
    pair_index: int,
) -> KPIFrame:
    return replace(
        template,
        frame=SemanticFrame.CHANGE_TO,
        value=round(value.value, 6),
        unit=value.unit,
        change=change.value,
        change_unit=change.unit,
        comparator="PRIOR_YEAR",
        context_trace={**template.context_trace, "semantic_pair_index": pair_index},
    )


def _clone_change_by(
    template: KPIFrame,
    value: QuantityMention,
    pair_index: int,
) -> KPIFrame:
    return replace(
        template,
        frame=SemanticFrame.CHANGE_BY,
        value=value.value,
        unit=value.unit,
        change=None,
        change_unit=None,
        comparator="PRIOR_PERIOD",
        context_trace={**template.context_trace, "semantic_pair_index": pair_index},
    )


def _postprocess_rule_frames(
    frames: tuple[KPIFrame, ...],
    concepts: tuple[ConceptMention, ...],
    quantities: tuple[QuantityMention, ...],
) -> tuple[KPIFrame, ...]:
    if not frames:
        return ()
    rule_id = frames[0].rule_id
    if rule_id in {"v273.revenue_growth_range", "v273.revenue_expected_growth_from_to"}:
        return tuple(
            replace(
                frame,
                concept="REVENUE_CHANGE_GUIDANCE",
                period_semantics=PeriodSemantics.FORECAST,
            )
            for frame in frames
        )
    if rule_id == "v273.revenue_reported_and_cc_pairs":
        template = frames[0]
        amounts = _owned_amounts(concepts, quantities, "REVENUE")
        percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
        output: list[KPIFrame] = []
        for index, (amount, changes) in enumerate(_regions(amounts, percents)):
            if len(changes) < 2:
                continue
            output.extend(
                (
                    _clone_change_to(template, amount, changes[0], index),
                    _clone_change_by(template, changes[1], index),
                )
            )
        return tuple(output)
    if rule_id == "v273.operating_income_reported_pairs":
        template = frames[0]
        amounts = _owned_amounts(concepts, quantities, "OPERATING_INCOME")
        percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
        return tuple(
            _clone_change_to(template, amount, changes[0], index)
            for index, (amount, changes) in enumerate(_regions(amounts, percents))
            if changes
        )
    if rule_id == "v273.revenue_was_increased_cc":
        template = frames[0]
        percents = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT
            and template.value is not None
            and item.char_start
            >= min(
                (
                    amount.char_end
                    for amount in quantities
                    if amount.kind is QuantityKind.MONEY
                    and abs(amount.value - template.value) <= max(1e-9, abs(template.value) * 1e-9)
                ),
                default=10**12,
            )
        )
        return (
            template,
            _clone_change_by(template, percents[1], 0),
        ) if len(percents) >= 2 else frames
    if rule_id == "v273.operating_margin_contracted_to":
        template = frames[0]
        basis_points = tuple(
            item for item in quantities if item.kind is QuantityKind.BASIS_POINTS
        )
        percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
        return tuple(
            replace(
                _clone_change_to(template, values[0], delta, index),
                polarity=Polarity(False, "contract", None, None),
            )
            for index, (delta, values) in enumerate(_regions(basis_points, percents))
            if values
        )
    return frames


def recover_v273_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V273_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v273()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v273(block.text, selected_backend)
        quantities = semantic_quantities_v273(block.text, selected_backend)
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
            processed = _postprocess_rule_frames(matched or (), concepts, quantities)
            for frame in processed:
                output.append(
                    replace(
                        frame,
                        context_trace={
                            **frame.context_trace,
                            "candidate_id": _candidate_id(frame, block, candidates),
                            "binding_eligibility": "V273_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V273_SPACY_SEMANTIC_LAW_VERIFIER",
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


def _same_block(left: KPIFrame, right: KPIFrame) -> bool:
    return left.source.sha256 == right.source.sha256 and (
        left.source_span.char_start <= right.source_span.char_start
        and right.source_span.char_end <= left.source_span.char_end
        or right.source_span.char_start <= left.source_span.char_start
        and left.source_span.char_end <= right.source_span.char_end
    )


def _values(frame: KPIFrame) -> set[float]:
    return {
        value
        for value in (frame.value, frame.change, frame.lower_value, frame.upper_value)
        if value is not None
    }


def _arr_owns_revenue(frame: KPIFrame, backend: SpacySemanticBackend) -> bool:
    if _base(frame.concept) != "REVENUE":
        return False
    text = frame.source_span.literal
    arr_ranges = tuple(
        (start, end)
        for _, start, end in backend.phrase_mentions(text, ("annual recurring revenue",))
    )
    if not arr_ranges:
        return False
    revenue_mentions = tuple(
        mention
        for mention in semantic_concepts_v273(text, backend)
        if mention.concept == "REVENUE"
    )
    return bool(revenue_mentions) and all(
        any(start <= mention.char_start and mention.char_end <= end for start, end in arr_ranges)
        for mention in revenue_mentions
    )


def resolve_frame_conflicts_v273(
    document: CanonicalDocument,
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v273()

    def superseded(frame: KPIFrame) -> bool:
        peers = tuple(
            other
            for other in recovered
            if _base(other.concept) == _base(frame.concept) and _same_block(frame, other)
        )
        if not peers:
            return False
        for other in peers:
            if other.frame is SemanticFrame.RANGE_GUIDANCE and _values(frame) & _values(other):
                return True
            if other.frame is SemanticFrame.COMPARATIVE and (
                frame.value == other.value or frame.change == other.value
            ):
                return True
            if other.frame in {
                SemanticFrame.CHANGE_TO,
                SemanticFrame.ABSOLUTE_VALUE,
                SemanticFrame.COMPOSITION,
            } and frame.value == other.value:
                return True
        return False

    prior = tuple(frame for frame in existing if not superseded(frame))
    merged = resolve_frame_conflicts_v272(document, prior, recovered, selected_backend)
    baseline_cues = (
        "guidance is based on the following",
        "guidance is based on following",
        "guidance baseline uses",
    )
    merged = tuple(
        replace(
            frame,
            concept=frame.concept.removesuffix("_GUIDANCE"),
            period_semantics=PeriodSemantics.DOCUMENT_PERIOD,
            context_trace={**frame.context_trace, "guidance_baseline": True},
        )
        if frame.rule_id in {
            "v273.revenue_colon_level",
            "v273.operating_income_colon_level",
        }
        and selected_backend.phrase_mentions(frame.source_span.literal, baseline_cues)
        else frame
        for frame in merged
    )
    without_arr = tuple(frame for frame in merged if not _arr_owns_revenue(frame, selected_backend))

    def artifact(frame: KPIFrame) -> bool:
        peers = tuple(other for other in without_arr if other is not frame and _same_block(frame, other))
        base = _base(frame.concept)
        if frame.frame is SemanticFrame.ABSOLUTE_VALUE and any(
            _base(other.concept) == base
            and other.frame is SemanticFrame.CHANGE_TO
            and other.value == frame.value
            for other in peers
        ):
            return True
        if (
            base == "REVENUE"
            and frame.frame is SemanticFrame.CHANGE_BY
            and frame.value is not None
            and abs(frame.value) >= 1_000_000
            and any(
                _base(other.concept) == base
                and other.frame is SemanticFrame.CHANGE_TO
                and other.value == frame.value
                for other in peers
            )
        ):
            return True
        if frame.frame is SemanticFrame.CHANGE_BY and any(
            _base(other.concept) == base
            and other.frame is SemanticFrame.COMPOSITION
            and other.value == frame.value
            for other in peers
        ):
            return True
        if frame.frame is SemanticFrame.CHANGE_TO and frame.change is not None:
            same_level = tuple(
                other
                for other in peers
                if _base(other.concept) == base
                and other.frame is SemanticFrame.CHANGE_TO
                and other.value == frame.value
                and other.change != frame.change
            )
            standalone_changes = {
                other.value
                for other in peers
                if _base(other.concept) == base
                and other.frame is SemanticFrame.CHANGE_BY
                and other.value is not None
                and abs(other.value) < 1_000
            }
            if same_level and frame.change in standalone_changes:
                return True
        return False

    selected: dict[tuple[object, ...], KPIFrame] = {}
    for frame in without_arr:
        if artifact(frame):
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
        current = selected.get(signature)
        if current is None or frame.rule_id.startswith("v273."):
            selected[signature] = frame
    return tuple(selected.values())
