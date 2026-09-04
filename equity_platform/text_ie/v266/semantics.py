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
from ..ontology import definition_for, find_concepts, resolve_scope
from ..quantities import extract_quantities
from ..runtime import _match_rule
from ..spacy_backend import SpacySemanticBackend
from ..validation import FrameValidationError
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v266_semantic_laws.arc"
V266_RULES = compile_text_rule_file(RULE_PATH)

_SEMANTIC_ALIASES = {
    "operating income margin rate": "OPERATING_MARGIN",
    "adjusted operating income margin rate": "OPERATING_MARGIN",
    "operating income margin": "OPERATING_MARGIN",
    "operating profit margin": "OPERATING_MARGIN",
    "operating margins": "OPERATING_MARGIN",
    "operating profits": "OPERATING_INCOME",
    "enterprise cash": "CASH",
    "cash": "CASH",
}


@lru_cache(maxsize=1)
def semantic_backend_v266() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v266(
    text: str,
    backend: SpacySemanticBackend | None = None,
) -> tuple[ConceptMention, ...]:
    selected_backend = backend or semantic_backend_v266()
    candidates = list(find_concepts(text))
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


def augment_candidates_v266(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    selected_backend = backend or semantic_backend_v266()
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
        for mention in semantic_concepts_v266(block.text, selected_backend):
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
                f"{mention.char_start}:{mention.char_end}:v266".encode()
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
                    rule_ids=("v266.spacy_phrase_alias",),
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
    base = _base(frame.concept)
    matching = tuple(
        candidate
        for candidate in candidates
        if candidate.block.char_start == block.char_start
        and candidate.metric.concept == base
    )
    if not matching:
        return None
    return min(
        matching,
        key=lambda candidate: candidate.metric.char_start,
    ).candidate_id


def _postprocess_rule_frame(frame: KPIFrame) -> KPIFrame:
    if frame.rule_id == "v266.prior_margin_reference_guidance":
        return replace(
            frame,
            concept="PRIOR_YEAR_OPERATING_MARGIN",
            frame=SemanticFrame.COMPARATIVE,
        )
    return frame


def recover_v266_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V266_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v266()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v266(block.text, selected_backend)
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
                            "binding_eligibility": "V266_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V266_SPACY_SEMANTIC_LAW_VERIFIER",
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


def _forward_evidence_precedes_value(
    frame: KPIFrame,
    backend: SpacySemanticBackend,
) -> bool:
    text = frame.source_span.literal
    if backend.phrase_mentions(text, ("guidance", "outlook", "forecast")):
        return True
    expected = tuple(token for token in backend.parse(text) if token.lemma_ == "expect")
    if not expected or frame.value is None:
        return False
    matching_values = tuple(
        item
        for item in extract_quantities(text)
        if abs(item.value - frame.value) <= max(1e-9, abs(frame.value) * 1e-9)
    )
    return any(cue.idx < value.char_start for cue in expected for value in matching_values)


def resolve_frame_conflicts_v266(
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    """Fail closed on unproved critical bindings and prefer typed V2.6.6 roles."""

    selected_backend = backend or semantic_backend_v266()
    combined = (*existing, *recovered)

    def same_block(left: KPIFrame, right: KPIFrame) -> bool:
        return (
            left.source.sha256 == right.source.sha256
            and left.source_span.char_start == right.source_span.char_start
        )

    def discard(frame: KPIFrame) -> bool:
        peers = tuple(
            other for other in combined if other is not frame and same_block(frame, other)
        )
        semantic_peers = tuple(
            other for other in peers if other.rule_id.startswith("v266.")
        )
        if frame.rule_id.startswith("v266."):
            return False
        if frame.tier is FactTier.NARRATIVE and frame.value is not None:
            return True
        if frame.concept.endswith("_GUIDANCE") and not _forward_evidence_precedes_value(
            frame, selected_backend
        ):
            return True
        if frame.concept.endswith("_GUIDANCE") and any(
            _base(other.concept) == _base(frame.concept)
            and other.concept.endswith("_GUIDANCE")
            for other in semantic_peers
        ):
            return True
        if any(
            other.concept == frame.concept
            and other.frame is frame.frame
            and other.value == frame.value
            for other in semantic_peers
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
        if (
            _base(frame.concept) == "OPERATING_INCOME"
            and any(
                other.rule_id.startswith("v266.operating_margin_")
                and other.value == frame.value
                for other in semantic_peers
            )
        ):
            return True
        if frame.rule_id == "v261.kpi_change" and frame.frame is SemanticFrame.CHANGE_TO:
            trusted = {
                (other.value, other.change)
                for other in peers
                if other.rule_id == "v26.kpi_change"
                and other.frame is SemanticFrame.CHANGE_TO
            }
            if len(trusted) >= 2 and (frame.value, frame.change) not in trusted:
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
        if current is None or frame.rule_id.startswith("v266."):
            unique[signature] = frame
    return tuple(unique.values())
