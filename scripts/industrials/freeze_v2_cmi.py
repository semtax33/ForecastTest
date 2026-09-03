from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v2.benchmark import freeze_cmi_v2


if __name__ == "__main__":
    print(json.dumps(freeze_cmi_v2(PROJECT_ROOT), indent=2, default=str))
