from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path


_PAIR_FILES = (
    "annotator_a_pairs.csv",
    "annotator_b_pairs.csv",
    "adjudication_template.csv",
)
_CONTEXT_FILES = (
    "annotator_a_context_audit.csv",
    "annotator_b_context_audit.csv",
)
_FILES = (*_PAIR_FILES, *_CONTEXT_FILES)
_CHUNK_LOCATIONS = {
    "annotator_a_pairs.csv": ("annotator_a", "pairs.csv"),
    "annotator_a_context_audit.csv": ("annotator_a", "context_audit.csv"),
    "annotator_b_pairs.csv": ("annotator_b", "pairs.csv"),
    "annotator_b_context_audit.csv": ("annotator_b", "context_audit.csv"),
    "adjudication_template.csv": ("adjudicator", "adjudication.csv"),
}


@dataclass(frozen=True)
class AnnotationChunk:
    chunk_id: str
    context_ids: tuple[str, ...]
    pair_ids: tuple[str, ...]
    files: dict[str, str]


@dataclass(frozen=True)
class AnnotationChunkPackage:
    chunk_count: int
    context_count: int
    pair_count: int
    chunks: tuple[AnnotationChunk, ...]
    oversized_context_ids: tuple[str, ...] = ()


def _read(path: Path) -> tuple[dict[str, str], ...]:
    if not path.exists():
        raise ValueError(f"annotation batch file is missing: {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = tuple(dict(row) for row in csv.DictReader(handle))
    if not rows:
        raise ValueError(f"annotation batch file is empty: {path.name}")
    return rows


def _write(path: Path, rows: tuple[dict[str, str], ...]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty annotation chunk: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _unique_ids(rows, key: str, file_name: str) -> set[str]:
    values = [str(row.get(key, "")).strip() for row in rows]
    if "" in values or len(values) != len(set(values)):
        raise ValueError(f"{file_name} requires unique non-empty {key}")
    return set(values)


def _package_from_manifest(row: dict[str, object]) -> AnnotationChunkPackage:
    chunks = tuple(AnnotationChunk(
        chunk_id=str(chunk["chunk_id"]),
        context_ids=tuple(str(value) for value in chunk["context_ids"]),
        pair_ids=tuple(str(value) for value in chunk["pair_ids"]),
        files={str(key): str(value) for key, value in chunk["files"].items()},
    ) for chunk in row["chunks"])
    return AnnotationChunkPackage(
        chunk_count=int(row["chunk_count"]),
        context_count=int(row["context_count"]),
        pair_count=int(row["pair_count"]),
        chunks=chunks,
        oversized_context_ids=tuple(
            str(value) for value in row.get("oversized_context_ids", ())
        ),
    )


def split_annotation_batch_into_chunks(
    *,
    batch_root: Path,
    chunks_root: Path,
    maximum_pairs_per_chunk: int = 400,
) -> AnnotationChunkPackage:
    """Split by whole context so a candidate graph never crosses files."""

    if maximum_pairs_per_chunk < 1:
        raise ValueError("maximum_pairs_per_chunk must be positive")
    rows = {name: _read(batch_root / name) for name in _FILES}
    pair_sets = {
        name: _unique_ids(rows[name], "pair_id", name) for name in _PAIR_FILES
    }
    if len({frozenset(values) for values in pair_sets.values()}) != 1:
        raise ValueError("A/B/adjudication pair sets do not match")
    context_sets = {
        name: _unique_ids(rows[name], "context_id", name)
        for name in _CONTEXT_FILES
    }
    if len({frozenset(values) for values in context_sets.values()}) != 1:
        raise ValueError("A/B context audit sets do not match")
    context_ids = next(iter(context_sets.values()))
    pair_context_maps = {
        name: {row["pair_id"]: row["context_id"] for row in rows[name]}
        for name in _PAIR_FILES
    }
    if any(
        pair_context_maps[name] != pair_context_maps["annotator_a_pairs.csv"]
        for name in _PAIR_FILES[1:]
    ):
        raise ValueError("pair/context identity mismatch across annotation files")
    if not set(pair_context_maps["annotator_a_pairs.csv"].values()) <= context_ids:
        raise ValueError("pair rows reference contexts outside the context audit")
    pair_rows = {row["pair_id"]: row for row in rows["annotator_a_pairs.csv"]}
    pairs_by_context = {
        context_id: tuple(sorted(
            pair_id
            for pair_id, row in pair_rows.items()
            if row["context_id"] == context_id
        ))
        for context_id in context_ids
    }
    if any(not values for values in pairs_by_context.values()):
        raise ValueError("every context must own at least one pair")
    oversized_context_ids = tuple(sorted(
        context_id
        for context_id, values in pairs_by_context.items()
        if len(values) > maximum_pairs_per_chunk
    ))
    groups: list[list[str]] = []
    active: list[str] = []
    active_pairs = 0
    for context_id in sorted(context_ids):
        count = len(pairs_by_context[context_id])
        if active and active_pairs + count > maximum_pairs_per_chunk:
            groups.append(active)
            active = []
            active_pairs = 0
        active.append(context_id)
        active_pairs += count
    if active:
        groups.append(active)
    chunks = []
    for index, context_group in enumerate(groups, start=1):
        chunk_id = f"chunk_{index:03d}"
        selected_contexts = set(context_group)
        selected_pairs = {
            pair_id
            for context_id in context_group
            for pair_id in pairs_by_context[context_id]
        }
        files = {}
        for name in _FILES:
            key = "pair_id" if name in _PAIR_FILES else "context_id"
            selected_ids = selected_pairs if key == "pair_id" else selected_contexts
            selected_rows = tuple(
                row for row in rows[name] if row[key] in selected_ids
            )
            channel, suffix = _CHUNK_LOCATIONS[name]
            relative_path = Path(channel) / f"{chunk_id}__{suffix}"
            _write(chunks_root / relative_path, selected_rows)
            files[name] = relative_path.as_posix()
        chunks.append(AnnotationChunk(
            chunk_id=chunk_id,
            context_ids=tuple(context_group),
            pair_ids=tuple(sorted(selected_pairs)),
            files=files,
        ))
    package = AnnotationChunkPackage(
        chunk_count=len(chunks),
        context_count=len(context_ids),
        pair_count=len(next(iter(pair_sets.values()))),
        chunks=tuple(chunks),
        oversized_context_ids=oversized_context_ids,
    )
    manifest = {
        "schema_version": "1.0.0",
        "source_batch": str(batch_root),
        "maximum_pairs_per_chunk": maximum_pairs_per_chunk,
        "chunk_count": package.chunk_count,
        "context_count": package.context_count,
        "pair_count": package.pair_count,
        "oversized_context_ids": list(package.oversized_context_ids),
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "context_ids": list(chunk.context_ids),
                "pair_ids": list(chunk.pair_ids),
                "files": chunk.files,
            }
            for chunk in package.chunks
        ],
    }
    chunks_root.mkdir(parents=True, exist_ok=True)
    (chunks_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return package


def merge_annotation_chunk_package(
    *,
    chunks_root: Path,
    output_root: Path,
) -> AnnotationChunkPackage:
    """Reassemble edited chunks while requiring every original identity once."""

    manifest_path = chunks_root / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("annotation chunk manifest is missing")
    package = _package_from_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    if package.chunk_count != len(package.chunks):
        raise ValueError("annotation chunk manifest count mismatch")
    all_context_ids = {
        value for chunk in package.chunks for value in chunk.context_ids
    }
    all_pair_ids = {value for chunk in package.chunks for value in chunk.pair_ids}
    if len(all_context_ids) != package.context_count or len(all_pair_ids) != package.pair_count:
        raise ValueError("annotation chunk manifest contains duplicate or missing ids")
    for name in _FILES:
        key = "pair_id" if name in _PAIR_FILES else "context_id"
        expected_all = all_pair_ids if key == "pair_id" else all_context_ids
        merged = []
        for chunk in package.chunks:
            chunk_rows = _read(chunks_root / chunk.files[name])
            observed = _unique_ids(chunk_rows, key, name)
            expected = set(chunk.pair_ids if key == "pair_id" else chunk.context_ids)
            if observed != expected:
                raise ValueError(f"{name} chunk id set mismatch: {chunk.chunk_id}")
            merged.extend(chunk_rows)
        observed_all = _unique_ids(tuple(merged), key, name)
        if observed_all != expected_all:
            raise ValueError(f"{name} merged id set mismatch")
        _write(output_root / name, tuple(merged))
    return package


__all__ = [
    "AnnotationChunk",
    "AnnotationChunkPackage",
    "merge_annotation_chunk_package",
    "split_annotation_batch_into_chunks",
]
