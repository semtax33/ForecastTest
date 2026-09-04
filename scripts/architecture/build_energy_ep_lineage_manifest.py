from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT


SOURCE = PROJECT_ROOT / "output/v3_5_1_audit_only/companyfacts_quarterly_revenue.csv"
UNIVERSE = PROJECT_ROOT / "output/energy_valuation_v1_1/adjusted_market_inputs.csv"
DESTINATION = PROJECT_ROOT / "data-lake/gold/certification/energy_ep_source_manifest.csv"


def build_manifest() -> pd.DataFrame:
    source = pd.read_csv(SOURCE)
    universe = pd.read_csv(UNIVERSE)
    expected = set(universe.loc[universe["subindustry"].eq("ep"), "ticker"])
    rows: list[dict[str, object]] = []
    for ticker in sorted(expected):
        paths = sorted(
            {
                Path(str(value))
                for value in source.loc[source["ticker"].eq(ticker), "source_path"].dropna()
            }
        )
        if len(paths) != 1 or not paths[0].is_file():
            raise ValueError(f"{ticker}: expected one existing CompanyFacts source, got {paths}")
        path = paths[0]
        observations = int(source.loc[source["ticker"].eq(ticker)].shape[0])
        rows.append(
            {
                "ticker": ticker,
                "source_kind": "SEC_COMPANYFACTS",
                "source_path": str(path),
                "source_sha256": sha256_file(path),
                "available_at": datetime.fromtimestamp(
                    path.stat().st_mtime, timezone.utc
                ).isoformat(),
                "evidence_table": SOURCE.relative_to(PROJECT_ROOT).as_posix(),
                "audited_quarterly_observations": observations,
                "manifest_policy": "EXPLICIT_PATH_AND_CONTENT_HASH_FAIL_CLOSED",
            }
        )
    result = pd.DataFrame(rows)
    if set(result["ticker"]) != expected or len(result) != 14:
        raise ValueError("E&P lineage manifest must cover all 14 registered issuers")
    return result


def main() -> int:
    manifest = build_manifest()
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(DESTINATION, index=False)
    print(manifest[["ticker", "source_kind", "audited_quarterly_observations"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
