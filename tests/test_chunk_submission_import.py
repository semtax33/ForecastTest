from __future__ import annotations

import csv
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from equity_platform.text_ie.training import (
    import_annotation_chunk_submission,
    split_annotation_batch_into_chunks,
)


PAIR_FILES = (
    "annotator_a_pairs.csv",
    "annotator_b_pairs.csv",
    "adjudication_template.csv",
)
CONTEXT_FILES = (
    "annotator_a_context_audit.csv",
    "annotator_b_context_audit.csv",
)


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _package(tmp_path: Path) -> Path:
    batch = tmp_path / "batch"
    pair_rows = [
        {"pair_id": "pair-1", "context_id": "context-1", "answer": "one"},
        {"pair_id": "pair-2", "context_id": "context-2", "answer": "two"},
    ]
    context_rows = [
        {"context_id": "context-1", "complete": "TRUE"},
        {"context_id": "context-2", "complete": "TRUE"},
    ]
    for name in PAIR_FILES:
        _write(batch / name, pair_rows)
    for name in CONTEXT_FILES:
        _write(batch / name, context_rows)
    chunks = tmp_path / "chunks"
    split_annotation_batch_into_chunks(
        batch_root=batch,
        chunks_root=chunks,
        maximum_pairs_per_chunk=1,
    )
    return chunks


def _zip_channel(chunks: Path, channel: str, output: Path) -> None:
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted((chunks / channel).glob("*.csv")):
            archive.write(path, arcname=path.name)


def test_complete_zip_submission_imports_without_mutating_templates(tmp_path) -> None:
    chunks = _package(tmp_path)
    a_zip = tmp_path / "a.zip"
    b_zip = tmp_path / "b.zip"
    _zip_channel(chunks, "annotator_a", a_zip)
    _zip_channel(chunks, "annotator_b", b_zip)
    original = (chunks / "annotator_a" / "chunk_001__pairs.csv").read_bytes()

    report = import_annotation_chunk_submission(
        chunks_root=chunks,
        annotator_a_zip=a_zip,
        annotator_b_zip=b_zip,
        adjudication_files=tuple(sorted((chunks / "adjudicator").glob("*.csv"))),
        staging_root=tmp_path / "staging",
        output_root=tmp_path / "submission",
    )

    assert report["status"] == "CHUNK_SUBMISSION_IMPORTED_AWAITING_INGESTION"
    assert report["chunks"] == 2
    assert report["contexts"] == 2
    assert report["pairs"] == 2
    assert (chunks / "annotator_a" / "chunk_001__pairs.csv").read_bytes() == original
    assert (tmp_path / "submission" / "annotator_a_pairs.csv").exists()
    assert (tmp_path / "submission" / "submission_provenance.json").exists()


def test_import_rejects_unexpected_or_unsafe_zip_member(tmp_path) -> None:
    chunks = _package(tmp_path)
    a_zip = tmp_path / "a.zip"
    b_zip = tmp_path / "b.zip"
    _zip_channel(chunks, "annotator_b", b_zip)
    with ZipFile(a_zip, "w") as archive:
        archive.writestr("../chunk_001__pairs.csv", "malicious")

    with pytest.raises(ValueError, match="unsafe or nested ZIP member"):
        import_annotation_chunk_submission(
            chunks_root=chunks,
            annotator_a_zip=a_zip,
            annotator_b_zip=b_zip,
            adjudication_files=tuple(sorted((chunks / "adjudicator").glob("*.csv"))),
            staging_root=tmp_path / "staging",
            output_root=tmp_path / "submission",
        )


def test_import_rejects_incomplete_adjudication_file_set(tmp_path) -> None:
    chunks = _package(tmp_path)
    a_zip = tmp_path / "a.zip"
    b_zip = tmp_path / "b.zip"
    _zip_channel(chunks, "annotator_a", a_zip)
    _zip_channel(chunks, "annotator_b", b_zip)
    adjudications = tuple(sorted((chunks / "adjudicator").glob("*.csv")))

    with pytest.raises(ValueError, match="adjudication file set mismatch"):
        import_annotation_chunk_submission(
            chunks_root=chunks,
            annotator_a_zip=a_zip,
            annotator_b_zip=b_zip,
            adjudication_files=adjudications[:-1],
            staging_root=tmp_path / "staging",
            output_root=tmp_path / "submission",
        )


def test_import_refuses_to_replace_different_existing_submission(tmp_path) -> None:
    chunks = _package(tmp_path)
    a_zip = tmp_path / "a.zip"
    b_zip = tmp_path / "b.zip"
    _zip_channel(chunks, "annotator_a", a_zip)
    _zip_channel(chunks, "annotator_b", b_zip)
    output = tmp_path / "submission"
    output.mkdir()
    (output / "annotator_a_pairs.csv").write_text("different", encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to replace a different submission"):
        import_annotation_chunk_submission(
            chunks_root=chunks,
            annotator_a_zip=a_zip,
            annotator_b_zip=b_zip,
            adjudication_files=tuple(sorted((chunks / "adjudicator").glob("*.csv"))),
            staging_root=tmp_path / "staging",
            output_root=output,
        )

