from __future__ import annotations

from equity_platform.documents import CanonicalDocument

from ..v26 import V26ExtractionResult


def extract_text_kpis_v263(document: CanonicalDocument) -> V26ExtractionResult:
    """Compatibility entrypoint; V2.6.3 regex recovery was retired by V2.6.4."""

    from ..v264.runtime import extract_text_kpis_v264

    return extract_text_kpis_v264(document)

