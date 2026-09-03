from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v11_benchmark import freeze_v11


if __name__ == "__main__":
    print(json.dumps(freeze_v11(PROJECT_ROOT), indent=2, ensure_ascii=False))
