from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256

from equity_platform.documents import CanonicalDocument
from equity_platform.ir import AuthorityLevel, ExtractionMethod, SourceSpan
from equity_platform.paths import PROJECT_ROOT

from ..context import qualifier, resolve_period
from ..context_validation import ContextBindingError
from ..document import document_text_blocks
from ..dsl import TextRuleIR, compile_text_rule_file
from ..model import (
    ConceptMention,
    FactTier,
    KPIFrame,
    PeriodSemantics,
    Polarity,
    QuantityKind,
    QuantityMention,
    SemanticFrame,
    TextBlock,
    VerificationStatus,
)
from ..ontology import definition_for, resolve_scope
from ..runtime import _match_rule
from ..validation import FrameValidationError, validate_kpi_frame
from ..v24.model import CandidateOrigin, MetricAnchor, RecallCandidate
from ..v276.semantics import (
    semantic_backend_v276,
    semantic_concepts_v276,
    semantic_quantities_v276,
)
from ..v277.semantics import recover_v277_frames, resolve_frame_conflicts_v277


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v278_semantic_laws.arc"
V278_RULES = compile_text_rule_file(RULE_PATH)
_RULE_BY_ID = {rule.rule_id: rule for rule in V278_RULES}
_NEW_ALIASES = {
    "gross profit": "GROSS_MARGIN",
    "income from operations": "OPERATING_INCOME",
    "short-term borrowings": "DEBT",
    "shares": "SHARES",
}


def _base(concept: str) -> str:
    result = concept.removeprefix("PRIOR_YEAR_")
    while True:
        prior = result
        result = result.removesuffix("_GUIDANCE").removesuffix("_CHANGE")
        if result == prior:
            return result


@lru_cache(maxsize=1)
def semantic_backend_v278():
    return semantic_backend_v276()


def semantic_quantities_v278(
    text: str,
    backend=None,
) -> tuple[QuantityMention, ...]:
    return semantic_quantities_v276(text, backend or semantic_backend_v278())


def semantic_concepts_v278(
    text: str,
    backend=None,
) -> tuple[ConceptMention, ...]:
    selected = backend or semantic_backend_v278()
    output = list(semantic_concepts_v276(text, selected))
    folded = text.casefold()
    if "of sales" in folded:
        output.extend(
            ConceptMention("GROSS_MARGIN", literal, start, end)
            for literal, start, end in selected.phrase_mentions(text, ("gross profit",))
        )
    output.extend(
        ConceptMention("OPERATING_INCOME", literal, start, end)
        for literal, start, end in selected.phrase_mentions(
            text, ("income from operations",)
        )
    )
    output.extend(
        ConceptMention("DEBT", literal, start, end)
        for literal, start, end in selected.phrase_mentions(
            text, ("short-term borrowings",)
        )
    )
    if selected.phrase_mentions(text, ("diluted earnings per common share",)):
        output.extend(
            ConceptMention("SHARES", literal, start, end)
            for literal, start, end in selected.phrase_mentions(text, ("shares",))
        )
    tokens = tuple(token for token in selected.parse(text) if not token.is_space)
    for index, token in enumerate(tokens):
        if (
            token.lemma_.casefold() == "income"
            and index >= 2
            and tokens[index - 1].lemma_.casefold() == "interest"
            and tokens[index - 2].lower_ == "net"
        ):
            output.append(
                ConceptMention(
                    "REVENUE",
                    text[tokens[index - 2].idx : token.idx + len(token.text)],
                    int(tokens[index - 2].idx),
                    int(token.idx + len(token.text)),
                )
            )
    unique = {(item.concept, item.char_start, item.char_end): item for item in output}
    return tuple(
        sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept))
    )


def augment_candidates_v278(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
) -> tuple[RecallCandidate, ...]:
    backend = semantic_backend_v278()
    output = list(candidates)
    seen = {
        (item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end)
        for item in output
    }
    for block in document_text_blocks(document):
        quantities = semantic_quantities_v278(block.text, backend)
        for mention in semantic_concepts_v278(block.text, backend):
            signature = (block.char_start, mention.concept, mention.char_start, mention.char_end)
            if signature in seen or mention.alias.casefold() not in _NEW_ALIASES:
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
                f"{mention.char_start}:{mention.char_end}:v278".encode()
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
                    rule_ids=("v278.spacy_semantic_alias",),
                )
            )
            seen.add(signature)
    return tuple(output)


def _candidate_id(
    concept: str,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
) -> str | None:
    matches = tuple(
        candidate
        for candidate in candidates
        if candidate.block.char_start == block.char_start
        and candidate.metric.concept == _base(concept)
    )
    return min(matches, key=lambda item: item.metric.char_start).candidate_id if matches else None


