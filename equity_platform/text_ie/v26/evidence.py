from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT


class EvidenceChannel(StrEnum):
    SEC_10K = "SEC_10K"
    SEC_10Q = "SEC_10Q"
    COMPANY_IR = "COMPANY_IR"
    SEC_FINANCIAL_STATEMENT_NOTE = "SEC_FINANCIAL_STATEMENT_NOTE"
    INDUSTRY_STATISTIC = "INDUSTRY_STATISTIC"


@dataclass(frozen=True)
class EvidenceSource:
    ticker: str | None
    channel: EvidenceChannel
    path: Path
    sha256: str
    available_at: str | None
    authority_role: str


_KIND_CHANNEL = {
    "10-K": EvidenceChannel.SEC_10K,
    "10-Q": EvidenceChannel.SEC_10Q,
    "ir": EvidenceChannel.COMPANY_IR,
}


DEFAULT_INDUSTRY_MAP = {
    "A": ("Health Care", "pharma"),
    "AA": ("Materials", "chemicals"),
    "AAL": ("Industrials", "airlines"),
    "AAOI": ("Information Technology", "semiconductors"),
    "AAON": ("Industrials", "machinery"),
    "AARD": ("Health Care", "pharma"),
    "ABAT": ("Materials", "chemicals"),
    "ABCB": ("Financials", "banks"),
    "ABCL": ("Health Care", "pharma"),
    "AACO": ("Financials", "banks"),
}


def load_holdout_evidence_sources(
    config_path: Path = PROJECT_ROOT / "configs/certification/platform_v26_fourth_holdout.toml",
    *,
    arcana_lake: Path = Path("D:/Programming/python_example/Arcana/data-lake"),
) -> tuple[EvidenceSource, ...]:
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    inventory = pd.read_csv(PROJECT_ROOT / str(config["source_inventory"]))
    root = arcana_lake / "bronze/sec/fillings"
    output = []
    for row in inventory.itertuples(index=False):
        path = root / str(row.kind) / str(row.ticker) / str(row.file_name)
        actual = sha256_file(path)
        if actual != row.sha256:
            raise ValueError(f"V2.6 evidence hash mismatch: {row.ticker}/{row.kind}")
        output.append(EvidenceSource(
            ticker=str(row.ticker),
            channel=_KIND_CHANNEL[str(row.kind)],
            path=path,
            sha256=actual,
            available_at=str(row.file_name)[:10],
            authority_role="COMPANY_EVIDENCE",
        ))
    return tuple(output)


def industry_context(
    ticker: str,
    registry_path: Path = PROJECT_ROOT / "configs/industry_sensor_registry.csv",
) -> pd.DataFrame:
    """Return context-only public statistics; never emit company facts."""

    sector, subindustry = DEFAULT_INDUSTRY_MAP[ticker]
    registry = pd.read_csv(registry_path)
    selected = registry.loc[
        registry["sector"].eq(sector) & registry["subindustry"].eq(subindustry)
    ].copy()
    selected.insert(0, "ticker", ticker)
    selected["evidence_channel"] = EvidenceChannel.INDUSTRY_STATISTIC.value
    selected["authority_role"] = "CONTEXT_ONLY_NOT_COMPANY_FACT"
    return selected.reset_index(drop=True)
