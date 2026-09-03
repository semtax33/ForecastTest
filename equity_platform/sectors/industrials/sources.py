from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

from equity_platform.artifacts import sha256_file


REQUIRED_SOURCE_COLUMNS = {
    "fiscal_year",
    "filing_date",
    "accession",
    "primary_document",
    "source_url",
    "local_path",
}


def load_cat_10k_sources(
    root: Path,
    catalog_path: Path,
    cutoff: pd.Timestamp,
    *,
    fetch_missing: bool = False,
) -> pd.DataFrame:
    catalog = pd.read_csv(catalog_path)
    missing_columns = REQUIRED_SOURCE_COLUMNS.difference(catalog.columns)
    if missing_columns:
        raise ValueError(f"CAT source catalog is missing: {sorted(missing_columns)}")
    catalog["fiscal_year"] = pd.to_numeric(
        catalog["fiscal_year"], errors="raise"
    ).astype(int)
    catalog["filing_date"] = pd.to_datetime(catalog["filing_date"], errors="raise")
    catalog = catalog.loc[catalog["filing_date"].le(pd.Timestamp(cutoff))].copy()
    catalog["resolved_path"] = catalog["local_path"].map(
        lambda relative: str((root / str(relative)).resolve())
    )
    if fetch_missing:
        for row in catalog.to_dict("records"):
            path = Path(row["resolved_path"])
            if path.is_file():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            request = Request(
                str(row["source_url"]),
                headers={"User-Agent": "ForecastTest/1.0 research@example.com"},
            )
            with urlopen(request, timeout=60) as response:  # noqa: S310 - SEC only
                path.write_bytes(response.read())
    missing_files = [
        row["local_path"]
        for row in catalog.to_dict("records")
        if not Path(row["resolved_path"]).is_file()
    ]
    if missing_files:
        raise FileNotFoundError(f"Missing CAT 10-K sources: {missing_files}")
    catalog["source_sha256"] = catalog["resolved_path"].map(
        lambda value: sha256_file(Path(value))
    )
    catalog["source_authority"] = "SEC_EDGAR_10_K"
    catalog["point_in_time_eligible"] = True
    return catalog.sort_values("fiscal_year").reset_index(drop=True)

