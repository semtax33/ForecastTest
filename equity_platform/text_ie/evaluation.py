from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any


_SEMANTIC_IDENTITY_FIELDS = (
    "concept",
    "frame",
    "value",
    "change",
    "lower_value",
    "upper_value",
    "polarity",
)


def semantic_frame_signature(frame: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return the meaning-bearing identity used for duplicate evaluation."""
    return tuple(frame.get(field) for field in _SEMANTIC_IDENTITY_FIELDS)


def count_semantic_duplicate_frames(
    frame_groups: Iterable[Iterable[Mapping[str, Any]]],
) -> int:
    """Count exact semantic duplicates without merging opposite directions."""
    duplicate_count = 0
    for frames in frame_groups:
        counts = Counter(semantic_frame_signature(frame) for frame in frames)
        duplicate_count += sum(count - 1 for count in counts.values())
    return duplicate_count
