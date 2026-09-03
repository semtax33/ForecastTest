from __future__ import annotations

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.gd_v6.benchmark import (
    freeze_gd_v6_research,
)


if __name__ == "__main__":
    result = freeze_gd_v6_research(PROJECT_ROOT)
    print(result)
