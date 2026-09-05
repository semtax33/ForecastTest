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
from ..v275.semantics import (
    augment_candidates_v275,
    resolve_frame_conflicts_v275,
    semantic_backend_v275,
    semantic_concepts_v275,
    semantic_quantities_v275,
)


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v276_semantic_laws.arc"
V276_RULES = compile_text_rule_file(RULE_PATH)

_ALIASES = {
    "revpar": "REVENUE",
    "underwriting income": "OPERATING_INCOME",
    "fee income": "REVENUE",
    "noninterest income": "REVENUE",
    "net interest income": "REVENUE",
    "investment banking transactions": "ACTIVITY_VOLUME",
}


@lru_cache(maxsize=1)
def semantic_backend_v276() -> SpacySemanticBackend:
    return semantic_backend_v275()


def semantic_concepts_v276(
    text: str,
    backend: SpacySemanticBackend | None = None,
) -> tuple[ConceptMention, ...]:
    selected_backend = backend or semantic_backend_v276()
    output = list(semantic_concepts_v275(text, selected_backend))
    for phrase, concept in _ALIASES.items():
        output.extend(
            ConceptMention(concept, literal, start, end)
            for literal, start, end in selected_backend.phrase_mentions(text, (phrase,))
        )
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(
        sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept))
    )


def semantic_quantities_v276(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    output = list(semantic_quantities_v275(text, backend))
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    for index, token in enumerate(tokens):
        if not token.like_num:
            continue
        tail = tokens[index + 1 : index + 5]
        if not any(item.lemma_.casefold() == "transaction" for item in tail):
            continue
        try:
            value = float(token.text.replace(",", ""))
        except ValueError:
            continue
        output.append(
            QuantityMention(
                kind=QuantityKind.COUNT,
                value=value,
                unit="COUNT",
                raw=token.text,
                char_start=int(token.idx),
                char_end=int(token.idx + len(token.text)),
            )
        )
    unique = {(item.kind, item.value, item.char_start, item.char_end): item for item in output}
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.kind)))


def augment_candidates_v276(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    selected_backend = backend or semantic_backend_v276()
    output = list(augment_candidates_v275(document, candidates, selected_backend))
    seen = {
        (item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end)
        for item in output
    }
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v276(block.text, selected_backend)
        for mention in semantic_concepts_v276(block.text, selected_backend):
            signature = (block.char_start, mention.concept, mention.char_start, mention.char_end)
            if signature in seen or mention.alias.casefold() not in _ALIASES:
                continue
            allowed = set(definition_for(mention.concept).quantity_kinds) | {
                QuantityKind.PERCENT,
                QuantityKind.BASIS_POINTS,
                QuantityKind.COUNT,
            }
            compatible = tuple(
                item
                for item in quantities
                if item.kind in allowed and abs(item.char_start - mention.char_start) <= 420
            )
            if not compatible:
                continue
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:"
                f"{mention.char_start}:{mention.char_end}:v276".encode()
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
                    rule_ids=("v276.spacy_semantic_alias",),
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
    matches = tuple(
        candidate
        for candidate in candidates
        if candidate.block.char_start == block.char_start
        and candidate.metric.concept == _base(frame.concept)
    )
    return min(matches, key=lambda item: item.metric.char_start).candidate_id if matches else None


def _same_block(left: KPIFrame, right: KPIFrame) -> bool:
    return left.source.sha256 == right.source.sha256 and (
        left.source_span.char_start <= right.source_span.char_start
        and right.source_span.char_end <= left.source_span.char_end
        or right.source_span.char_start <= left.source_span.char_start
        and left.source_span.char_end <= right.source_span.char_end
    )


def _revpar_frames(
    template: KPIFrame,
    block: TextBlock,
    concepts: tuple[ConceptMention, ...],
    quantities: tuple[QuantityMention, ...],
    backend: SpacySemanticBackend,
) -> tuple[KPIFrame, ...]:
    parsed = backend.parse(block.text)
    output: list[KPIFrame] = []
    revpars = tuple(item for item in concepts if item.alias.casefold() == "revpar")
    for index, mention in enumerate(revpars):
        token = next(
            (item for item in parsed if item.idx <= mention.char_start < item.idx + len(item.text)),
            None,
        )
        if token is None:
            continue
        sentence_end = int(token.sent.end_char)
        next_start = revpars[index + 1].char_start if index + 1 < len(revpars) else sentence_end
        values = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT
            and mention.char_end <= item.char_start < min(sentence_end, next_start)
        )
        if not values:
            continue
        value = min(values, key=lambda item: item.char_start)
        trend = next(
            (
                item
                for item in parsed
                if mention.char_end <= item.idx < value.char_start
                and item.lemma_.casefold() in {"increase", "rise", "decline"}
            ),
            None,
        )
        if trend is None:
            continue
        output.append(
            replace(
                template,
                concept="REVENUE",
                frame=SemanticFrame.CHANGE_BY,
                value=value.value,
                unit=value.unit,
                change=None,
                change_unit=None,
                comparator="PRIOR_PERIOD",
                polarity=Polarity(trend.lemma_.casefold() != "decline", trend.text, None, None),
            )
        )
    return tuple(output)


def recover_v276_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V276_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v276()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v276(block.text, selected_backend)
        quantities = semantic_quantities_v276(block.text, selected_backend)
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
            frames = matched or ()
            if rule.rule_id == "v276.revpar_change" and frames:
                frames = _revpar_frames(frames[0], block, concepts, quantities, selected_backend)
            for frame in frames:
                if _base(frame.concept) in {"ACTIVITY_VOLUME", "CAPEX"}:
                    frame = replace(frame, tier=FactTier.CRITICAL)
                output.append(
                    replace(
                        frame,
                        context_trace={
                            **frame.context_trace,
                            "candidate_id": _candidate_id(frame, block, candidates),
                            "binding_eligibility": "V276_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V276_SPACY_SEMANTIC_LAW_VERIFIER",
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


def _production_misbound(
    frame: KPIFrame,
    backend: SpacySemanticBackend,
) -> bool:
    if _base(frame.concept) != "PRODUCTION" or frame.value is None:
        return False
    text = frame.source_span.literal
    concepts = tuple(item for item in semantic_concepts_v276(text, backend) if item.concept == "PRODUCTION")
    percents = tuple(
        item for item in semantic_quantities_v276(text, backend) if item.kind is QuantityKind.PERCENT
    )
    matched = tuple(item for item in percents if item.value == frame.value)
    if not concepts or not matched:
        return False
    bound_distance = min(abs(item.char_start - concept.char_end) for item in matched for concept in concepts)
    nearest_distance = min(abs(item.char_start - concept.char_end) for item in percents for concept in concepts)
    return bound_distance > nearest_distance


def resolve_frame_conflicts_v276(
    document: CanonicalDocument,
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v276()
    merged = resolve_frame_conflicts_v275(document, existing, recovered, selected_backend)

    def ownership_error(frame: KPIFrame) -> bool:
        peers = tuple(other for other in merged if other is not frame and _same_block(frame, other))
        if _production_misbound(frame, selected_backend):
            return True
        if (
            _base(frame.concept) == "REVENUE"
            and frame.frame is SemanticFrame.ABSOLUTE_VALUE
            and frame.rule_id == "v262.explicit_revenue_level"
            and any(
                _base(other.concept) == "REVENUE"
                and other.frame is SemanticFrame.CHANGE_BY
                and other.value == frame.value
                for other in peers
            )
        ):
            return True
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
        if current is None or frame.rule_id.startswith("v276."):
            unique[signature] = frame
    return tuple(unique.values())
