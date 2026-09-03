from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Any

from equity_platform.artifacts import freeze_manifest


def freeze_research_benchmark(
    *,
    root: Path,
    manifest_path: Path,
    name: str,
    version: str,
    relative_paths: Iterable[str],
    assertions: Mapping[str, Any],
    parents: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Freeze research only after terminal and production authority are denied."""
    if not bool(assertions.get("research_freeze_eligible")):
        raise ValueError("Research benchmark is not freeze eligible")
    if bool(assertions.get("terminal_input_allowed")):
        raise ValueError("Research freeze cannot grant terminal authority")
    if bool(assertions.get("production_promoted")):
        raise ValueError("Research freeze cannot grant production authority")
    return freeze_manifest(
        root=root,
        manifest_path=manifest_path,
        name=name,
        version=version,
        relative_paths=relative_paths,
        assertions=assertions,
        parents=parents,
    )
