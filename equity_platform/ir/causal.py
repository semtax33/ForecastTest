from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .authority import AuthorityLevel


class Direction(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    CONDITIONAL = "CONDITIONAL"


class IdentificationStatus(StrEnum):
    HYPOTHESIZED = "HYPOTHESIZED"
    MANAGEMENT_CLAIM = "MANAGEMENT_CLAIM"
    ASSOCIATIONAL = "ASSOCIATIONAL"
    TEMPORAL_SUPPORT = "TEMPORAL_SUPPORT"
    QUASI_CAUSAL = "QUASI_CAUSAL"
    CAUSALLY_IDENTIFIED = "CAUSALLY_IDENTIFIED"


@dataclass(frozen=True)
class LagSpec:
    minimum: int
    modal: int
    maximum: int
    unit: str

    def __post_init__(self) -> None:
        if not 0 <= self.minimum <= self.modal <= self.maximum:
            raise ValueError("Lag bounds must be non-negative and ordered")


@dataclass(frozen=True)
class MagnitudeSpec:
    kind: str
    estimate: float | None
    lower: float | None
    upper: float | None

    def __post_init__(self) -> None:
        if self.estimate is not None and self.lower is not None and self.upper is not None:
            if not self.lower <= self.estimate <= self.upper:
                raise ValueError("Magnitude estimate must lie inside its interval")


@dataclass(frozen=True)
class Falsifier:
    horizon: str
    condition: str


@dataclass(frozen=True)
class CausalEdgeIR:
    edge_id: str
    cause: str
    effect: str
    direction: Direction
    mechanism: str
    path: tuple[str, ...]
    lag: LagSpec
    magnitude: MagnitudeSpec
    regime: str | None
    confounders: tuple[str, ...]
    identification: IdentificationStatus
    supporting_evidence: tuple[str, ...]
    contradicting_evidence: tuple[str, ...]
    falsifiers: tuple[Falsifier, ...]
    authority: AuthorityLevel

    def __post_init__(self) -> None:
        if not self.cause or not self.effect or not self.mechanism:
            raise ValueError("Causal edges need cause, effect, and mechanism")
        if self.cause == self.effect:
            raise ValueError("A time-expanded causal edge cannot self-loop")
