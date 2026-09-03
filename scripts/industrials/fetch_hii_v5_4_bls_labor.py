from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib
from urllib.request import Request, urlopen

from equity_platform.paths import PROJECT_ROOT


CONFIG = PROJECT_ROOT / "configs/industrials_v5_4_hii_margin_mechanisms.toml"
BLS_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    target = PROJECT_ROOT / Path(config["bls_labor_snapshot"])
    if target.exists() and not args.force:
        print(target)
        return 0
    payload = {
        "seriesid": list(config["bls_series"]),
        "startyear": "2019",
        "endyear": "2026",
    }
    request = Request(
        BLS_API,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Arcana research"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS request failed: {result}")
    missing = [
        series["seriesID"]
        for series in result["Results"]["series"]
        if not series.get("data")
    ]
    if missing:
        raise RuntimeError(f"BLS series returned no data: {missing}")
    artifact = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "U.S. Bureau of Labor Statistics Public Data API v2",
        "source_url": BLS_API,
        "authority": "CURRENT_REVISED_MECHANISM_DIAGNOSTIC_NOT_PIT_MODEL_INPUT",
        "request": payload,
        "series_titles": config["bls_series"],
        "response": result,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
