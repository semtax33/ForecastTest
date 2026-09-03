from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AnchorDefinition:
    name: str
    unit: str
    financial_targets: tuple[str, ...]
    source_concepts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.financial_targets or not self.source_concepts:
            raise ValueError("An anchor needs a name, targets, and source concepts")


@dataclass(frozen=True)
class SectorDefinition:
    sector: str
    subindustry: str
    tickers: tuple[str, ...]
    anchors: tuple[AnchorDefinition, ...]

    def __post_init__(self) -> None:
        if not self.sector or not self.subindustry or not self.tickers:
            raise ValueError("A sector definition needs a sector, subindustry, and tickers")
        if len(set(self.tickers)) != len(self.tickers):
            raise ValueError("Ticker definitions must be unique")


@dataclass(frozen=True)
class ForecastSnapshot:
    forecast_as_of: str
    model_version: str
    sector: str
    subindustry: str
    ticker: str
    target_period: str
    input_hash: str
    revenue_forecast_usd: float | None
    ebit_forecast_usd: float | None
    margin_forecast_pct: float | None
    fcff_forecast_usd: float | None
    roic_forecast_pct: float | None
    forward_dcf_value_per_share: float | None
    reverse_dcf_metric: str | None
    reverse_dcf_value: float | None
    expectations_gap_pct: float | None
    consensus_value_usd: float | None
    consensus_as_of: str | None
    source_manifest_sha256: str

    def as_row(self) -> dict[str, Any]:
        return asdict(self)
