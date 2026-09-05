from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..context_validation import ContextBindingError
from ..dsl import TextRuleIR, compile_text_rule_file
from ..model import (
    FactTier,
    KPIFrame,
    PeriodSemantics,
    QuantityKind,
    QuantityMention,
    SemanticFrame,
    TextBlock,
)
from ..ontology import resolve_scope
from ..runtime import _match_rule
from ..spacy_backend import SpacySemanticBackend
from ..validation import FrameValidationError
from ..v24.model import RecallCandidate
from ..v273.semantics import (
    augment_candidates_v273,
    resolve_frame_conflicts_v273,
    semantic_concepts_v273,
    semantic_quantities_v273,
)
from .context import has_guidance_context


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v274_semantic_laws.arc"
V274_RULES = compile_text_rule_file(RULE_PATH)


@lru_cache(maxsize=1)
def semantic_backend_v274() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v274(text: str, backend: SpacySemanticBackend | None = None):
    return semantic_concepts_v273(text, backend or semantic_backend_v274())


def _number(token: object) -> float | None:
    try:
        return float(str(token.text).replace(",", ""))
    except ValueError:
        return None


def _word_percent_range_quantities(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    output = []
    for index, token in enumerate(tokens):
        value = _number(token) if token.like_num else None
        if value is None or index + 3 >= len(tokens):
            continue
        if (
            tokens[index + 1].lower_ == "to"
            and tokens[index + 2].like_num
            and tokens[index + 3].lemma_.casefold() == "percent"
        ):
            output.append(
                QuantityMention(
                    kind=QuantityKind.PERCENT,
                    value=value,
                    unit="PERCENT",
                    raw=token.text,
                    char_start=int(token.idx),
                    char_end=int(token.idx + len(token.text)),
                )
            )
    return tuple(output)


def semantic_quantities_v274(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    output = list(semantic_quantities_v273(text, backend))
    seen = {(item.char_start, item.char_end, item.kind) for item in output}
    for item in _word_percent_range_quantities(text, backend):
        signature = (item.char_start, item.char_end, item.kind)
        if signature not in seen:
            output.append(item)
            seen.add(signature)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end, item.kind)))


