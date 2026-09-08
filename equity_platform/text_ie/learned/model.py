from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..llm.encoder_registry import EncoderSourceSlice
from ..model import TextBlock


class LearnedSpanUnavailableError(RuntimeError):
    """The optional span proposer cannot run without weakening its policy."""


@dataclass(frozen=True)
class LearnedSpanProposal:
    """An exact, source-grounded metric span proposal—not an extracted fact."""

    source_sha256: str
    block_char_start: int
    block_char_end: int
    char_start: int
    char_end: int
    raw_text: str
    raw_label: str
    confidence: float
    model_id: str
    model_revision: str
    canonical_concept: str | None = None

    def __post_init__(self) -> None:
        if len(self.source_sha256) != 64:
            raise ValueError("learned span proposals require a SHA-256 source identity")
        if self.block_char_start < 0 or self.block_char_end <= self.block_char_start:
            raise ValueError("learned span proposals require an ordered block span")
        if self.char_start < 0 or self.char_end <= self.char_start:
            raise ValueError("learned span proposals require an ordered source span")
        if not self.raw_text or not self.raw_label or not self.model_id:
            raise ValueError("learned span proposals require text, label, and model")
        if not self.model_revision:
            raise ValueError("learned span proposals require a model revision")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("learned span proposal confidence must be within [0, 1]")
        if self.canonical_concept is not None and not self.canonical_concept.strip():
            raise ValueError("canonical concept cannot be blank")


class LearnedSpanBackend(Protocol):
    name: str
    device: str

    def propose(
        self,
        block: TextBlock,
        source_slice: EncoderSourceSlice,
    ) -> tuple[LearnedSpanProposal, ...]: ...


@dataclass(frozen=True)
class LearnedSpanRejection:
    model_id: str
    source_sha256: str
    block_char_start: int
    block_char_end: int
    char_start: int
    char_end: int
    reason: str


__all__ = [
    "LearnedSpanBackend",
    "LearnedSpanProposal",
    "LearnedSpanRejection",
    "LearnedSpanUnavailableError",
]
