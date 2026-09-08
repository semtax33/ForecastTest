from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from .annotation_chunks import merge_annotation_chunk_package


_MERGED_FILES = (
    "annotator_a_pairs.csv",
    "annotator_b_pairs.csv",
    "adjudication_template.csv",
    "annotator_a_context_audit.csv",
    "annotator_b_context_audit.csv",
)


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _expected_channel_members(
    manifest: dict[str, object],
    channel: str,
) -> dict[str, str]:
    logical_names = (
        f"annotator_{channel}_pairs.csv",
        f"annotator_{channel}_context_audit.csv",
    )
    output = {}
    for chunk in manifest["chunks"]:
        files = chunk["files"]
        for logical_name in logical_names:
            relative = str(files[logical_name])
            member = Path(relative).name
            if member in output:
                raise ValueError(f"duplicate expected ZIP member: {member}")
            output[member] = relative
    return output


def _read_flat_zip(path: Path, expected: set[str]) -> dict[str, bytes]:
    if not path.exists():
        raise ValueError(f"annotation ZIP is missing: {path}")
    with ZipFile(path) as archive:
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        if any(
            PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
            or PurePosixPath(name).name != name
            for name in names
        ):
            raise ValueError("unsafe or nested ZIP member")
        if len(names) != len(set(names)):
            raise ValueError("annotation ZIP contains duplicate members")
        if set(names) != expected:
            missing = sorted(expected - set(names))
            unexpected = sorted(set(names) - expected)
            raise ValueError(
                f"annotation ZIP member set mismatch: missing={missing}, "
                f"unexpected={unexpected}"
            )
        return {name: archive.read(name) for name in names}


def _write_new_or_identical(path: Path, value: bytes) -> None:
    if path.exists() and path.read_bytes() != value:
        raise ValueError(f"refusing to replace a different submission: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(value)


def import_annotation_chunk_submission(
    *,
    chunks_root: Path,
    annotator_a_zip: Path,
    annotator_b_zip: Path,
    adjudication_files: tuple[Path, ...],
    staging_root: Path,
    output_root: Path,
) -> dict[str, object]:
    """Import flat human chunk artifacts without mutating generated templates."""

    manifest_path = chunks_root / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("annotation chunk manifest is missing")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    expected_a = _expected_channel_members(manifest, "a")
    expected_b = _expected_channel_members(manifest, "b")
    a_members = _read_flat_zip(annotator_a_zip, set(expected_a))
    b_members = _read_flat_zip(annotator_b_zip, set(expected_b))
    expected_adjudication = {
        Path(str(chunk["files"]["adjudication_template.csv"])).name
        for chunk in manifest["chunks"]
    }
    by_name: dict[str, Path] = {}
    for path in adjudication_files:
        if path.name in by_name:
            raise ValueError("adjudication file set contains duplicate names")
        by_name[path.name] = path
    if set(by_name) != expected_adjudication:
        missing = sorted(expected_adjudication - set(by_name))
        unexpected = sorted(set(by_name) - expected_adjudication)
        raise ValueError(
            f"adjudication file set mismatch: missing={missing}, "
            f"unexpected={unexpected}"
        )
    _write_new_or_identical(staging_root / "manifest.json", manifest_bytes)
    for member, relative in expected_a.items():
        _write_new_or_identical(staging_root / relative, a_members[member])
    for member, relative in expected_b.items():
        _write_new_or_identical(staging_root / relative, b_members[member])
    for chunk in manifest["chunks"]:
        relative = str(chunk["files"]["adjudication_template.csv"])
        source = by_name[Path(relative).name]
        if not source.exists():
            raise ValueError(f"adjudication file is missing: {source}")
        _write_new_or_identical(staging_root / relative, source.read_bytes())
    merged_root = staging_root / "_validated_merged"
    package = merge_annotation_chunk_package(
        chunks_root=staging_root,
        output_root=merged_root,
    )
    merged = {name: (merged_root / name).read_bytes() for name in _MERGED_FILES}
    for name, value in merged.items():
        target = output_root / name
        if target.exists() and target.read_bytes() != value:
            raise ValueError(f"refusing to replace a different submission: {name}")
    for name, value in merged.items():
        _write_new_or_identical(output_root / name, value)
    report = {
        "status": "CHUNK_SUBMISSION_IMPORTED_AWAITING_INGESTION",
        "production_enabled": False,
        "chunks": package.chunk_count,
        "contexts": package.context_count,
        "pairs": package.pair_count,
        "source_manifest_sha256": _sha256_bytes(manifest_bytes),
        "input_sha256": {
            annotator_a_zip.name: _sha256_file(annotator_a_zip),
            annotator_b_zip.name: _sha256_file(annotator_b_zip),
            **{
                name: _sha256_file(path)
                for name, path in sorted(by_name.items())
            },
        },
        "merged_sha256": {
            name: _sha256_bytes(value) for name, value in sorted(merged.items())
        },
    }
    report_bytes = (json.dumps(report, indent=2) + "\n").encode("utf-8")
    _write_new_or_identical(
        output_root / "submission_provenance.json",
        report_bytes,
    )
    return report


__all__ = ["import_annotation_chunk_submission"]
