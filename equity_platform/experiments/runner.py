from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
import tomllib
from typing import Callable, Generic, Mapping, TypeVar

import pandas as pd


T = TypeVar("T")


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    version: str
    config_path: Path
    output_path: Path


@dataclass(frozen=True)
class StageRecord:
    sequence: int
    stage: str
    status: str
    consumes: tuple[str, ...]
    produces: tuple[str, ...]
    elapsed_seconds: float


class ExperimentRunner(Generic[T]):
    """Small deterministic shell around functional research stages.

    The runner owns configuration identity and execution lineage only. Domain
    calculations remain pure functions and can be tested independently.
    """

    def __init__(self, *, root: Path, spec: ExperimentSpec) -> None:
        self.root = root.resolve()
        self.spec = spec
        self.config = tomllib.loads(
            (self.root / spec.config_path).read_text(encoding="utf-8")
        )
        configured_id = self.config.get("experiment_id")
        configured_version = self.config.get("version")
        if configured_id != spec.experiment_id:
            raise ValueError(
                f"Experiment id mismatch: config={configured_id!r}, spec={spec.experiment_id!r}"
            )
        if configured_version != spec.version:
            raise ValueError(
                f"Experiment version mismatch: config={configured_version!r}, spec={spec.version!r}"
            )
        self._records: list[StageRecord] = []

    @property
    def output_path(self) -> Path:
        return self.root / self.spec.output_path

    def stage(
        self,
        name: str,
        build: Callable[[], T],
        *,
        consumes: tuple[str, ...] = (),
        produces: tuple[str, ...] | None = None,
    ) -> T:
        if not name or any(record.stage == name for record in self._records):
            raise ValueError(f"Stage names must be unique and non-empty: {name!r}")
        started = perf_counter()
        try:
            result = build()
        except Exception:
            self._records.append(
                StageRecord(
                    sequence=len(self._records) + 1,
                    stage=name,
                    status="FAILED",
                    consumes=consumes,
                    produces=(),
                    elapsed_seconds=perf_counter() - started,
                )
            )
            raise
        resolved_produces: tuple[str, ...] = produces or ()
        if produces is None and isinstance(result, Mapping):
            resolved_produces = tuple(sorted(str(key) for key in result))
        self._records.append(
            StageRecord(
                sequence=len(self._records) + 1,
                stage=name,
                status="COMPLETED",
                consumes=consumes,
                produces=resolved_produces,
                elapsed_seconds=perf_counter() - started,
            )
        )
        return result

    def ledger(self, *, include_timing: bool = False) -> pd.DataFrame:
        """Return deterministic lineage by default; timing is operational telemetry."""

        rows = []
        for record in self._records:
            row = asdict(record)
            if not include_timing:
                row.pop("elapsed_seconds")
            row["experiment_id"] = self.spec.experiment_id
            row["version"] = self.spec.version
            row["consumes"] = "|".join(record.consumes)
            row["produces"] = "|".join(record.produces)
            rows.append(row)
        return pd.DataFrame(rows)
