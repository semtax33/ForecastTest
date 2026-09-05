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
from ..v274.semantics import (
    augment_candidates_v274,
    resolve_frame_conflicts_v274,
    semantic_concepts_v274,
    semantic_quantities_v274,
)
from .context import declared_money_scale


RULE_PATH = PROJECT_ROOT / "configs/parser_rules/text_ie/v275_semantic_laws.arc"
V275_RULES = compile_text_rule_file(RULE_PATH)

_ALIASES = {
    "operating loss": "OPERATING_INCOME",
    "price/mix": "PRICE_REALIZATION",
    "residential sales": "ACTIVITY_VOLUME",
    "investment in property and equipment": "CAPEX",
    "device signings": "ACTIVITY_VOLUME",
    "fully diluted shares": "SHARES",
    "acquisition and divestiture mix": "REVENUE",
}


@lru_cache(maxsize=1)
def semantic_backend_v275() -> SpacySemanticBackend:
    return SpacySemanticBackend()


def semantic_concepts_v275(
    text: str,
    backend: SpacySemanticBackend | None = None,
) -> tuple[ConceptMention, ...]:
    selected_backend = backend or semantic_backend_v275()
    output = list(semantic_concepts_v274(text, selected_backend))
    for phrase, concept in _ALIASES.items():
        output.extend(
            ConceptMention(concept, literal, start, end)
            for literal, start, end in selected_backend.phrase_mentions(text, (phrase,))
        )
    unique = {
        (item.concept, item.char_start, item.char_end): item for item in output
    }
    return tuple(
        sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.concept))
    )


def semantic_quantities_v275(
    text: str,
    backend: SpacySemanticBackend,
) -> tuple[QuantityMention, ...]:
    output = list(semantic_quantities_v274(text, backend))
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    for index, token in enumerate(tokens):
        if not token.like_num:
            continue
        try:
            number = float(token.text.replace(",", ""))
        except ValueError:
            continue
        # Materialize the left side of "27,000 and 29,000 units".  The right
        # side is already typed by the shared quantity parser.
        if index + 3 < len(tokens) and tokens[index + 1].lower_ == "and":
            right = tokens[index + 2]
            unit = tokens[index + 3]
            if right.like_num and unit.lemma_.casefold() in {"unit", "meu", "signing"}:
                for count_token in (token, right):
                    output.append(
                        QuantityMention(
                            kind=QuantityKind.COUNT,
                            value=float(count_token.text.replace(",", "")),
                            unit="COUNT",
                            raw=count_token.text,
                            char_start=int(count_token.idx),
                            char_end=int(count_token.idx + len(count_token.text)),
                        )
                    )
        # A share count often puts the unit after "of fully diluted".
        if index + 1 < len(tokens) and tokens[index + 1].lower_ in {"million", "billion"}:
            tail = " ".join(item.lower_ for item in tokens[index + 2 : index + 7])
            if "share" in tail:
                scale = 1_000_000.0 if tokens[index + 1].lower_ == "million" else 1_000_000_000.0
                output.append(
                    QuantityMention(
                        kind=QuantityKind.COUNT,
                        value=number * scale,
                        unit="COUNT",
                        raw=text[int(token.idx) : int(tokens[index + 1].idx + len(tokens[index + 1].text))],
                        char_start=int(token.idx),
                        char_end=int(tokens[index + 1].idx + len(tokens[index + 1].text)),
                    )
                )
    unique = {
        (item.kind, item.value, item.char_start, item.char_end): item for item in output
    }
    return tuple(sorted(unique.values(), key=lambda item: (item.char_start, item.char_end, item.kind)))


