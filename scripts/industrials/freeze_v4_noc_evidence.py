from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.noc.benchmark import (
    freeze_noc_v4_evidence,
)


if __name__ == "__main__":
    print(json.dumps(freeze_noc_v4_evidence(PROJECT_ROOT), indent=2, default=str))
