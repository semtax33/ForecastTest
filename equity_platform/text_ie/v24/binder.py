from __future__ import annotations

from hashlib import sha256
import re

from ..model import QuantityKind, QuantityMention, SemanticFrame
from .model import BoundFrameCandidate, RecallCandidate


_FORWARD = re.compile(
    r"\b(?:expects?|expected|guidance|forecast|outlook|projects?|will|target)\b",
    re.IGNORECASE,
)
_RANGE_CONNECTOR = re.compile(r"^\s*(?:to|through|[-–—]|and)\s*$", re.IGNORECASE)
_CHANGE = re.compile(
    r"\b(?:increased|grew|rose|decreased|declined|fell|up|down|"
    r"expansion|contraction|increase|decrease)\b",
    re.IGNORECASE,
)
_NEGATIVE_CHANGE = re.compile(
    r"\b(?:decreased|declined|fell|down|contraction|decrease)\b",
    re.IGNORECASE,
)
_ABSOLUTE = re.compile(
    r"\b(?:was|were|is|are|of|at|reached|total(?:ed|s)?|reported|"
    r"ended\b.{0,48}\bwith|balance\s+of|stood\s+at|had|has|invested)\b",
    re.IGNORECASE,
)
_VALUE_BEFORE = re.compile(
    r"\b(?:invested|reported|generated|generates|expects?|forecast|projects?)\s+"
    r"(?:approximately\s+|about\s+|more\s+than\s+|over\s+)?$",
    re.IGNORECASE,
)
_CAUSE_REVERSE = re.compile(
    r"\b(?:due to|because|driven by|resulted from|reflecting)\b",
    re.IGNORECASE,
)
_CAUSE_FORWARD = re.compile(r"\bincreased\b", re.IGNORECASE)


def _local_quantities(candidate: RecallCandidate) -> tuple[QuantityMention, ...]:
    metric = candidate.metric
    return tuple(
        sorted(
            candidate.quantities,
            key=lambda item: (
                abs(item.char_start - metric.char_start),
                item.char_start,
            ),
        )
    )


def _bound(
    candidate: RecallCandidate,
    *,
    frame: SemanticFrame,
    concept: str,
    value: QuantityMention | None,
    evidence: re.Match[str] | tuple[int, int, str],
    rule_id: str,
    lower: float | None = None,
    upper: float | None = None,
    relation_group: str | None = None,
) -> BoundFrameCandidate:
    if isinstance(evidence, tuple):
        start, end, literal = evidence
    else:
        start, end, literal = evidence.start(), evidence.end(), evidence.group(0)
    return BoundFrameCandidate(
        candidate_id=candidate.candidate_id,
        block=candidate.block,
        metric=candidate.metric,
        frame=frame,
        output_concept=concept,
        value=value,
        lower_value=lower,
        upper_value=upper,
        relation_evidence=literal,
        relation_start=start,
        relation_end=end,
        origins=candidate.origins,
        rule_id=rule_id,
        relation_group=relation_group,
    )


def _range_bindings(candidate: RecallCandidate) -> tuple[BoundFrameCandidate, ...]:
    text = candidate.block.text
    ordered = sorted(candidate.quantities, key=lambda item: item.char_start)
    pairs: list[tuple[QuantityMention, QuantityMention, tuple[int, int, str]]] = []
    for left, right in zip(ordered, ordered[1:]):
        if left.kind is not right.kind or left.unit != right.unit:
            continue
        connector = text[left.char_end : right.char_start]
        if _RANGE_CONNECTOR.fullmatch(connector) is None:
            continue
        metric_distance = min(
            abs(candidate.metric.char_start - left.char_start),
            abs(candidate.metric.char_start - right.char_start),
        )
        if metric_distance > 220:
            continue
        prefix = text[max(0, candidate.metric.char_start - 100) : right.char_end]
        if _FORWARD.search(prefix) is None and "between" not in prefix.casefold():
            continue
        pairs.append((left, right, (left.char_end, right.char_start, connector)))
    if not pairs:
        return ()
    left, right, evidence = min(
        pairs,
        key=lambda pair: abs(pair[0].char_start - candidate.metric.char_start),
    )
    low, high = sorted((left.value, right.value))
    midpoint = QuantityMention(
        left.kind,
        (low + high) / 2.0,
        left.unit,
        f"{left.raw}..{right.raw}",
        left.char_start,
        right.char_end,
    )
    return (
        _bound(
            candidate,
            frame=SemanticFrame.RANGE_GUIDANCE,
            concept=candidate.metric.concept + "_GUIDANCE",
            value=midpoint,
            evidence=evidence,
            rule_id="v24.range",
            lower=low,
            upper=high,
        ),
    )


