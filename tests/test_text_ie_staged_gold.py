from __future__ import annotations

import json

import pytest

from equity_platform.text_ie import training
from equity_platform.text_ie.training.staged_gold import load_staged_gold


def _valid_row() -> dict[str, object]:
    return {
        "example_id": "A-FUTURE-Q1-001",
        "entity": "TEST",
        "holdout_axis": "A",
        "source_kind": "IR",
        "source_sha256": "a" * 64,
        "available_at": "2026-09-05",
        "document_period": "2026Q2",
        "text": "Revenue was $10 million.",
        "gold_route": "TEXT_IE",
        "quantities": [
            {
                "node_id": "q1",
                "kind": "MONEY",
                "value": 10000000.0,
                "char_start": 12,
                "char_end": 23,
            }
        ],
        "concepts": [
            {
                "node_id": "c1",
                "concept": "REVENUE",
                "char_start": 0,
                "char_end": 7,
            }
        ],
        "candidate_edges": [{"concept_id": "c1", "quantity_id": "q1"}],
        "binding_edges": [{"concept_id": "c1", "quantity_id": "q1"}],
        "role_edges": [
            {
                "concept_id": "c1",
                "quantity_id": "q1",
                "role": "VALUE_CURRENT",
            }
        ],
        "expected_frames": [
            {"concept": "REVENUE", "frame": "ABSOLUTE_VALUE", "value": 10000000.0}
        ],
        "annotation_source": "DOUBLE_REVIEWED_HUMAN",
    }


def test_staged_gold_loads_explicit_graph_nodes_and_edges(tmp_path) -> None:
    path = tmp_path / "staged.jsonl"
    path.write_text(json.dumps(_valid_row()) + "\n", encoding="utf-8")

    corpus = load_staged_gold(path)

    assert corpus[0].holdout_axis.value == "A"
    assert corpus[0].source_kind == "IR"
    assert corpus[0].source_sha256 == "a" * 64
    assert corpus[0].quantities[0].value == 10_000_000.0
    assert corpus[0].role_edges[0].role == "VALUE_CURRENT"


def test_staged_gold_rejects_role_edge_without_a_binding(tmp_path) -> None:
    row = _valid_row()
    row["binding_edges"] = []
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="role edge requires an annotated binding"):
        load_staged_gold(path)


def test_training_package_preserves_existing_and_staged_public_exports() -> None:
    assert training.GoldExample
    assert training.calibration_metrics
    assert training.ReviewAnnotation
    assert training.WeakLabel
    assert training.StagedGoldExample
    assert training.load_staged_gold


def test_staged_gold_rejects_invalid_release_date(tmp_path) -> None:
    row = _valid_row()
    row["available_at"] = "future-ish"
    path = tmp_path / "invalid-date.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="available_at"):
        load_staged_gold(path)


def test_staged_gold_allows_an_exhaustive_no_fact_negative(tmp_path) -> None:
    row = _valid_row()
    row.update({
        "example_id": "C-NO-FACT-001",
        "gold_route": "NO_FACT",
        "quantities": [],
        "concepts": [],
        "candidate_edges": [],
        "binding_edges": [],
        "role_edges": [],
        "expected_frames": [],
    })
    path = tmp_path / "no-fact.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    corpus = load_staged_gold(path)

    assert corpus[0].gold_route == "NO_FACT"
    assert corpus[0].concepts == ()
    assert corpus[0].quantities == ()


def test_staged_gold_rejects_empty_positive_text_example(tmp_path) -> None:
    row = _valid_row()
    row.update({
        "quantities": [],
        "concepts": [],
        "candidate_edges": [],
        "binding_edges": [],
        "role_edges": [],
        "expected_frames": [],
    })
    path = tmp_path / "empty-positive.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="non-NO_FACT"):
        load_staged_gold(path)


@pytest.mark.parametrize("source_kind", ["10-K_NOTE", "10-Q_NOTE"])
def test_staged_gold_accepts_financial_statement_note_sources(
    tmp_path,
    source_kind: str,
) -> None:
    row = _valid_row()
    row["source_kind"] = source_kind
    path = tmp_path / "note-source.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    corpus = load_staged_gold(path)

    assert corpus[0].source_kind == source_kind
