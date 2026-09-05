from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from .model import QuantityMention, SemanticFrame


class SemanticRole(StrEnum):
    VALUE_CURRENT = "VALUE_CURRENT"
    VALUE_PRIOR = "VALUE_PRIOR"
    DELTA = "DELTA"
    COMPOSITION = "COMPOSITION"
    GUIDANCE_VALUE = "GUIDANCE_VALUE"
    GUIDANCE_LOW = "GUIDANCE_LOW"
    GUIDANCE_HIGH = "GUIDANCE_HIGH"


@dataclass(frozen=True)
class QuantityRoleAssignment:
    role: SemanticRole
    quantity: QuantityMention


@dataclass(frozen=True)
class FrameRoleIntent:
    concept: str
    binding_concept: str
    semantic: SemanticFrame
    assignments: tuple[QuantityRoleAssignment, ...]
    positive: bool = True


@dataclass(frozen=True)
class FrameMaterialization:
    concept: str
    semantic: SemanticFrame
    value: QuantityMention
    change: QuantityMention | None = None
    lower: QuantityMention | None = None
    upper: QuantityMention | None = None
    positive: bool = True


def base_binding_concept(concept: str) -> str:
    output = concept.removeprefix("PRIOR_YEAR_")
    for suffix in ("_CHANGE_GUIDANCE", "_GUIDANCE"):
        if output.endswith(suffix):
            return output[: -len(suffix)]
    return output


def build_frame_role_intent(
    *,
    concept: str,
    semantic: SemanticFrame,
    value: QuantityMention | None = None,
    change: QuantityMention | None = None,
    lower: QuantityMention | None = None,
    upper: QuantityMention | None = None,
    positive: bool = True,
) -> FrameRoleIntent:
    if semantic is SemanticFrame.RANGE_GUIDANCE:
        if lower is None or upper is None:
            raise ValueError("RANGE_GUIDANCE requires observed lower and upper quantities")
        assignments = (
            QuantityRoleAssignment(SemanticRole.GUIDANCE_LOW, lower),
            QuantityRoleAssignment(SemanticRole.GUIDANCE_HIGH, upper),
        )
    elif semantic is SemanticFrame.CHANGE_TO:
        if value is None or change is None:
            raise ValueError("CHANGE_TO requires observed current-value and delta quantities")
        assignments = (
            QuantityRoleAssignment(SemanticRole.VALUE_CURRENT, value),
            QuantityRoleAssignment(SemanticRole.DELTA, change),
        )
    elif semantic is SemanticFrame.CHANGE_BY:
        if value is None:
            raise ValueError("CHANGE_BY requires an observed delta quantity")
        assignments = (QuantityRoleAssignment(SemanticRole.DELTA, value),)
    elif semantic is SemanticFrame.COMPOSITION:
        if value is None:
            raise ValueError("COMPOSITION requires an observed composition quantity")
        assignments = (QuantityRoleAssignment(SemanticRole.COMPOSITION, value),)
    elif semantic is SemanticFrame.COMPARATIVE:
        if value is None:
            raise ValueError("COMPARATIVE requires an observed value quantity")
        role = (
            SemanticRole.VALUE_PRIOR
            if concept.startswith("PRIOR_YEAR_")
            else SemanticRole.VALUE_CURRENT
        )
        assignments = (QuantityRoleAssignment(role, value),)
    elif semantic in {
        SemanticFrame.ABSOLUTE_VALUE,
        SemanticFrame.COUNT_ACTIVITY,
        SemanticFrame.RATE,
    }:
        if value is None:
            raise ValueError(f"{semantic.value} requires an observed value quantity")
        role = (
            SemanticRole.GUIDANCE_VALUE
            if concept.endswith("_GUIDANCE")
            else SemanticRole.VALUE_CURRENT
        )
        assignments = (QuantityRoleAssignment(role, value),)
    else:
        raise ValueError(f"Unsupported role-intent semantic frame: {semantic.value}")

    return FrameRoleIntent(
        concept=concept,
        binding_concept=base_binding_concept(concept),
        semantic=semantic,
        assignments=assignments,
        positive=positive,
    )


def materialize_role_intent(intent: FrameRoleIntent) -> FrameMaterialization:
    by_role = {assignment.role: assignment.quantity for assignment in intent.assignments}
    if intent.semantic is SemanticFrame.RANGE_GUIDANCE:
        lower = by_role[SemanticRole.GUIDANCE_LOW]
        upper = by_role[SemanticRole.GUIDANCE_HIGH]
        value = replace(lower, value=(lower.value + upper.value) / 2)
        return FrameMaterialization(
            concept=intent.concept,
            semantic=intent.semantic,
            value=value,
            lower=lower,
            upper=upper,
            positive=intent.positive,
        )
    if intent.semantic is SemanticFrame.CHANGE_TO:
        return FrameMaterialization(
            concept=intent.concept,
            semantic=intent.semantic,
            value=by_role[SemanticRole.VALUE_CURRENT],
            change=by_role[SemanticRole.DELTA],
            positive=intent.positive,
        )
    return FrameMaterialization(
        concept=intent.concept,
        semantic=intent.semantic,
        value=intent.assignments[0].quantity,
        positive=intent.positive,
    )


__all__ = [
    "FrameMaterialization",
    "FrameRoleIntent",
    "QuantityRoleAssignment",
    "SemanticRole",
    "base_binding_concept",
    "build_frame_role_intent",
    "materialize_role_intent",
]