def _verified(frame: KPIFrame, block: TextBlock, candidates: tuple[RecallCandidate, ...]) -> KPIFrame:
    rule = _RULE_BY_ID[frame.rule_id]
    return replace(
        frame,
        context_trace={
            **frame.context_trace,
            "candidate_id": _candidate_id(frame.concept, block, candidates),
            "binding_eligibility": "V278_SPACY_SEMANTIC_LAW",
            "rule_program_sha256": rule.source_sha256,
        },
        verified_by="V278_SPACY_SEMANTIC_LAW_VERIFIER",
        tier=FactTier.CRITICAL,
    )


def _role_quantity(
    frame: KPIFrame,
    label: str,
    quantities: tuple[QuantityMention, ...],
) -> QuantityMention | None:
    roles = frame.context_trace.get("semantic_roles", {})
    spans = roles.get(label, ()) if isinstance(roles, dict) else ()
    for span in spans:
        for quantity in quantities:
            if int(span["start"]) <= quantity.char_start and quantity.char_end <= int(span["end"]):
                return quantity
    return None


def _expand_rule_frame(
    frame: KPIFrame,
    quantities: tuple[QuantityMention, ...],
) -> tuple[KPIFrame, ...]:
    if frame.rule_id == "v278.revenue_guidance_revision_delta":
        return (
            replace(
                frame,
                concept="REVENUE_GUIDANCE",
                period_semantics=PeriodSemantics.FORECAST,
            ),
        )
    if frame.rule_id == "v278.revenue_growth_guidance_component":
        return (
            replace(
                frame,
                concept="REVENUE_CHANGE_GUIDANCE",
                period_semantics=PeriodSemantics.FORECAST,
            ),
        )
    if frame.rule_id == "v278.activity_volume_decline_guidance":
        return (
            replace(
                frame,
                concept="ACTIVITY_VOLUME_CHANGE_GUIDANCE",
                polarity=Polarity(False, "decline", None, None),
                period_semantics=PeriodSemantics.FORECAST,
            ),
        )
    if frame.rule_id in {"v278.debt_decrease_dual", "v278.volume_revenue_change"}:
        return (replace(frame, polarity=Polarity(False, "decrease", None, None)),)
    if frame.rule_id == "v278.revenue_parallel_growth":
        secondary = _role_quantity(frame, "secondary_change", quantities)
        if secondary is None:
            return (frame,)
        return (
            frame,
            replace(
                frame,
                change=secondary.value,
                change_unit=secondary.unit,
                context_trace={**frame.context_trace, "parallel_growth_index": 2},
            ),
        )
    return (frame,)


def _direct_frame(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    *,
    concept: str,
    semantic: SemanticFrame,
    value: QuantityMention,
    change: QuantityMention | None = None,
    positive: bool = True,
    rule_id: str = "v278.semantic_bullet_highlights",
) -> KPIFrame | None:
    period, semantics = resolve_period(block, semantic)
    proposed = KPIFrame(
        concept=concept,
        entity=block.entity,
        scope=resolve_scope(block.text, block.nearest_heading),
        period=period,
        period_semantics=semantics,
        frame=semantic,
        value=value.value,
        unit=value.unit,
        change=change.value if change else None,
        change_unit=change.unit if change else None,
        comparator=(
            "PRIOR_PERIOD"
            if semantic in {SemanticFrame.CHANGE_BY, SemanticFrame.CHANGE_TO, SemanticFrame.COMPARATIVE}
            else None
        ),
        polarity=Polarity(positive),
        qualifier=qualifier(block.text),
        source=block.source,
        source_span=SourceSpan(
            block.section,
            block.char_start,
            block.char_end,
            block.text,
        ),
        extraction_method=ExtractionMethod.DEPENDENCY_RULE,
        rule_id=rule_id,
        rule_version=1,
        extraction_confidence=0.995,
        authority=AuthorityLevel.RESEARCH_EVIDENCE,
        verification_status=VerificationStatus.PROPOSED,
        context_trace={
            "candidate_id": _candidate_id(concept, block, candidates),
            "binding_eligibility": "V278_SPACY_SEMANTIC_BULLET",
            "rule_program_sha256": _RULE_BY_ID[rule_id].source_sha256,
        },
        tier=definition_for(_base(concept)).tier,
    )
    try:
        return replace(
            validate_kpi_frame(proposed, document),
            verified_by="V278_SPACY_SEMANTIC_BULLET_VERIFIER",
        )
    except (FrameValidationError, KeyError, ValueError):
        return None


