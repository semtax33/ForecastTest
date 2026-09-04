from __future__ import annotations

from collections import defaultdict
import re

from ..model import QuantityKind
from ..ontology import definition_for
from ..v24.model import RecallCandidate
from .clause import segment_clauses
from .model import CanonicalBinding, Role, TypedRoleCandidate


_CHANGE = re.compile(
    r"\b(increased|grew|rose|decreased|declined|fell|up|down|increase|decrease)\b",
    re.IGNORECASE,
)
_NEGATIVE = {"decreased", "declined", "fell", "down", "decrease"}
_ABSOLUTE = re.compile(
    r"\b(?:was|were|is|are|of|at|reached|total(?:ed|s)?|reported|stood at|had|has)\b",
    re.IGNORECASE,
)
_COMPARATIVE = re.compile(r"\b(?:compared (?:with|to)|versus|prior year)\b", re.I)


def _compatible(candidate: RecallCandidate, role: Role, quantity: object) -> bool:
    if role is Role.DELTA:
        return quantity.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
    kinds = definition_for(candidate.metric.concept).quantity_kinds
    return not kinds or quantity.kind in kinds


def typed_role_candidates(
    candidates: tuple[RecallCandidate, ...],
) -> tuple[TypedRoleCandidate, ...]:
    output: list[TypedRoleCandidate] = []
    for candidate in candidates:
        if candidate.metric.inherited_from:
            continue
        clause = next(
            (
                item
                for item in segment_clauses(candidate.block)
                if item.char_start <= candidate.metric.char_start < item.char_end
            ),
            None,
        )
        if clause is None:
            continue
        local_quantities = [
            item
            for item in candidate.quantities
            if clause.char_start <= item.char_start and item.char_end <= clause.char_end
        ]
        metric_end = candidate.metric.char_end
        next_metric = min(
            (
                other.metric.char_start
                for other in candidates
                if other.block is candidate.block
                and other.metric.char_start > candidate.metric.char_start
                and other.metric.char_start < clause.char_end
            ),
            default=clause.char_end,
        )
        trigger_match = _CHANGE.search(candidate.block.text[metric_end:next_metric])
        absolute_match = _ABSOLUTE.search(candidate.block.text[metric_end:next_metric])
        trigger = trigger_match.group(0) if trigger_match else (
            absolute_match.group(0) if absolute_match else ""
        )
        trigger_start = metric_end + (
            trigger_match.start() if trigger_match else absolute_match.start() if absolute_match else 0
        )
        direction = -1 if trigger.casefold() in _NEGATIVE else 1
        for quantity in local_quantities:
            between = candidate.block.text[
                min(metric_end, quantity.char_end) : max(candidate.metric.char_start, quantity.char_start)
            ]
            relation_window = candidate.block.text[max(metric_end, quantity.char_start - 40):quantity.char_start]
            delta_evidence = trigger_match is not None and (
                quantity.kind in {QuantityKind.PERCENT, QuantityKind.BASIS_POINTS}
                and quantity.char_start >= trigger_start
                and quantity.char_start < next_metric
            )
            level_evidence = quantity.char_start < next_metric and (
                re.search(r"\bto\s*$", relation_window, re.I) is not None
                or (absolute_match is not None and quantity.char_start >= metric_end)
            )
            for role, evidence in ((Role.DELTA, delta_evidence), (Role.LEVEL, level_evidence)):
                compatible = _compatible(candidate, role, quantity)
                eligible = bool(evidence and compatible and not _COMPARATIVE.search(clause.text))
                distance = abs(quantity.char_start - candidate.metric.char_end)
                score = (
                    0.40
                    + (0.25 if evidence else 0.0)
                    + (0.20 if compatible else 0.0)
                    + max(0.0, 0.15 * (1.0 - distance / 200.0))
                )
                output.append(
                    TypedRoleCandidate(
                        candidate, clause, role, quantity, trigger, trigger_start,
                        direction, eligible,
                        "ELIGIBLE" if eligible else "HARD_CONSTRAINT_REJECT",
                        score,
                    )
                )
    return tuple(output)


def constraint_bind(
    candidates: tuple[RecallCandidate, ...],
    *,
    absolute_threshold: float = 0.80,
    ambiguity_threshold: float = 0.12,
) -> tuple[tuple[TypedRoleCandidate, ...], tuple[CanonicalBinding, ...]]:
    roles = typed_role_candidates(candidates)
    grouped: dict[tuple[object, ...], list[TypedRoleCandidate]] = defaultdict(list)
    for item in roles:
        if item.eligible:
            grouped[(item.candidate.candidate_id, item.clause.char_start, item.role)].append(item)
    selected: dict[tuple[str, int], dict[Role, TypedRoleCandidate]] = defaultdict(dict)
    margins: dict[tuple[str, int, Role], float] = {}
    ambiguous: set[tuple[str, int, Role]] = set()
    for key, options in grouped.items():
        ranked = sorted(options, key=lambda item: (-item.score, item.quantity.char_start))
        margin = ranked[0].score - ranked[1].score if len(ranked) > 1 else 1.0
        margins[key] = margin
        if ranked[0].score < absolute_threshold or margin < ambiguity_threshold:
            ambiguous.add(key)
        else:
            selected[(key[0], key[1])][key[2]] = ranked[0]
    bindings: list[CanonicalBinding] = []
    by_id = {item.candidate_id: item for item in candidates}
    keys = set(selected) | {(key[0], key[1]) for key in ambiguous}
    for candidate_id, clause_start in sorted(keys):
        candidate = by_id[candidate_id]
        chosen = selected.get((candidate_id, clause_start), {})
        clause = next(item.clause for item in roles if item.candidate.candidate_id == candidate_id and item.clause.char_start == clause_start)
        ambiguity = min(
            (margins[key] for key in ambiguous if key[:2] == (candidate_id, clause_start)),
            default=min((margins.get((candidate_id, clause_start, role), 1.0) for role in chosen), default=1.0),
        )
        if any(key[:2] == (candidate_id, clause_start) for key in ambiguous):
            status, reason = "REVIEW", "TOP1_TOP2_MARGIN_BELOW_THRESHOLD"
        elif not chosen:
            status, reason = "ABSTAIN", "NO_ELIGIBLE_ROLE_ASSIGNMENT"
        else:
            status, reason = "AUTO", "CONSTRAINT_AND_MARGIN_PASS"
        representative = next(iter(chosen.values()), None)
        bindings.append(
            CanonicalBinding(
                candidate,
                clause,
                chosen.get(Role.LEVEL).quantity if Role.LEVEL in chosen else None,
                chosen.get(Role.DELTA).quantity if Role.DELTA in chosen else None,
                representative.direction if representative else 1,
                max((item.score for item in chosen.values()), default=0.0),
                ambiguity,
                status,
                reason,
            )
        )
    return roles, tuple(bindings)
