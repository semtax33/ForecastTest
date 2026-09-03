"""Canonical ForecastTest data-lake locations.

The catalog keeps physical medallion paths out of model code.  Callers that
receive an alternate lake root (for tests or replay) can use ``DataCatalog``;
ordinary workspace code can import ``DATA``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import PROJECT_ROOT


@dataclass(frozen=True)
class DataCatalog:
    lake: Path

    @property
    def bronze(self) -> Path:
        return self.lake / "bronze"

    @property
    def silver(self) -> Path:
        return self.lake / "silver"

    @property
    def gold(self) -> Path:
        return self.lake / "gold"

    @property
    def manual_consensus(self) -> Path:
        return self.bronze / "manual_consensus" / "analyst_consensus.csv"

    def snapshot(self, name: str) -> Path:
        return self.bronze / "snapshots" / name

    def model(self, version: str) -> Path:
        return self.silver / "models" / version

    def champion(self, version: str) -> Path:
        return self.gold / "champions" / version

    @property
    def v21(self) -> Path:
        return self.model("v2_1")

    @property
    def v33(self) -> Path:
        return self.champion("v3_3")

    @property
    def company_kpi_snapshot(self) -> Path:
        return self.snapshot("phase2_4_company_kpi")

    @property
    def rig_snapshot(self) -> Path:
        return self.snapshot("phase2_4_rig")

    @property
    def steo_snapshot(self) -> Path:
        return self.snapshot("phase2_4_steo")

    @property
    def macro_snapshot(self) -> Path:
        return self.snapshot("v3_6_macro")


DATA = DataCatalog(PROJECT_ROOT / "data-lake")

