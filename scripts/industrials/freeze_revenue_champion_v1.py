from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v16.benchmark import freeze_revenue_champion_v1


if __name__ == "__main__":
    print(json.dumps(freeze_revenue_champion_v1(PROJECT_ROOT), ensure_ascii=False, indent=2))
