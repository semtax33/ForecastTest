from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..context_validation import ContextBindingError
from ..dsl import TextRuleIR, compile_text_rule_file
from ..model import FactTier, KPIFrame, QuantityKind, QuantityMention, SemanticFrame, TextBlock
from ..ontology import resolve_scope
from ..runtime import _match_rule
from ..spacy_backend import SpacySemanticBackend
from ..validation import FrameValidationError
from ..v24.model import RecallCandidate
from ..v269.semantics import (
    augment_candidates_v269,
    semantic_concepts_v269,
    semantic_quantities_v269,
)


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v270_semantic_laws.arc"
V270_RULES = compile_text_rule_file(RULE_PATH)


@lru_cache(maxsize=1)
def semantic_backend_v270() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v270(text: str, backend: SpacySemanticBackend | None = None):
    return semantic_concepts_v269(text, backend or semantic_backend_v270())


def _share_count_quantities(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    if not backend.phrase_mentions(text, ("shares outstanding",)):
        return ()
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    scales = {"thousand": 1_000.0, "million": 1_000_000.0, "billion": 1_000_000_000.0}
    output: list[QuantityMention] = []
    for index, token in enumerate(tokens[:-1]):
        scale = scales.get(tokens[index + 1].lower_)
        if not token.like_num or scale is None:
            continue
        try:
            value = float(token.text.replace(",", "")) * scale
        except ValueError:
            continue
        end_token = tokens[index + 1]
        output.append(
            QuantityMention(
                kind=QuantityKind.COUNT,
                value=value,
                unit="COUNT",
                raw=text[int(token.idx) : int(end_token.idx + len(end_token.text))],
                char_start=int(token.idx),
                char_end=int(end_token.idx + len(end_token.text)),
            )
        )
    return tuple(output)


def semantic_quantities_v270(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    output = list(semantic_quantities_v269(text, backend))
    seen = {(item.char_start, item.char_end, item.kind) for item in output}
    for item in _share_count_quantities(text, backend):
        signature = (item.char_start, item.char_end, item.kind)
        if signature not in seen:
            output.append(item)
            seen.add(signature)
    return tuple(sorted(output, key=lambda item: (item.char_start, item.char_end)))


def augment_candidates_v270(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    # V2.6.9 already reaches every semantic concept in the disclosed set.
    return augment_candidates_v269(document, candidates, backend or semantic_backend_v270())


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
    if _base(frame.concept) == "ACTIVITY_VOLUME" and frame.value is not None:
        return replace(frame, tier=FactTier.CRITICAL)
    return frame


def recover_v270_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V270_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v270()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v270(block.text, selected_backend)
        quantities = semantic_quantities_v270(block.text, selected_backend)
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
                            "binding_eligibility": "V270_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V270_SPACY_SEMANTIC_LAW_VERIFIER",
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


def resolve_frame_conflicts_v270(
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v270()
    # ``existing`` is the already-adjudicated V269 output.  Sending it back
    # through every historical conflict resolver makes an older version judge
    # facts emitted by a newer version and can silently erase valid frames
    # (for example V269 revenue-range guidance).  Version boundaries are
    # ownership boundaries: V270 may suppress prior facts only with a V270 law.
    prior = existing

    def overlaps_span(left: KPIFrame, right: KPIFrame) -> bool:
        return left.source.sha256 == right.source.sha256 and (
            left.source_span.char_start < right.source_span.char_end
            and right.source_span.char_start < left.source_span.char_end
        )

    def same_block(left: KPIFrame, right: KPIFrame) -> bool:
        return overlaps_span(left, right) and (
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
        text = frame.source_span.literal
        folded = text.casefold()
        peers = tuple(other for other in recovered if same_block(frame, other))
        same_metric = tuple(
            other for other in peers if _base(other.concept) == _base(frame.concept)
        )
        if any(values(frame) & values(other) for other in same_metric):
            return True
        if _base(frame.concept) == "OPERATING_MARGIN" and any(
            other.rule_id == "v270.projected_operating_margin" for other in same_metric
        ):
            return True
        if (
            _base(frame.concept) == "OPERATING_INCOME"
            and selected_backend.phrase_mentions(
                text,
                (
                    "income from operations included share-based compensation expense",
                    "operating income included share-based compensation expense",
                ),
            )
        ):
            return True
        if (
            _base(frame.concept) == "REVENUE"
            and selected_backend.phrase_mentions(text, ("net revenues included",))
            and selected_backend.phrase_mentions(
                text, ("mark-to-market gains", "mark to market gains")
            )
        ):
            return True
        if (
            _base(frame.concept) == "REVENUE"
            and frame.value is not None
            and abs(frame.value) < 100.0
            and "diluted eps" in folded
            and selected_backend.phrase_mentions(
                text, ("gross margin", "operating margin")
            )
        ):
            return True
        if frame.frame is SemanticFrame.CHANGE_TO and frame.change is None and any(
            other.frame is SemanticFrame.COMPARATIVE
            and _base(other.concept) == _base(frame.concept)
            and frame.value == other.value
            and same_block(frame, other)
            for other in prior
            if other is not frame
        ):
            return True
        return False

    ordered = tuple(frame for frame in prior if not discard_prior(frame)) + recovered
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
                and overlaps_span(current, frame)
            ),
            None,
        )
        if duplicate_index is None:
            selected.append(frame)
        elif frame.rule_id.startswith("v270."):
            selected[duplicate_index] = frame
    return tuple(selected)
