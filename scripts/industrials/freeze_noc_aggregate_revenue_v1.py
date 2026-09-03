from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.aerospace_defense.aggregate_revenue_v1 import (
    freeze_noc_aggregate_revenue_v1,
)


if __name__ == "__main__":
    print(json.dumps(freeze_noc_aggregate_revenue_v1(PROJECT_ROOT), indent=2, default=str))
