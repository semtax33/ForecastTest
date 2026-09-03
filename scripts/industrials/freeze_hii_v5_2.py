from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii_v52 import (
    freeze_ad_aggregate_replication_v1,
    freeze_hii_v51_governance,
    freeze_hii_v52_valuation,
)


def main() -> int:
    governance = freeze_hii_v51_governance(PROJECT_ROOT)
    replication = freeze_ad_aggregate_replication_v1(PROJECT_ROOT)
    valuation = freeze_hii_v52_valuation(PROJECT_ROOT)
    print(governance["manifest_sha256"])
    print(replication["manifest_sha256"])
    print(valuation["manifest_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