def augment_candidates_v274(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    return augment_candidates_v273(document, candidates, backend or semantic_backend_v274())


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


def _nearest_percent_before(
    quantities: tuple[QuantityMention, ...],
    position: int,
) -> QuantityMention | None:
    return max(
        (
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT and item.char_end <= position
        ),
        key=lambda item: item.char_end,
        default=None,
    )


def _secondary_change(
    frame: KPIFrame,
    quantity: QuantityMention,
    label: str,
) -> KPIFrame:
    return replace(
        frame,
        frame=SemanticFrame.CHANGE_BY,
        value=quantity.value,
        unit=quantity.unit,
        change=None,
        change_unit=None,
        comparator="PRIOR_PERIOD",
        context_trace={**frame.context_trace, "secondary_basis": label},
    )


def _postprocess_rule_frames(
    frames: tuple[KPIFrame, ...],
    quantities: tuple[QuantityMention, ...],
    backend: SpacySemanticBackend,
) -> tuple[KPIFrame, ...]:
    if not frames:
        return ()
    rule_id = frames[0].rule_id
    if rule_id in {
        "v274.revenue_representing_increase",
        "v274.revenue_surpassing_level",
        "v274.revenue_delivered_of_reported_fx",
    }:
        # A block can introduce an outlook and then quote a historical result.
        # These predicates are explicit realization predicates, so a broad
        # block-level guidance cue must not relabel their local clause.
        frames = tuple(
            replace(
                frame,
                concept="REVENUE",
                period_semantics=PeriodSemantics.DOCUMENT_PERIOD,
            )
            for frame in frames
        )
    if rule_id == "v274.revenue_estimated_growth_range":
        return tuple(
            replace(
                frame,
                concept="REVENUE_CHANGE_GUIDANCE",
                period_semantics=PeriodSemantics.FORECAST,
            )
            for frame in frames
        )
    basis_phrases = {
        "v274.revenue_representing_increase": (
            ("operational and organic basis", "organic basis"),
            "OPERATIONAL_ORGANIC",
        ),
        "v274.revenue_delivered_of_reported_fx": (
            ("fx-neutral basis", "fx neutral basis"),
            "FX_NEUTRAL",
        ),
    }
    if rule_id in basis_phrases:
        phrases, label = basis_phrases[rule_id]
        mentions = backend.phrase_mentions(frames[0].source_span.literal, phrases)
        secondary = _nearest_percent_before(quantities, mentions[0][1]) if mentions else None
        if secondary is not None and secondary.value != frames[0].change:
            return frames + (_secondary_change(frames[0], secondary, label),)
    return frames


def recover_v274_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V274_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v274()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v274(block.text, selected_backend)
        quantities = semantic_quantities_v274(block.text, selected_backend)
        for rule in rules:
            if (
                rule.rule_id == "v274.revenue_contextual_colon_range"
                and not has_guidance_context(block, selected_backend)
            ):
                continue
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
            for frame in _postprocess_rule_frames(
                matched or (), quantities, selected_backend
            ):
                if _base(frame.concept) == "ACTIVITY_VOLUME":
                    frame = replace(frame, tier=FactTier.CRITICAL)
                output.append(
                    replace(
                        frame,
                        context_trace={
                            **frame.context_trace,
                            "candidate_id": _candidate_id(frame, block, candidates),
                            "binding_eligibility": "V274_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V274_SPACY_SEMANTIC_LAW_VERIFIER",
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


def resolve_frame_conflicts_v274(
    document: CanonicalDocument,
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v274()

    def superseded(frame: KPIFrame) -> bool:
        peers = tuple(
            other
            for other in recovered
            if _base(other.concept) == _base(frame.concept) and _same_block(frame, other)
        )
        return any(
            frame.value == other.value
            or (other.change is not None and frame.value == other.change)
            or bool(_values(frame) & _values(other))
            for other in peers
        )

    prior = tuple(frame for frame in existing if not superseded(frame))
    merged = resolve_frame_conflicts_v273(document, prior, recovered, selected_backend)
    realized_rule_ids = {
        "v274.revenue_representing_increase",
        "v274.revenue_surpassing_level",
        "v274.revenue_delivered_of_reported_fx",
    }
    # The inherited resolver intentionally promotes nearby outlook facts.  A
    # realization predicate is a stronger clause-local signal, so restore its
    # historical identity after that broad promotion pass as well.
    merged = tuple(
        replace(
            frame,
            concept="REVENUE",
            period_semantics=PeriodSemantics.DOCUMENT_PERIOD,
            context_trace={**frame.context_trace, "realized_predicate_override": True},
        )
        if frame.rule_id in realized_rule_ids
        else frame
        for frame in merged
    )

    def ownership_error(frame: KPIFrame) -> bool:
        peers = tuple(other for other in merged if other is not frame and _same_block(frame, other))
        if frame.frame is SemanticFrame.ABSOLUTE_VALUE and any(
            _base(other.concept) == _base(frame.concept)
            and other.frame in {SemanticFrame.CHANGE_TO, SemanticFrame.COMPARATIVE}
            and other.value == frame.value
            for other in peers
        ):
            return True
        if frame.frame is SemanticFrame.CHANGE_BY and any(
            _base(other.concept) == _base(frame.concept)
            and other.frame is SemanticFrame.CHANGE_TO
            and other.change == frame.value
            for other in peers
        ):
            return True
        if _base(frame.concept) == "OPERATING_MARGIN" and frame.frame is SemanticFrame.CHANGE_BY:
            return any(
                _base(other.concept) == "OPERATING_INCOME"
                and other.frame is SemanticFrame.CHANGE_TO
                and other.change == frame.value
                for other in peers
            ) and any(
                _base(other.concept) == "OPERATING_MARGIN"
                and other.frame is SemanticFrame.ABSOLUTE_VALUE
                for other in peers
            )
        return False

    unique: dict[tuple[object, ...], KPIFrame] = {}
    for frame in merged:
        if ownership_error(frame):
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
        if current is None or frame.rule_id.startswith("v274."):
            unique[signature] = frame
    return tuple(unique.values())
