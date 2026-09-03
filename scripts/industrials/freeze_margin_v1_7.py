from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.v17.benchmark import freeze_margin_v1_7


def main() -> int:
    manifest = freeze_margin_v1_7(PROJECT_ROOT)
    print(json.dumps({"manifest_path": manifest["manifest_path"], "manifest_sha256": manifest["manifest_sha256"], "verified_files": manifest["verified_files"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