def augment_candidates_v275(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[RecallCandidate, ...]:
    selected_backend = backend or semantic_backend_v275()
    output = list(augment_candidates_v274(document, candidates, selected_backend))
    seen = {
        (item.block.char_start, item.metric.concept, item.metric.char_start, item.metric.char_end)
        for item in output
    }
    blocks = {
        (block.char_start, block.char_end): block for block in document_text_blocks(document)
    }
    for block in blocks.values():
        quantities = semantic_quantities_v275(block.text, selected_backend)
        for mention in semantic_concepts_v275(block.text, selected_backend):
            signature = (
                block.char_start,
                mention.concept,
                mention.char_start,
                mention.char_end,
            )
            if signature in seen or mention.alias.casefold() not in _ALIASES:
                continue
            compatible = tuple(
                item
                for item in quantities
                if item.kind
                in set(definition_for(mention.concept).quantity_kinds)
                | {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
                and abs(item.char_start - mention.char_start) <= 420
            )
            if not compatible:
                continue
            candidate_id = sha256(
                f"{document.source.sha256}:{block.char_start}:{mention.concept}:"
                f"{mention.char_start}:{mention.char_end}:v275".encode()
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
                    rule_ids=("v275.spacy_semantic_alias",),
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


def _change_by(template: KPIFrame, quantity: QuantityMention) -> KPIFrame:
    return replace(
        template,
        frame=SemanticFrame.CHANGE_BY,
        value=quantity.value,
        unit=quantity.unit,
        change=None,
        change_unit=None,
        comparator="PRIOR_PERIOD",
    )


def _local_polarity(
    text: str,
    quantity: QuantityMention,
    backend: SpacySemanticBackend,
) -> Polarity:
    tokens = tuple(token for token in backend.parse(text) if not token.is_space)
    nearby = tuple(
        token
        for token in tokens
        if abs(int(token.idx) - quantity.char_start) <= 80
        and token.lemma_.casefold() in {"increase", "decrease", "decline", "contract"}
    )
    if not nearby:
        return Polarity(True, None, None, None)
    trigger = min(
        nearby,
        key=lambda token: min(
            abs(int(token.idx) - quantity.char_end),
            abs(int(token.idx + len(token.text)) - quantity.char_start),
        ),
    )
    negative = trigger.lemma_.casefold() in {"decrease", "decline", "contract"}
    return Polarity(not negative, trigger.text, None, None)


def _quantity(
    quantities: tuple[QuantityMention, ...],
    value: float | None,
    kind: QuantityKind,
) -> QuantityMention | None:
    if value is None:
        return None
    return min(
        (
            item
            for item in quantities
            if item.kind is kind
            and abs(item.value - value) <= max(1e-9, abs(value) * 1e-9)
        ),
        key=lambda item: item.char_start,
        default=None,
    )


def _scaled(frame: KPIFrame, scale: float | None) -> KPIFrame:
    if scale is None or frame.value is None or abs(frame.value) >= 1_000_000:
        return frame
    return replace(
        frame,
        value=frame.value * scale,
        context_trace={**frame.context_trace, "declared_money_scale": scale},
    )


def _postprocess(
    document: CanonicalDocument,
    block: TextBlock,
    frames: tuple[KPIFrame, ...],
    quantities: tuple[QuantityMention, ...],
    backend: SpacySemanticBackend,
) -> tuple[KPIFrame, ...]:
    if not frames:
        return ()
    rule_id = frames[0].rule_id
    template = frames[0]
    if rule_id == "v275.compact_product_sales":
        change = _quantity(quantities, template.change, QuantityKind.PERCENT)
        parenthesized = bool(
            change
            and change.char_start > 0
            and block.text[change.char_start - 1 : change.char_start] == "("
        )
        return (replace(template, polarity=Polarity(not parenthesized, None, None, None)),)
    if rule_id == "v275.revenue_reflecting_components":
        parsed = backend.parse(block.text)
        reflect_token = max(
            (
                token
                for token in parsed
                if token.lemma_.casefold() == "reflect"
            ),
            key=lambda token: int(token.idx),
            default=None,
        )
        reflect = (
            int(reflect_token.idx + len(reflect_token.text))
            if reflect_token is not None
            else len(block.text)
        )
        sentence_end = (
            int(reflect_token.sent.end_char)
            if reflect_token is not None
            else len(block.text)
        )
        components = tuple(
            item
            for item in quantities
            if item.kind is QuantityKind.PERCENT
            and reflect <= item.char_start < sentence_end
        )
        return tuple(
            replace(_change_by(template, item), polarity=_local_polarity(block.text, item, backend))
            for item in components
        )
    if rule_id in {"v275.operating_loss_level", "v275.ebit_loss_level"}:
        return (replace(template, polarity=Polarity(False, "loss", None, None)),)
    if rule_id == "v275.volume_impact_pair":
        percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
        return tuple(_change_by(template, item) for item in percents[:2])
    if rule_id == "v275.revenue_percent_level_cc":
        secondary = _quantity(quantities, 2.0, QuantityKind.PERCENT)
        if secondary is None or secondary.value == template.change:
            percents = tuple(item for item in quantities if item.kind is QuantityKind.PERCENT)
            secondary = percents[1] if len(percents) > 1 else None
        return (template,) + ((_change_by(template, secondary),) if secondary else ())
    if rule_id == "v275.revenue_decline_range":
        marker = next(
            (
                int(token.idx)
                for token in backend.parse(block.text)
                if token.lemma_.casefold() == "decline"
            ),
            0,
        )
        values = tuple(
            item.value
            for item in quantities
            if item.kind is QuantityKind.PERCENT and item.char_start >= marker
        )
        if len(values) < 2:
            return ()
        low, high = sorted(values[:2])
        return (
            replace(
                template,
                concept="REVENUE_CHANGE_GUIDANCE",
                frame=SemanticFrame.RANGE_GUIDANCE,
                value=(low + high) / 2,
                change=None,
                change_unit=None,
                lower_value=low,
                upper_value=high,
                period_semantics=PeriodSemantics.FORECAST,
                polarity=Polarity(False, "decline", None, None),
            ),
        )
    if rule_id == "v275.revenue_acquisition_fx":
        value = _quantity(quantities, template.value, QuantityKind.MONEY)
        change = _quantity(quantities, template.change, QuantityKind.MONEY)
        output = [
            replace(template, frame=SemanticFrame.ABSOLUTE_VALUE, change=None, change_unit=None)
        ]
        if change is not None:
            output.append(_change_by(template, change))
        return tuple(output)
    if rule_id == "v275.diluted_share_outlook":
        return (
            replace(
                template,
                concept="SHARES_GUIDANCE",
                period_semantics=PeriodSemantics.FORECAST,
            ),
        )
    if rule_id == "v275.capex_comparative":
        scale = declared_money_scale(document, block, backend)
        return tuple(_scaled(frame, scale) for frame in frames)
    if rule_id == "v275.revenue_money_percent_change":
        scale = declared_money_scale(document, block, backend)
        money = _quantity(quantities, template.value, QuantityKind.MONEY)
        percent = _quantity(quantities, template.change, QuantityKind.PERCENT)
        output = []
        if money is not None:
            output.append(_scaled(_change_by(template, money), scale))
        if percent is not None:
            output.append(_change_by(template, percent))
        return tuple(output)
    if rule_id == "v275.activity_goal_range":
        return tuple(
            replace(
                frame,
                concept="ACTIVITY_VOLUME_GUIDANCE",
                period_semantics=PeriodSemantics.FORECAST,
                tier=FactTier.CRITICAL,
            )
            for frame in frames
        )
    return frames


def recover_v275_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
    *,
    rules: tuple[TextRuleIR, ...] = V275_RULES,
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v275()
    blocks = {
        (candidate.block.char_start, candidate.block.char_end): candidate.block
        for candidate in candidates
    }
    output: list[KPIFrame] = []
    for block_span, block in blocks.items():
        if block_span not in allowed_spans:
            continue
        concepts = semantic_concepts_v275(block.text, selected_backend)
        quantities = semantic_quantities_v275(block.text, selected_backend)
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
            for frame in _postprocess(
                document, block, matched or (), quantities, selected_backend
            ):
                if _base(frame.concept) in {
                    "ACTIVITY_VOLUME",
                    "PRICE_REALIZATION",
                    "CAPEX",
                }:
                    frame = replace(frame, tier=FactTier.CRITICAL)
                output.append(
                    replace(
                        frame,
                        context_trace={
                            **frame.context_trace,
                            "candidate_id": _candidate_id(frame, block, candidates),
                            "binding_eligibility": "V275_SPACY_SEMANTIC_LAW",
                            "rule_program_sha256": rule.source_sha256,
                        },
                        verified_by="V275_SPACY_SEMANTIC_LAW_VERIFIER",
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


def _normalized_local_polarity(
    frame: KPIFrame,
    backend: SpacySemanticBackend,
) -> KPIFrame:
    if frame.frame is not SemanticFrame.CHANGE_BY or frame.value is None:
        return frame
    quantities = semantic_quantities_v275(frame.source_span.literal, backend)
    matches = tuple(
        item
        for item in quantities
        if item.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
        and abs(item.value - frame.value) <= max(1e-9, abs(frame.value) * 1e-9)
    )
    if len(matches) != 1:
        return frame
    return replace(frame, polarity=_local_polarity(frame.source_span.literal, matches[0], backend))


def resolve_frame_conflicts_v275(
    document: CanonicalDocument,
    existing: tuple[KPIFrame, ...],
    recovered: tuple[KPIFrame, ...],
    backend: SpacySemanticBackend | None = None,
) -> tuple[KPIFrame, ...]:
    selected_backend = backend or semantic_backend_v275()
    merged = resolve_frame_conflicts_v274(document, existing, recovered, selected_backend)

    realized_ids = {
        "v275.reported_revenue_change_to",
        "v275.compact_product_sales",
        "v275.revenue_reflecting_components",
        "v275.revenue_acquisition_fx",
    }
    merged = tuple(
        replace(
            frame,
            concept=frame.concept.removesuffix("_GUIDANCE"),
            period_semantics=PeriodSemantics.DOCUMENT_PERIOD,
        )
        if frame.rule_id in realized_ids
        else frame
        for frame in merged
    )

    def ownership_error(frame: KPIFrame) -> bool:
        peers = tuple(other for other in merged if other is not frame and _same_block(frame, other))
        base = _base(frame.concept)
        if base == "OPERATING_INCOME" and frame.change is not None:
            margin_values = {
                value
                for other in peers
                if _base(other.concept) == "OPERATING_MARGIN"
                for value in (other.value, other.change)
                if value is not None
            }
            if frame.change in margin_values and any(
                _base(other.concept) == base
                and other.value == frame.value
                and other.change not in margin_values
                for other in peers
            ):
                return True
        if base in {"GROSS_MARGIN", "OPERATING_MARGIN"} and frame.change_unit != "BASIS_POINTS":
            if any(
                _base(other.concept) == base
                and other.value == frame.value
                and other.change_unit == "BASIS_POINTS"
                for other in peers
            ):
                return True
        if base == "REVENUE" and any(_base(other.concept) == "CAPEX" for other in peers):
            return True
        if base == "REVENUE" and frame.frame is SemanticFrame.CHANGE_TO:
            if any(
                other.rule_id == "v275.revenue_reflecting_components"
                and other.frame is SemanticFrame.CHANGE_BY
                and other.value == frame.change
                for other in peers
            ):
                return True
        if (
            base == "REVENUE"
            and frame.frame is SemanticFrame.CHANGE_BY
            and frame.rule_id != "v275.revenue_reflecting_components"
        ):
            if any(
                _base(other.concept) in {"PRICE_REALIZATION", "ACTIVITY_VOLUME"}
                and other.frame is SemanticFrame.CHANGE_BY
                and other.value == frame.value
                for other in peers
            ):
                return True
        if base == "EBIT" and frame.frame is SemanticFrame.CHANGE_BY:
            if any(
                _base(other.concept) == "EBIT"
                and other.frame is SemanticFrame.CHANGE_TO
                and other.change == frame.value
                for other in peers
            ):
                return True
        if frame.rule_id != "v275.revenue_money_percent_change" and frame.value is not None:
            if any(
                other.rule_id == "v275.revenue_money_percent_change"
                and other.context_trace.get("declared_money_scale")
                and frame.value * float(other.context_trace["declared_money_scale"])
                == other.value
                for other in peers
            ):
                return True
        return False

    unique: dict[tuple[object, ...], KPIFrame] = {}
    for raw in merged:
        if ownership_error(raw):
            continue
        frame = _normalized_local_polarity(raw, selected_backend)
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
        if current is None or frame.rule_id.startswith("v275."):
            unique[signature] = frame
    return tuple(unique.values())
