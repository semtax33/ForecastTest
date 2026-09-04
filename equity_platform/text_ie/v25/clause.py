from __future__ import annotations

import re

from ..model import TextBlock
from .model import ClauseSpan


_BOUNDARY = re.compile(
    r"(?:[.!?][\"”']?\s+(?=[A-Z$])|[;•·]+|,\s+(?=(?:while|whereas|but)\b)|"
    r"\s+(?=(?:while|whereas)\b))",
    re.IGNORECASE,
)


def segment_clauses(block: TextBlock) -> tuple[ClauseSpan, ...]:
    """Split only on hard semantic boundaries; offsets remain source exact."""

    starts = [0]
    ends: list[int] = []
    for match in _BOUNDARY.finditer(block.text):
        ends.append(match.start())
        starts.append(match.end())
    ends.append(len(block.text))
    clauses = []
    for start, end in zip(starts, ends):
        while start < end and block.text[start].isspace():
            start += 1
        while end > start and block.text[end - 1].isspace():
            end -= 1
        if end <= start:
            continue
        clauses.append(ClauseSpan(block, start, end, block.text[start:end]))
    return tuple(clauses)
