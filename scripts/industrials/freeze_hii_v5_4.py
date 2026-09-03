from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii_v54 import (
    freeze_hii_v54_margin_mechanism_research,
)


def main() -> int:
    frozen = freeze_hii_v54_margin_mechanism_research(PROJECT_ROOT)
    print(frozen["manifest_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
