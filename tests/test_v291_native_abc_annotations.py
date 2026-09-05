from __future__ import annotations

import csv

import pytest

from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training.staged_gold import load_staged_gold
from scripts.architecture.v291_native_abc_annotations import (
    CANDIDATES,
    _literal_span,
    build_annotations,
    write_annotations,
)


def _candidate_rows() -> list[dict[str, str]]:
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_literal_span_requires_explicit_occurrence_when_text_is_ambiguous() -> None:
    with pytest.raises(ValueError, match="ambiguous literal"):
        _literal_span("Revenue then Revenue", "Revenue")

    assert _literal_span("Revenue then Revenue", "Revenue", occurrence=1) == (13, 20)


def test_native_abc_annotations_are_exhaustive_and_loadable(tmp_path) -> None:
    rows = build_annotations(_candidate_rows())
    output = tmp_path / "native-abc-stage-gold.jsonl"
    write_annotations(rows, output)

    corpus = load_staged_gold(output)

    assert len(corpus) == 120
    assert {example.holdout_axis.value for example in corpus} == {"A", "B", "C"}
    assert any(example.expected_frames for example in corpus)
    assert any(example.gold_route == "TABLE_DSL" for example in corpus)
    assert all("DOUBLE_REVIEWED_HUMAN" not in example.annotation_source for example in corpus)
    assert all(
        example.gold_route == "NO_FACT"
        for example in corpus
        if example.source_kind == "INDUSTRY_DATA"
    )
    periods = {
        (example.entity, example.source_kind.removesuffix("_NOTE")): example.document_period
        for example in corpus
        if example.entity != "PUBLIC_INDUSTRY_DATA"
    }
    assert periods[("AAL", "10-K")] == "2025"
    assert periods[("AAL", "10-Q")] == "2026Q2"
    assert periods[("AAME", "10-K")] == "2024"
    assert periods[("AAMI", "10-Q")] == "2026Q2"
    assert periods[("CL", "IR")] == "2026Q2"


def test_native_abc_annotations_fail_closed_on_selection_drift() -> None:
    rows = _candidate_rows()

    with pytest.raises(ValueError, match="selection coverage drift"):
        build_annotations(rows[:-1])


def test_annotation_output_lives_in_gold_data_layer() -> None:
    from scripts.architecture.v291_native_abc_annotations import ANNOTATIONS

    assert ANNOTATIONS == (
        PROJECT_ROOT
        / "data-lake/gold/parser/text_ie/v291_native_abc_stage_gold.jsonl"
    )
