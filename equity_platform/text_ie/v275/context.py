from __future__ import annotations

from equity_platform.documents import CanonicalDocument

from ..model import TextBlock
from ..spacy_backend import SpacySemanticBackend


_SCALE_CUES = {
    1_000.0: (
        "amounts are stated in thousands",
        "amounts stated in thousands",
        "dollars in thousands",
    ),
    1_000_000.0: (
        "amounts are stated in millions",
        "amounts stated in millions",
        "dollars in millions",
    ),
    1_000_000_000.0: (
        "amounts are stated in billions",
        "amounts stated in billions",
        "dollars in billions",
    ),
}


def declared_money_scale(
    document: CanonicalDocument,
    block: TextBlock,
    backend: SpacySemanticBackend,
) -> float | None:
    """Return a declared document scale without inheriting any KPI number."""

    preceding = document.text[: block.char_start]
    matches: list[tuple[int, float]] = []
    for scale, phrases in _SCALE_CUES.items():
        matches.extend(
            (start, scale)
            for _, start, _ in backend.phrase_mentions(preceding, phrases)
        )
    return max(matches, default=(0, None), key=lambda item: item[0])[1]
