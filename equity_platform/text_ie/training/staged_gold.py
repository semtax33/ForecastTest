from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
import json
from math import isfinite
from pathlib import Path


class HoldoutAxis(StrEnum):
    TEMPORAL = "A"
    ISSUER = "B"
    ONTOLOGY = "C"


@dataclass(frozen=True)
class QuantityGoldNode:
    node_id: str
    kind: str
    value: float
    char_start: int
    char_end: int


@dataclass(frozen=True)
class ConceptGoldNode:
    node_id: str
    concept: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class StageEdge:
    concept_id: str
    quantity_id: str


@dataclass(frozen=True)
class RoleGoldEdge:
    concept_id: str
    quantity_id: str
    role: str


@dataclass(frozen=True)
class StagedGoldExample:
    example_id: str
    entity: str
    holdout_axis: HoldoutAxis
    source_kind: str
    source_sha256: str
    available_at: str
    document_period: str
    text: str
    gold_route: str
    quantities: tuple[QuantityGoldNode, ...]
    concepts: tuple[ConceptGoldNode, ...]
    candidate_edges: tuple[StageEdge, ...]
    binding_edges: tuple[StageEdge, ...]
    role_edges: tuple[RoleGoldEdge, ...]
    expected_frames: tuple[dict[str, object], ...]
    annotation_source: str


def _quantity(row: dict[str, object]) -> QuantityGoldNode:
    value = float(row["value"])
    if not isfinite(value):
        raise ValueError("quantity values must be finite")
    return QuantityGoldNode(
        node_id=str(row["node_id"]),
        kind=str(row["kind"]),
        value=value,
        char_start=int(row["char_start"]),
        char_end=int(row["char_end"]),
    )


def _concept(row: dict[str, object]) -> ConceptGoldNode:
    return ConceptGoldNode(
        node_id=str(row["node_id"]),
        concept=str(row["concept"]),
        char_start=int(row["char_start"]),
        char_end=int(row["char_end"]),
    )


def _edge(row: dict[str, object]) -> StageEdge:
    return StageEdge(str(row["concept_id"]), str(row["quantity_id"]))


def _role(row: dict[str, object]) -> RoleGoldEdge:
    return RoleGoldEdge(
        str(row["concept_id"]),
        str(row["quantity_id"]),
        str(row["role"]),
    )


def _unique_ids(nodes, label: str, *, allow_empty: bool = False) -> set[str]:
    ids = [node.node_id for node in nodes]
    if (
        (not ids and not allow_empty)
        or any(not node_id for node_id in ids)
        or len(ids) != len(set(ids))
    ):
        raise ValueError(f"{label} nodes require non-empty unique ids")
    return set(ids)


def _validate(example: StagedGoldExample) -> None:
    if not example.example_id or not example.entity or not example.annotation_source:
        raise ValueError("staged gold identity and provenance fields cannot be blank")
    if example.source_kind not in {
        "10-K",
        "10-Q",
        "10-K_NOTE",
        "10-Q_NOTE",
        "IR",
        "INDUSTRY_DATA",
    }:
        raise ValueError("unsupported staged gold source kind")
    if len(example.source_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in example.source_sha256.casefold()
    ):
        raise ValueError("staged gold source sha256 must be a 64-character hex digest")
    try:
        date.fromisoformat(example.available_at)
    except ValueError as exc:
        raise ValueError("staged gold available_at must be an ISO release date") from exc
    if example.gold_route not in {"TEXT_IE", "TABLE_DSL", "NO_FACT"}:
        raise ValueError("unsupported staged gold route")
    no_fact = example.gold_route == "NO_FACT"
    text_ie = example.gold_route == "TEXT_IE"
    if no_fact and example.expected_frames:
        raise ValueError("NO_FACT staged gold cannot contain expected frames")
    if text_ie and (not example.concepts or not example.quantities):
        raise ValueError(
            "non-NO_FACT TEXT_IE staged gold requires concept and quantity nodes"
        )
    # A positional table can be a true routing target while containing no KPI
    # supported by the frozen ontology.  Requiring synthetic graph nodes for
    # such a block corrupts both route accuracy and intermediate-stage scores.
    allow_empty_graph = not text_ie
    concept_ids = _unique_ids(
        example.concepts,
        "concept",
        allow_empty=allow_empty_graph,
    )
    quantity_ids = _unique_ids(
        example.quantities,
        "quantity",
        allow_empty=allow_empty_graph,
    )
    for node in (*example.concepts, *example.quantities):
        if not 0 <= node.char_start < node.char_end <= len(example.text):
            raise ValueError("stage node spans must be inside the annotated text")
    candidate_pairs = {
        (edge.concept_id, edge.quantity_id) for edge in example.candidate_edges
    }
    binding_pairs = {
        (edge.concept_id, edge.quantity_id) for edge in example.binding_edges
    }
    if len(candidate_pairs) != len(example.candidate_edges):
        raise ValueError("candidate edges must be unique")
    if len(binding_pairs) != len(example.binding_edges):
        raise ValueError("binding edges must be unique")
    for edge in (*example.candidate_edges, *example.binding_edges):
        if edge.concept_id not in concept_ids or edge.quantity_id not in quantity_ids:
            raise ValueError("stage edge references an unknown node")
    if not binding_pairs <= candidate_pairs:
        raise ValueError("binding edge requires an annotated candidate edge")
    role_signatures = set()
    for edge in example.role_edges:
        pair = (edge.concept_id, edge.quantity_id)
        if pair not in binding_pairs:
            raise ValueError("role edge requires an annotated binding")
        signature = (*pair, edge.role)
        if signature in role_signatures:
            raise ValueError("role edges must be unique")
        role_signatures.add(signature)


def _example(row: dict[str, object]) -> StagedGoldExample:
    example = StagedGoldExample(
        example_id=str(row["example_id"]),
        entity=str(row["entity"]),
        holdout_axis=HoldoutAxis(str(row["holdout_axis"])),
        source_kind=str(row["source_kind"]),
        source_sha256=str(row["source_sha256"]),
        available_at=str(row["available_at"]),
        document_period=str(row["document_period"]),
        text=str(row["text"]),
        gold_route=str(row["gold_route"]),
        quantities=tuple(_quantity(item) for item in row["quantities"]),
        concepts=tuple(_concept(item) for item in row["concepts"]),
        candidate_edges=tuple(_edge(item) for item in row["candidate_edges"]),
        binding_edges=tuple(_edge(item) for item in row["binding_edges"]),
        role_edges=tuple(_role(item) for item in row["role_edges"]),
        expected_frames=tuple(dict(item) for item in row["expected_frames"]),
        annotation_source=str(row["annotation_source"]),
    )
    _validate(example)
    return example


def load_staged_gold(path: Path) -> tuple[StagedGoldExample, ...]:
    output = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            output.append(_example(json.loads(raw)))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Invalid staged gold on line {line_number}: {exc}"
            ) from exc
    ids = [example.example_id for example in output]
    if not output or len(ids) != len(set(ids)):
        raise ValueError("staged gold requires non-empty unique example ids")
    return tuple(output)
