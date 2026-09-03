from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.lmt_v31.benchmark import (
    freeze_lmt_v31_evidence,
)


if __name__ == "__main__":
    print(json.dumps(freeze_lmt_v31_evidence(PROJECT_ROOT), indent=2, default=str))
