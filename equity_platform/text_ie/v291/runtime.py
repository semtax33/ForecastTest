from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from equity_platform.documents import CanonicalDocument

from ..role_graph import FrameRoleIntent
from ..v290 import extract_text_kpis_v290
from .model import (
    ClauseSemanticTrace,
    DocumentSemanticTelemetry,
    QuantityBindingEdge,
    QuantityRoleEdge,
    V291ExtractionResult,
)


def _role_edges(
    bindings: tuple[QuantityBindingEdge, ...],
    intents: tuple[FrameRoleIntent, ...],
) -> tuple[QuantityRoleEdge, ...]:
    output = []
    for intent in intents:
        for assignment in intent.assignments:
            binding = next(
                (
                    edge
                    for edge in bindings
                    if edge.concept == intent.binding_concept
                    and edge.quantity == assignment.quantity
                ),
                None,
            )
            if binding is None:
                continue
            output.append(QuantityRoleEdge(
                concept=intent.binding_concept,
                role=assignment.role.value,
                quantity=assignment.quantity,
                concept_char_start=binding.concept_char_start,
                concept_char_end=binding.concept_char_end,
            ))
    return tuple(output)


def _unresolved_bindings(
    bindings: tuple[QuantityBindingEdge, ...],
    roles: tuple[QuantityRoleEdge, ...],
) -> tuple[QuantityBindingEdge, ...]:
    available = list(bindings)
    for role in roles:
        index = next(
            (
                index
                for index, edge in enumerate(available)
                if edge.concept == role.concept
                and edge.quantity == role.quantity
                and edge.concept_char_start == role.concept_char_start
                and edge.concept_char_end == role.concept_char_end
            ),
            None,
        )
        if index is not None:
            available.pop(index)
    return tuple(available)


def _trace(observation: Mapping[str, Any]) -> ClauseSemanticTrace:
    block = observation["block"]
    bindings = tuple(
        QuantityBindingEdge(
            concept=binding.concept,
            quantity=binding.quantity,
            concept_char_start=binding.concept_char_start,
            concept_char_end=binding.concept_char_end,
        )
        for binding in observation["bindings"]
    )
    intents = tuple(observation["role_intents"])
    frames = tuple(observation["frames"])
    roles = _role_edges(bindings, intents)
    unresolved = _unresolved_bindings(bindings, roles)
    primary_root_cause = str(observation["primary_root_cause"])
    if frames and unresolved:
        primary_root_cause = "PARTIAL_UNRESOLVED_BINDING"
    return ClauseSemanticTrace(
        block_char_start=block.char_start,
        block_char_end=block.char_end,
        clause_char_start=block.char_start + int(observation["clause_start"]),
        clause_char_end=block.char_start + int(observation["clause_end"]),
        candidate_ids=tuple(observation["candidate_ids"]),
        concepts=tuple(observation["concepts"]),
        quantities=tuple(observation["quantities"]),
        bindings=bindings,
        roles=roles,
        unresolved_bindings=unresolved,
        reduced_frames=frames,
        adjudicated=bool(observation["adjudicated"]),
        primary_root_cause=primary_root_cause,
    )


def extract_text_kpis_v291(document: CanonicalDocument) -> V291ExtractionResult:
    observations: list[Mapping[str, Any]] = []
    base = extract_text_kpis_v290(document, telemetry_observer=observations.append)
    telemetry = DocumentSemanticTelemetry(tuple(_trace(item) for item in observations))
    return V291ExtractionResult(base=base, telemetry=telemetry)
