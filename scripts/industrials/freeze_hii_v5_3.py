from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.hii_v53 import (
    freeze_hii_v53_margin_research,
)


def main() -> int:
    frozen = freeze_hii_v53_margin_research(PROJECT_ROOT)
    print(frozen["manifest_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
