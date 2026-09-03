from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v12.benchmark import freeze_v12_architecture


if __name__ == "__main__":
    print(json.dumps(freeze_v12_architecture(PROJECT_ROOT), indent=2, ensure_ascii=False))