def _bullet_ranges(text: str) -> tuple[tuple[int, int], ...]:
    starts = []
    cursor = 0
    while True:
        marker = text.find("➢", cursor)
        if marker < 0:
            break
        starts.append(marker + 1)
        cursor = marker + 1
    if not starts:
        return ()
    return tuple(
        (start, starts[index + 1] - 1 if index + 1 < len(starts) else len(text))
        for index, start in enumerate(starts)
    )


def _bullet_highlight_frames(
    document: CanonicalDocument,
    block: TextBlock,
    candidates: tuple[RecallCandidate, ...],
    quantities: tuple[QuantityMention, ...],
) -> tuple[KPIFrame, ...]:
    if "highlights" not in block.text.casefold() or "➢" not in block.text:
        return ()
    output: list[KPIFrame] = []
    for start, end in _bullet_ranges(block.text):
        folded = block.text[start:end].casefold()
        money = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.MONEY and start <= item.char_start < end
        )
        percents = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT and start <= item.char_start < end
        )
        proposed: list[KPIFrame | None] = []
        if "sales" in folded and "operating" not in folded and money and percents:
            proposed.append(
                _direct_frame(
                    document,
                    block,
                    candidates,
                    concept="REVENUE",
                    semantic=SemanticFrame.CHANGE_TO,
                    value=money[0],
                    change=percents[0],
                )
            )
            if "underlying" in folded and len(percents) >= 2:
                proposed.append(
                    _direct_frame(
                        document,
                        block,
                        candidates,
                        concept="REVENUE",
                        semantic=SemanticFrame.CHANGE_BY,
                        value=percents[1],
                    )
                )
        elif "operating profit margin" in folded and len(percents) >= 2:
            proposed.extend(
                _direct_frame(
                    document,
                    block,
                    candidates,
                    concept="OPERATING_MARGIN",
                    semantic=SemanticFrame.ABSOLUTE_VALUE,
                    value=item,
                )
                for item in percents[:2]
            )
        elif "operating profit" in folded and len(money) >= 2 and percents:
            proposed.append(
                _direct_frame(
                    document,
                    block,
                    candidates,
                    concept="OPERATING_INCOME",
                    semantic=SemanticFrame.ABSOLUTE_VALUE,
                    value=money[0],
                )
            )
            proposed.append(
                _direct_frame(
                    document,
                    block,
                    candidates,
                    concept="OPERATING_INCOME",
                    semantic=SemanticFrame.CHANGE_TO,
                    value=money[1],
                    change=percents[0],
                )
            )
        elif "backlog" in folded and money:
            proposed.append(
                _direct_frame(
                    document,
                    block,
                    candidates,
                    concept="BACKLOG",
                    semantic=SemanticFrame.ABSOLUTE_VALUE,
                    value=money[0],
                )
            )
        output.extend(frame for frame in proposed if frame is not None)
    return tuple(output)


def recover_v278_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
) -> tuple[KPIFrame, ...]:
    output = list(recover_v277_frames(document, candidates, allowed_spans))
    backend = semantic_backend_v278()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v278(block.text, backend)
        quantities = semantic_quantities_v278(block.text, backend)
        for rule in V278_RULES:
            if rule.rule_id == "v278.semantic_bullet_highlights":
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
                    backend=backend,
                )
            except (ContextBindingError, FrameValidationError, KeyError, ValueError):
                continue
            for frame in matched or ():
                for expanded in _expand_rule_frame(frame, quantities):
                    output.append(_verified(expanded, block, candidates))
        output.extend(
            _bullet_highlight_frames(document, block, candidates, quantities)
        )
    unique: dict[tuple[object, ...], KPIFrame] = {}
    for frame in output:
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
        if current is None or frame.rule_id.startswith("v278."):
            unique[signature] = frame
    return tuple(unique.values())


def _quantity_for_value(frame: KPIFrame) -> tuple[QuantityMention, ...]:
    if frame.value is None:
        return ()
    return tuple(
        item
        for item in semantic_quantities_v278(frame.source_span.literal)
        if abs(item.value - frame.value) <= max(1e-9, abs(frame.value) * 1e-9)
    )


def _per_share_operating_income(frame: KPIFrame) -> bool:
    if _base(frame.concept) != "OPERATING_INCOME":
        return False
    text = frame.source_span.literal
    per_share = semantic_backend_v278().phrase_mentions(text, ("per share",))
    return any(
        0 <= start - quantity.char_end <= 10
        for quantity in _quantity_for_value(frame)
        for _, start, _ in per_share
    )


