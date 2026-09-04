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
    SemanticFrame,
    TextBlock,
)
from ..ontology import definition_for, find_concepts, resolve_scope
from ..quantities import extract_quantities
from ..runtime import _match_rule
from ..spacy_backend import SpacySemanticBackend
from ..validation import FrameValidationError
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v265_semantic_laws.arc"
V265_RULES = compile_text_rule_file(RULE_PATH)

_SEMANTIC_ALIASES = {
    "operating income margin": "OPERATING_MARGIN",
    "operating profit margin": "OPERATING_MARGIN",
    "operating margins": "OPERATING_MARGIN",
    "cash": "CASH",
}


@lru_cache(maxsize=1)
def semantic_backend_v265() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v265(
    text: str,
    backend: SpacySemanticBackend | None = None,
) -> tuple[ConceptMention, ...]:
    selected_backend = backend or semantic_backend_v265()
    candidates = list(find_concepts(text))
    for literal, start, end in selected_backend.phrase_mentions(
        text,
        tuple(_SEMANTIC_ALIASES),
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


def augment_candidates_v265(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    selected_backend = backend or semantic_backend_v265()
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
        for mention in semantic_concepts_v265(block.text, selected_backend):
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
                f"{mention.char_start}:{mention.char_end}:v265".encode()
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
                    rule_ids=("v265.spacy_phrase_alias",),
                )
            )
            seen.add(signature)
    return tuple(output)


def _candidate_id(
    frame: KPIFrame,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
) -> str | None:
    base = frame.concept.removeprefix("PRIOR_YEAR_")
    for suffix in ("_GUIDANCE", "_CHANGE"):
        base = base.removesuffix(suffix)
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


def _postprocess_rule_frame(
    frame: KPIFrame,
    block: TextBlock,
    backend: SpacySemanticBackend,
) -> KPIFrame:
    if frame.rule_id == "v265.operating_margin_expansion_range":
        frame = replace(frame, concept="OPERATING_MARGIN_CHANGE_GUIDANCE")
    if (
        frame.rule_id == "v265.operating_income_comparative"
        and frame.concept.startswith("PRIOR_YEAR_")
    ):
        prior_roles = dict(frame.context_trace.get("semantic_roles", {})).get(
            "prior", ()
        )
        prior_start = int(prior_roles[0]["start"]) if prior_roles else len(block.text)
        loss_mentions = backend.phrase_mentions(
            block.text,
            ("operating loss", "net loss", "loss of"),
        )
        if any(end <= prior_start and prior_start - end <= 48 for _, _, end in loss_mentions):
            frame = replace(
                frame,
                polarity=Polarity(
                    positive=False,
                    cue="LOSS_ROLE",
                    cue_start=max(end for _, _, end in loss_mentions if end <= prior_start),
                    cue_end=prior_start,
                ),
            )
    return frame


def recover_v265_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V265_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v265()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v265(block.text, selected_backend)
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
                frame = _postprocess_rule_frame(raw_frame, block, selected_backend)
                candidate_id = _candidate_id(frame, block, candidates)
                output.append(
                    replace(
                        frame,
                        context_trace={
                            **frame.context_trace,
                            "candidate_id": candidate_id,
                            "binding_eligibility": "V265_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V265_SPACY_SEMANTIC_LAW_VERIFIER",
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


def semantic_owner_conflict_v265(
    frame: KPIFrame,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> bool:
    if (
        frame.tier is FactTier.NARRATIVE
        and frame.value is not None
        and not frame.rule_id.startswith(("v264.", "v265."))
    ):
        return True
    base = frame.concept.removeprefix("PRIOR_YEAR_")
    for suffix in ("_GUIDANCE", "_CHANGE"):
        base = base.removesuffix(suffix)
    if base != "CAPEX":
        return False
    metric_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.block.char_start <= frame.source_span.char_start
        and frame.source_span.char_end <= candidate.block.char_end
        and candidate.metric.concept == "CAPEX"
    )
    selected_backend = backend or semantic_backend_v265()
    for candidate in metric_candidates:
        doc = selected_backend.parse(candidate.block.text)
        span = doc.char_span(
            candidate.metric.char_start,
            candidate.metric.char_end,
            alignment_mode="expand",
        )
        if span is not None and span.root.head.lemma_.casefold() == "after":
            return True
    return False


def _base(concept: str) -> str:
    result = concept.removeprefix("PRIOR_YEAR_")
    for suffix in ("_GUIDANCE", "_CHANGE"):
        result = result.removesuffix(suffix)
    return result


def resolve_frame_conflicts_v265(
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
) -> tuple[KPIFrame, ...]:
    """Prefer structurally richer semantic frames over upstream heuristics."""

    combined = (*existing, *recovered)

    def same_block(left: KPIFrame, right: KPIFrame) -> bool:
        return (
            left.source.sha256 == right.source.sha256
            and left.source_span.char_start == right.source_span.char_start
        )

    def discard(frame: KPIFrame) -> bool:
        peers = tuple(
            other
            for other in combined
            if other is not frame and same_block(frame, other)
        )
        if frame.frame is SemanticFrame.ABSOLUTE_VALUE and any(
            other.concept == frame.concept
            and other.frame is SemanticFrame.CHANGE_TO
            and other.value == frame.value
            for other in peers
        ):
            return True
        if (
            frame.frame is SemanticFrame.CHANGE_BY
            and frame.rule_id != "v265.organic_secondary_revenue_change"
            and any(
            other.concept == frame.concept
            and other.frame is SemanticFrame.CHANGE_TO
            and other.change == frame.value
            for other in peers
            )
        ):
            return True
        if (
            frame.frame is SemanticFrame.CHANGE_TO
            and not frame.rule_id.startswith("v265.")
            and any(
                other.rule_id == "v265.organic_secondary_revenue_change"
                and other.concept == frame.concept
                and other.value == frame.change
                for other in peers
            )
            and any(
                other.concept == frame.concept
                and other.frame is SemanticFrame.CHANGE_TO
                and other.value == frame.value
                and other.change != frame.change
                for other in peers
            )
        ):
            return True
        guidance = frame.concept.endswith("_GUIDANCE")
        comparable = tuple(
            other
            for other in peers
            if _base(other.concept) == _base(frame.concept)
            and other.value == frame.value
        )
        if guidance and not frame.rule_id.startswith("v265.") and any(
            not other.concept.endswith("_GUIDANCE") for other in comparable
        ):
            return True
        if not guidance and any(
            other.concept.endswith("_GUIDANCE")
            and other.rule_id.startswith("v265.")
            for other in comparable
        ):
            return True
        if not frame.rule_id.startswith("v265.") and any(
            other.rule_id.startswith("v265.")
            and other.concept == frame.concept
            and other.frame is frame.frame
            and other.value == frame.value
            and other.change == frame.change
            for other in peers
        ):
            return True
        return False

    by_signature: dict[tuple[object, ...], KPIFrame] = {}
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
        current = by_signature.get(signature)
        if current is None or frame.rule_id.startswith("v265."):
            by_signature[signature] = frame
    return tuple(by_signature.values())
