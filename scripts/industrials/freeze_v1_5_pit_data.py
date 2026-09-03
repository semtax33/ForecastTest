from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v15.benchmark import freeze_v15_pit_data


if __name__ == "__main__":
    print(json.dumps(freeze_v15_pit_data(PROJECT_ROOT), indent=2, ensure_ascii=False))
