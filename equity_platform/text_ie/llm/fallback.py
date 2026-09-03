from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from equity_platform.ir import AuthorityLevel, ExtractionMethod

from ..model import KPIFrame, ReviewItem, TextBlock, VerificationStatus


class LLMTextIEBackend(Protocol):
    def propose(self, block: TextBlock) -> tuple[KPIFrame, ...]: ...


def verify_llm_frame(
    frame: KPIFrame,
    block: TextBlock,
) -> KPIFrame | ReviewItem:
    """Fail closed unless an LLM proposal reproduces an exact local source span."""

    if frame.extraction_method is not ExtractionMethod.LLM:
        raise ValueError("Only LLM proposals belong in the fallback verifier")
    span_matches = (
        frame.source.sha256 == block.source.sha256
        and frame.source_span.literal == block.text
        and frame.source_span.char_start == block.char_start
        and frame.source_span.char_end == block.char_end
    )
    if not span_matches:
        return ReviewItem(
            sentence_index=block.sentence_index,
            rule_id=frame.rule_id,
            status="REVIEW_LLM_SOURCE_SPAN_MISMATCH",
            reason="LLM proposal is not exactly grounded in the supplied TextBlock",
            source_span=frame.source_span,
        )
    return replace(
        frame,
        authority=min(frame.authority, AuthorityLevel.RESEARCH_DIAGNOSTIC),
        verification_status=VerificationStatus.VERIFIED,
        verified_by="EXACT_SOURCE_SPAN_VERIFIER",
    )

