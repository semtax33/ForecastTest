from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DriverRole(StrEnum):
    PRICE = "P"
    QUANTITY = "Q"
    COST = "C"
    INVESTMENT = "I"


class DataAuthority(StrEnum):
    HISTORICAL_PIT_MODEL_INPUT = "HISTORICAL_PIT_MODEL_INPUT"
    CURRENT_REVISED_CONTEXT_ONLY = "CURRENT_REVISED_CONTEXT_ONLY"
    COMPANY_DISCLOSED_PIT_INPUT = "COMPANY_DISCLOSED_PIT_INPUT"
    NOT_IDENTIFIED = "NOT_IDENTIFIED"


class ForecastAuthority(StrEnum):
    STRONG = "STRONG"
    MIXED = "MIXED"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    NOT_TESTED = "NOT_TESTED"


@dataclass(frozen=True)
class SourceDefinition:
    source: str
    dataset: str
    url: str
    roles: tuple[DriverRole, ...]
    authority: DataAuthority


@dataclass(frozen=True)
class SubindustryProfile:
    code: str
    name: str
    industry_group: str
    representative_ticker: str
    primary_target: str
    price_anchor: str
    quantity_anchor: str
    cost_anchor: str
    investment_anchor: str
    economic_bridge: str
    sources: tuple[SourceDefinition, ...]
    sec_form_regime: str = "10-K_10-Q"

    def validate(self) -> None:
        material = (
            self.code,
            self.name,
            self.industry_group,
            self.representative_ticker,
            self.primary_target,
            self.price_anchor,
            self.quantity_anchor,
            self.cost_anchor,
            self.investment_anchor,
            self.economic_bridge,
        )
        if not all(str(value).strip() for value in material):
            raise ValueError(f"Incomplete subindustry profile: {self.code}")
        covered = {role for source in self.sources for role in source.roles}
        missing = set(DriverRole) - covered
        if missing:
            raise ValueError(f"{self.code} is missing source coverage for {sorted(missing)}")


def classify_forecast_authority(
    *, revenue_mase: float | None, margin_mase: float | None
) -> ForecastAuthority:
    if revenue_mase is None or margin_mase is None:
        return ForecastAuthority.NOT_TESTED
    revenue_pass = revenue_mase < 1.0
    margin_pass = margin_mase < 1.0
    if revenue_pass and margin_pass:
        return ForecastAuthority.STRONG
    if revenue_pass or margin_pass:
        return ForecastAuthority.MIXED
    return ForecastAuthority.DIAGNOSTIC_ONLY
