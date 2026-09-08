from __future__ import annotations

import csv
from pathlib import Path

import pytest

from equity_platform.text_ie.training.annotation_chunks import (
    merge_annotation_chunk_package,
    split_annotation_batch_into_chunks,
)


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _batch(root: Path) -> None:
    pairs = [
        {"pair_id": f"pair-{context}-{pair}", "context_id": context, "reviewed": ""}
        for context, pair_count in (("c1", 2), ("c2", 2), ("c3", 1))
        for pair in range(pair_count)
    ]
    contexts = [
        {"context_id": context, "candidate_graph_complete": ""}
        for context in ("c1", "c2", "c3")
    ]
    _write(root / "annotator_a_pairs.csv", pairs)
    _write(root / "annotator_b_pairs.csv", list(reversed(pairs)))
    _write(root / "annotator_a_context_audit.csv", contexts)
    _write(root / "annotator_b_context_audit.csv", list(reversed(contexts)))
    _write(root / "adjudication_template.csv", pairs)


def test_chunk_package_never_splits_one_context_and_round_trips(tmp_path) -> None:
    batch = tmp_path / "batch"
    chunks = tmp_path / "chunks"
    merged = tmp_path / "merged"
    _batch(batch)

    package = split_annotation_batch_into_chunks(
        batch_root=batch,
        chunks_root=chunks,
        maximum_pairs_per_chunk=3,
    )

    assert package.chunk_count == 2
    assert package.context_count == 3
    assert package.pair_count == 5
    assert all(
        chunk.files["annotator_a_pairs.csv"].startswith("annotator_a/")
        and chunk.files["annotator_b_pairs.csv"].startswith("annotator_b/")
        and chunk.files["adjudication_template.csv"].startswith("adjudicator/")
        for chunk in package.chunks
    )
    for chunk in package.chunks:
        pair_contexts = {
            row["context_id"]
            for row in _read(chunks / chunk.files["annotator_a_pairs.csv"])
        }
        assert pair_contexts == set(chunk.context_ids)
    for path in chunks.rglob("chunk_*__*.csv"):
        rows = _read(path)
        for row in rows:
            if "reviewed" in row:
                row["reviewed"] = "DONE"
            if "candidate_graph_complete" in row:
                row["candidate_graph_complete"] = "TRUE"
        _write(path, rows)

    result = merge_annotation_chunk_package(
        chunks_root=chunks,
        output_root=merged,
    )

    assert result.pair_count == 5
    assert {row["pair_id"] for row in _read(merged / "annotator_a_pairs.csv")} == {
        f"pair-{context}-{pair}"
        for context, pair_count in (("c1", 2), ("c2", 2), ("c3", 1))
        for pair in range(pair_count)
    }


def test_merge_fails_closed_when_a_chunk_loses_a_pair(tmp_path) -> None:
    batch = tmp_path / "batch"
    chunks = tmp_path / "chunks"
    _batch(batch)
    package = split_annotation_batch_into_chunks(
        batch_root=batch,
        chunks_root=chunks,
        maximum_pairs_per_chunk=3,
    )
    path = chunks / package.chunks[0].files["annotator_b_pairs.csv"]
    rows = _read(path)
    _write(path, rows[1:])

    with pytest.raises(ValueError, match="annotator_b_pairs.csv.*id set mismatch"):
        merge_annotation_chunk_package(
            chunks_root=chunks,
            output_root=tmp_path / "merged",
        )


def test_split_rejects_cross_file_pair_context_identity_drift(tmp_path) -> None:
    batch = tmp_path / "batch"
    _batch(batch)
    path = batch / "annotator_b_pairs.csv"
    rows = _read(path)
    rows[0]["context_id"] = "c1" if rows[0]["context_id"] != "c1" else "c2"
    _write(path, rows)

    with pytest.raises(ValueError, match="pair/context identity mismatch"):
        split_annotation_batch_into_chunks(
            batch_root=batch,
            chunks_root=tmp_path / "chunks",
            maximum_pairs_per_chunk=3,
        )


def test_oversized_context_gets_an_atomic_chunk_instead_of_being_split(
    tmp_path,
) -> None:
    batch = tmp_path / "batch"
    chunks = tmp_path / "chunks"
    pairs = [
        {"pair_id": f"pair-{index}", "context_id": "large", "reviewed": ""}
        for index in range(4)
    ]
    contexts = [{"context_id": "large", "candidate_graph_complete": ""}]
    for name in (
        "annotator_a_pairs.csv",
        "annotator_b_pairs.csv",
        "adjudication_template.csv",
    ):
        _write(batch / name, pairs)
    for name in ("annotator_a_context_audit.csv", "annotator_b_context_audit.csv"):
        _write(batch / name, contexts)

    package = split_annotation_batch_into_chunks(
        batch_root=batch,
        chunks_root=chunks,
        maximum_pairs_per_chunk=3,
    )

    assert package.chunk_count == 1
    assert package.chunks[0].context_ids == ("large",)
    assert len(package.chunks[0].pair_ids) == 4
    assert package.oversized_context_ids == ("large",)