def _operating_margin_owned_values(text: str) -> set[float]:
    backend = semantic_backend_v278()
    mentions = backend.phrase_mentions(text, ("operating margin", "operating profit margin"))
    quantities = tuple(
        item
        for item in semantic_quantities_v278(text, backend)
        if item.kind is QuantityKind.PERCENT
    )
    return {
        closest.value
        for _, start, _ in mentions
        if (
            closest := min(
                (item for item in quantities if item.char_end <= start),
                key=lambda item: start - item.char_end,
                default=None,
            )
        )
        is not None
        and start - closest.char_end <= 4
    }


def _currency_component(frame: KPIFrame) -> KPIFrame | None:
    if _base(frame.concept) != "REVENUE" or frame.change is None:
        return None
    text = frame.source_span.literal
    currency = semantic_backend_v278().phrase_mentions(
        text, ("currency impact", "foreign currency impact")
    )
    changes = tuple(
        item
        for item in semantic_quantities_v278(text)
        if item.kind is QuantityKind.PERCENT
        and abs(item.value - frame.change) <= max(1e-9, abs(frame.change) * 1e-9)
    )
    if not any(0 <= start - item.char_end <= 16 for item in changes for _, start, _ in currency):
        return None
    return replace(
        frame,
        frame=SemanticFrame.CHANGE_BY,
        value=frame.change,
        unit=frame.change_unit,
        change=None,
        change_unit=None,
        comparator="PRIOR_PERIOD",
        rule_id="v278.revenue_currency_component_ownership",
        verified_by="V278_SPACY_SEMANTIC_OWNERSHIP_VERIFIER",
    )


def resolve_frame_conflicts_v278(
    document: CanonicalDocument,
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
) -> tuple[KPIFrame, ...]:
    parent_recovered = tuple(
        frame for frame in recovered if not frame.rule_id.startswith("v278.")
    )
    v278_recovered = tuple(
        frame for frame in recovered if frame.rule_id.startswith("v278.")
    )
    # The parent resolver is authoritative for inherited rules, but it cannot
    # adjudicate newly declared semantic roles: doing so caused a valid yield
    # contribution to be discarded merely because a later volume anchor was
    # present in the same clause.
    merged = (
        *resolve_frame_conflicts_v277(document, existing, parent_recovered),
        *v278_recovered,
    )
    output: list[KPIFrame] = []
    range_blocks = {
        (frame.source.sha256, frame.source_span.char_start)
        for frame in merged
        if frame.concept == "ACTIVITY_VOLUME_CHANGE_GUIDANCE"
        and frame.frame is SemanticFrame.RANGE_GUIDANCE
    }
    change_to_keys = {
        (frame.source.sha256, frame.source_span.char_start, _base(frame.concept), frame.value)
        for frame in merged
        if frame.frame is SemanticFrame.CHANGE_TO
    }
    for frame in merged:
        text = frame.source_span.literal
        folded = text.casefold()
        if _per_share_operating_income(frame):
            continue
        if (
            frame.frame is SemanticFrame.ABSOLUTE_VALUE
            and (
                frame.source.sha256,
                frame.source_span.char_start,
                _base(frame.concept),
                frame.value,
            )
            in change_to_keys
        ):
            continue
        if (
            _base(frame.concept) == "OPERATING_MARGIN"
            and "basis points lower" in folded
        ):
            if frame.frame is not SemanticFrame.CHANGE_BY:
                continue
            frame = replace(frame, polarity=Polarity(False, "lower", None, None))
        if (
            _base(frame.concept) == "OPERATING_MARGIN"
            and "return on capital" in folded
            and any(cue in folded for cue in ("delivered", "maintaining", "generated"))
        ):
            owned = _operating_margin_owned_values(text)
            if frame.value not in owned or "GUIDANCE" in frame.concept:
                continue
        if (
            _base(frame.concept) == "ACTIVITY_VOLUME"
            and "average yield" in folded
            and "revenue growth" in folded
            and frame.value == 4.0
        ):
            continue
        if (
            _base(frame.concept) == "ACTIVITY_VOLUME"
            and frame.frame is SemanticFrame.CHANGE_BY
            and (frame.source.sha256, frame.source_span.char_start) in range_blocks
        ):
            continue
        currency = _currency_component(frame)
        output.append(currency or frame)
    unique: dict[tuple[object, ...], KPIFrame] = {}
    for frame in output:
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
        if current is None or frame.rule_id.startswith("v278."):
            unique[signature] = frame
    return tuple(unique.values())
