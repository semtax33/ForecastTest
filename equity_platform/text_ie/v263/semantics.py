from __future__ import annotations

from equity_platform.documents import CanonicalDocument

from ..model import KPIFrame
from ..v24.model import RecallCandidate


def recover_v263_frames(
    document: CanonicalDocument,
    candidates: tuple[RecallCandidate, ...],
    allowed_spans: set[tuple[int, int]],
) -> tuple[KPIFrame, ...]:
    """Compatibility entrypoint delegated to the V2.6.4 semantic-law engine."""

    from ..v264.semantics import recover_v264_frames

    return recover_v264_frames(document, candidates, allowed_spans)

