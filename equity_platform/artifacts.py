from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_files(root: Path, relative_paths: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in sorted(set(relative_paths)):
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Required artifact is missing: {relative}")
        result[relative] = sha256_file(path)
    return result


def content_hash(values: Mapping[str, Any]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def freeze_manifest(
    *,
    root: Path,
    manifest_path: Path,
    name: str,
    version: str,
    relative_paths: Iterable[str],
    assertions: Mapping[str, Any],
    parents: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    target = root / manifest_path
    if target.exists():
        return verify_manifest(root=root, manifest_path=manifest_path)
    manifest = {
        "name": name,
        "version": version,
        "frozen_as_of": date.today().isoformat(),
        "immutable": True,
        "research_frozen": True,
        "assertions": dict(assertions),
        "parents": dict(parents or {}),
        "files": hash_files(root, relative_paths),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return verify_manifest(root=root, manifest_path=manifest_path)


def verify_manifest(*, root: Path, manifest_path: Path) -> dict[str, Any]:
    target = root / manifest_path
    manifest = json.loads(target.read_text(encoding="utf-8"))
    failures: list[str] = []
    for relative, expected in manifest["files"].items():
        path = root / relative
        if not path.is_file():
            failures.append(f"missing:{relative}")
        elif sha256_file(path) != expected:
            failures.append(f"hash:{relative}")
    if failures:
        raise ValueError(f"Frozen manifest verification failed: {failures}")
    return {
        **manifest,
        "manifest_path": str(target),
        "manifest_sha256": sha256_file(target),
        "verified_files": len(manifest["files"]),
    }
