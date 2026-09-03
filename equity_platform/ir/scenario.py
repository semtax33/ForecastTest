from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from .authority import AuthorityLevel


class ScenarioClass(StrEnum):
    POSSIBLE = "POSSIBLE"
    PLAUSIBLE = "PLAUSIBLE"
    PROBABLE = "PROBABLE"


class IdentificationState(StrEnum):
    IDENTIFIED = "IDENTIFIED"
    CONDITIONAL = "CONDITIONAL"
    UNIDENTIFIABLE = "UNIDENTIFIABLE"


@dataclass(frozen=True)
class ScenarioIR:
    scenario_id: str
    scenario_class: ScenarioClass
    assumption_nodes: tuple[str, ...]
    evidence_claims: tuple[str, ...]
    probability_weight: float | None
    authority: AuthorityLevel

    def __post_init__(self) -> None:
        if not self.scenario_id or not self.assumption_nodes:
            raise ValueError("Scenarios require an id and assumption nodes")
        if self.probability_weight is not None:
            if not isfinite(self.probability_weight) or not 0 <= self.probability_weight <= 1:
                raise ValueError("Scenario probability weight must lie in [0, 1]")
        if self.scenario_class is ScenarioClass.POSSIBLE and self.authority >= AuthorityLevel.VALUATION_INPUT:
            raise ValueError("Possible scenarios cannot directly receive valuation authority")


@dataclass(frozen=True)
class ExpectationsGapIR:
    gap_id: str
    model_node: str
    market_implied_node: str
    metric: str
    value: float | None
    identification: IdentificationState
    authority: AuthorityLevel

    def __post_init__(self) -> None:
        if not self.gap_id or not self.model_node or not self.market_implied_node:
            raise ValueError("Expectations gaps require explicit model and market nodes")
        if self.identification is IdentificationState.UNIDENTIFIABLE:
            if self.value is not None or self.authority >= AuthorityLevel.VALUATION_INPUT:
                raise ValueError("Unidentifiable gaps cannot carry a value or valuation authority")
