from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class SemanticTask(StrEnum):
    CONCEPT = "CONCEPT"
    BINDING = "BINDING"
    ROLE = "ROLE"


class SemanticChallengerUnavailableError(RuntimeError):
    """The optional learned challenger cannot score without degrading safety."""


@dataclass(frozen=True)
class SemanticPairRequest:
    request_id: str
    source_sha256: str
    context: str
    metric_char_start: int
    metric_char_end: int
    quantity_char_start: int
    quantity_char_end: int

    def __post_init__(self) -> None:
        if not self.request_id or len(self.source_sha256) != 64 or not self.context:
            raise ValueError("semantic requests require identity, source hash, and context")
        spans = (
            (self.metric_char_start, self.metric_char_end),
            (self.quantity_char_start, self.quantity_char_end),
        )
        if any(not 0 <= start < end <= len(self.context) for start, end in spans):
            raise ValueError("semantic request spans must be inside the context")

    @property
    def metric_literal(self) -> str:
        return self.context[self.metric_char_start:self.metric_char_end]

    @property
    def quantity_literal(self) -> str:
        return self.context[self.quantity_char_start:self.quantity_char_end]

    @property
    def metric_marked_context(self) -> str:
        return "".join((
            self.context[: self.metric_char_start],
            "[METRIC]",
            self.metric_literal,
            "[/METRIC]",
            self.context[self.metric_char_end :],
        ))

    @property
    def marked_context(self) -> str:
        spans = sorted((
            (self.metric_char_start, self.metric_char_end, "[METRIC]", "[/METRIC]"),
            (self.quantity_char_start, self.quantity_char_end, "[QTY]", "[/QTY]"),
        ))
        if spans[0][1] > spans[1][0]:
            raise ValueError("metric and quantity spans must not overlap")
        output = []
        cursor = 0
        for start, end, opening, closing in spans:
            output.extend((self.context[cursor:start], opening, self.context[start:end], closing))
            cursor = end
        output.append(self.context[cursor:])
        return "".join(output)


@dataclass(frozen=True)
class SemanticScore:
    request_id: str
    task: SemanticTask
    label: str
    confidence: float
    source_sha256: str
    metric_char_start: int
    metric_char_end: int
    quantity_char_start: int
    quantity_char_end: int
    model_id: str
    device: str

    def __post_init__(self) -> None:
        if not self.label or not self.model_id or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("semantic scores require a label, model, and probability")


class SemanticChallenger(Protocol):
    name: str
    device: str

    def score(
        self,
        requests: tuple[SemanticPairRequest, ...],
    ) -> tuple[SemanticScore, ...]: ...


__all__ = [
    "SemanticChallenger",
    "SemanticChallengerUnavailableError",
    "SemanticPairRequest",
    "SemanticScore",
    "SemanticTask",
]
