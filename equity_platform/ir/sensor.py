from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from .authority import AuthorityLevel, DriverRole


class SensorTransform(StrEnum):
    LEVEL = "LEVEL"
    YOY_PCT = "YOY_PCT"
    QOQ_PCT = "QOQ_PCT"
    SPREAD = "SPREAD"
    WEIGHTED_BASKET = "WEIGHTED_BASKET"


@dataclass(frozen=True)
class SensorIR:
    sensor_id: str
    source: str
    dataset: str
    series_id: str
    role: DriverRole
    target_scope: str
    frequency: str
    unit: str
    transform: SensorTransform
    availability_lag_days: int
    authority: AuthorityLevel
    proxy_status: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        material = (
            self.sensor_id,
            self.source,
            self.dataset,
            self.series_id,
            self.target_scope,
            self.frequency,
            self.unit,
            self.proxy_status,
        )
        if not all(str(value).strip() for value in material):
            raise ValueError("SensorIR identity fields must not be blank")
        if self.availability_lag_days < 0:
            raise ValueError("Sensor availability lag cannot be negative")
        if not isfinite(self.weight) or self.weight < 0:
            raise ValueError("Sensor weight must be finite and non-negative")
