from __future__ import annotations

import json
from energy_nowcast.research.ep_v19.benchmark import freeze_v19
from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT


if __name__ == "__main__":
    print(json.dumps(freeze_v19(ROOT), indent=2, ensure_ascii=False))