def _numeric_bindings(candidate: RecallCandidate) -> tuple[BoundFrameCandidate, ...]:
    text = candidate.block.text
    metric = candidate.metric
    if metric.inherited_from:
        return ()
    results: list[BoundFrameCandidate] = []
    quantities = _local_quantities(candidate)
    for quantity in quantities:
        left = min(metric.char_end, quantity.char_end)
        right = max(metric.char_start, quantity.char_start)
        bridge = text[left:right]
        context = text[max(0, left - 80) : min(len(text), right + 80)]
        change = _CHANGE.search(context)
        is_relation_quantity = quantity.kind in {
            QuantityKind.PERCENT,
            QuantityKind.BASIS_POINTS,
            QuantityKind.MONEY,
            QuantityKind.COUNT,
        }
        if change is not None and is_relation_quantity:
            results.append(
                _bound(
                    candidate,
                    frame=SemanticFrame.CHANGE_BY,
                    concept=metric.concept + "_CHANGE",
                    value=quantity,
                    evidence=(
                        max(0, left - 80) + change.start(),
                        max(0, left - 80) + change.end(),
                        change.group(0),
                    ),
                    rule_id="v24.change",
                )
            )
        absolute = _ABSOLUTE.search(bridge)
        if metric.char_end <= quantity.char_start and absolute is not None:
            results.append(
                _bound(
                    candidate,
                    frame=SemanticFrame.ABSOLUTE_VALUE,
                    concept=metric.concept,
                    value=quantity,
                    evidence=(
                        left + absolute.start(),
                        left + absolute.end(),
                        absolute.group(0),
                    ),
                    rule_id="v24.proximity",
                )
            )
        elif quantity.char_end <= metric.char_start:
            prefix = text[max(0, quantity.char_start - 96) : quantity.char_start]
            leading = _VALUE_BEFORE.search(prefix)
            if leading is not None and len(bridge) <= 96:
                evidence_literal = leading.group(0).rstrip()
                evidence_start = max(0, quantity.char_start - 96) + leading.start()
                results.append(
                    _bound(
                        candidate,
                        frame=SemanticFrame.ABSOLUTE_VALUE,
                        concept=metric.concept,
                        value=quantity,
                        evidence=(
                            evidence_start,
                            evidence_start + len(evidence_literal),
                            evidence_literal,
                        ),
                        rule_id="v24.proximity",
                    )
                )
    return tuple(results)


def _causal_bindings(group: tuple[RecallCandidate, ...]) -> tuple[BoundFrameCandidate, ...]:
    if not group:
        return ()
    text = group[0].block.text
    anchors = sorted(
        {(
            item.metric.char_start,
            item.metric.char_end,
            item.metric.concept,
            item.metric.alias,
            item.metric.inherited_from,
        ) for item in group if not item.metric.inherited_from}
    )
    matches = list(_CAUSE_REVERSE.finditer(text)) + list(_CAUSE_FORWARD.finditer(text))
    output: list[BoundFrameCandidate] = []
    for match in sorted(matches, key=lambda item: item.start()):
        before = [item for item in anchors if item[1] <= match.start()]
        after = [item for item in anchors if item[0] >= match.end()]
        if not before or not after:
            continue
        left = max(before, key=lambda item: item[1])
        right = min(after, key=lambda item: item[0])
        if match.start() - left[1] > 180 or right[0] - match.end() > 180:
            continue
        left_candidate = next(item for item in group if item.metric.char_start == left[0])
        right_candidate = next(item for item in group if item.metric.char_start == right[0])
        group_id = sha256(
            f"{left_candidate.candidate_id}:{right_candidate.candidate_id}:{match.start()}".encode()
        ).hexdigest()[:16]
        for candidate in (left_candidate, right_candidate):
            output.append(
                _bound(
                    candidate,
                    frame=SemanticFrame.CAUSE_EFFECT,
                    concept=candidate.metric.concept,
                    value=None,
                    evidence=match,
                    rule_id="v24.causal",
                    relation_group=group_id,
                )
            )
    return tuple(output)


def bind_recall_candidates(
    candidates: tuple[RecallCandidate, ...],
) -> tuple[BoundFrameCandidate, ...]:
    results: list[BoundFrameCandidate] = []
    by_block: dict[tuple[str, int, int], list[RecallCandidate]] = {}
    for candidate in candidates:
        key = (
            candidate.block.source.sha256,
            candidate.block.char_start,
            candidate.block.char_end,
        )
        by_block.setdefault(key, []).append(candidate)
        results.extend(_range_bindings(candidate))
        results.extend(_numeric_bindings(candidate))
    for group in by_block.values():
        results.extend(_causal_bindings(tuple(group)))
    deduped: dict[tuple[object, ...], BoundFrameCandidate] = {}
    for item in results:
        key = (
            item.candidate_id,
            item.frame,
            item.output_concept,
            item.value.value if item.value else None,
            item.value.char_start if item.value else None,
            item.relation_group,
        )
        deduped.setdefault(key, item)
    return tuple(deduped.values())
