from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from equity_platform.documents import CanonicalDocument
from equity_platform.paths import PROJECT_ROOT

from ..context_validation import ContextBindingError
from ..dsl import TextRuleIR, compile_text_rule_file
from ..model import KPIFrame, SemanticFrame, TextBlock
from ..ontology import find_concepts, resolve_scope
from ..quantities import extract_quantities
from ..runtime import _match_rule
from ..spacy_backend import SpacySemanticBackend
from ..validation import FrameValidationError
from ..v24.model import RecallCandidate


RULE_PATH = (
    PROJECT_ROOT / "configs/parser_rules/text_ie/v264_semantic_laws.arc"
)
V264_RULES = compile_text_rule_file(RULE_PATH)


@lru_cache(maxsize=1)
def semantic_backend_v264() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def _candidate_id(
    frame: KPIFrame,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
) -> str | None:
    base = (
        frame.concept.removeprefix("PRIOR_YEAR_")
        .removesuffix("_GUIDANCE")
        .removesuffix("_CHANGE")
    )
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
        key=lambda candidate: abs(
            candidate.metric.char_start
            - min(
                (
                    int(role["start"])
                    for roles in dict(
                        frame.context_trace.get("semantic_roles", {})
                    ).values()
                    for role in roles
                    if role.get("value") == base
                ),
                default=candidate.metric.char_start,
            )
        ),
    ).candidate_id


def recover_v264_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V264_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v264()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = find_concepts(block.text)
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
            if not matched:
                continue
            for frame in matched:
                candidate_id = _candidate_id(frame, block, candidates)
                output.append(
                    replace(
                        frame,
                        context_trace={
                            **frame.context_trace,
                            "candidate_id": candidate_id,
                            "binding_eligibility": "V264_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V264_SPACY_SEMANTIC_LAW_VERIFIER",
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


def semantic_owner_conflict(
    frame: KPIFrame,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> bool:
    base_concept = frame.concept.removeprefix("PRIOR_YEAR_")
    candidate_id = frame.context_trace.get("candidate_id")
    candidate = next(
        (item for item in candidates if item.candidate_id == candidate_id),
        None,
    )
    if candidate is None:
        return False
    selected_backend = backend or semantic_backend_v264()
    doc = selected_backend._parse(candidate.block.text)
    span = doc.char_span(
        candidate.metric.char_start,
        candidate.metric.char_end,
        alignment_mode="expand",
    )
    if span is None:
        return False
    if (
        base_concept == "REVENUE"
        and candidate.metric.alias.casefold() in {"sale", "sales"}
        and any(
            token.lemma_.casefold() in {"cost", "expense"}
            for token in (span.root, *tuple(span.root.subtree))
        )
    ):
        return True
    matching_values = tuple(
        quantity
        for quantity in extract_quantities(candidate.block.text)
        if frame.value == quantity.value
        and quantity.char_end <= candidate.metric.char_start
    )
    causal_ancestors = {
        "attribute",
        "create",
        "drive",
        "offset",
        "reflect",
        "result",
    }
    if matching_values and any(
        token.lemma_.casefold() in causal_ancestors
        for token in (span.root, *tuple(span.root.ancestors))
    ):
        return True
    forward_values = tuple(
        quantity
        for quantity in extract_quantities(candidate.block.text)
        if frame.value == quantity.value
        and candidate.metric.char_end <= quantity.char_start
    )
    intervening_owner = any(
        mention.concept != base_concept
        and candidate.metric.char_end <= mention.char_start < quantity.char_start
        for quantity in forward_values
        for mention in find_concepts(candidate.block.text)
    )
    return bool(
        intervening_owner
    )


semantic_owner_is_cost = semantic_owner_conflict


def resolve_frame_conflicts(
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
) -> tuple[KPIFrame, ...]:
    """Apply frame-level specificity precedence without issuer exceptions."""

    def same_block(left: KPIFrame, right: KPIFrame) -> bool:
        return (
            left.source.sha256 == right.source.sha256
            and left.source_span.char_start == right.source_span.char_start
            and abs(left.source_span.char_end - right.source_span.char_end) <= 8
        )

    def semantic_supersedes(candidate: KPIFrame) -> bool:
        return any(
            same_block(replacement, candidate)
            and replacement.concept == candidate.concept
            and replacement.value == candidate.value
            and (
                (
                    candidate.frame is SemanticFrame.ABSOLUTE_VALUE
                    and replacement.frame
                    in {SemanticFrame.CHANGE_BY, SemanticFrame.CHANGE_TO}
                )
                or (
                    candidate.frame is replacement.frame
                    and candidate.polarity.positive
                    is not replacement.polarity.positive
                )
            )
            for replacement in recovered
        )

    retained_existing = tuple(
        frame for frame in existing if not semantic_supersedes(frame)
    )
    retained_recovered = tuple(
        frame
        for frame in recovered
        if not (
            frame.frame is SemanticFrame.CHANGE_BY
            and any(
                prior.concept == frame.concept
                and same_block(prior, frame)
                and prior.frame is SemanticFrame.CHANGE_TO
                and prior.change == frame.value
                for prior in retained_existing
            )
        )
    )
    by_signature: dict[tuple[object, ...], KPIFrame] = {}
    for frame in (*retained_existing, *retained_recovered):
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
        if current is None or frame.rule_id.startswith("v264."):
            by_signature[signature] = frame
    return tuple(by_signature.values())
