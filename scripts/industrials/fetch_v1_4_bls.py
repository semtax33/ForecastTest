from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import urllib.request

import pandas as pd

from equity_platform.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT
SENSORS = ROOT / "configs/industrials_v1_4_segment_sensors.csv"
OUTPUT = ROOT / "data-lake/bronze/industrials/v1_4/bls"
API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def main() -> int:
    sensors = pd.read_csv(SENSORS)
    series_ids = list(dict.fromkeys(sensors["series_id"].tolist()))
    body = json.dumps({"seriesid": series_ids, "startyear": "2020", "endyear": "2026"}).encode("utf-8")
    request = urllib.request.Request(API_URL, data=body, headers={"Content-Type": "application/json", "User-Agent": "Arcana-ForecastTest/1.0"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS request failed: {result.get('message')}")
    returned = {item["seriesID"] for item in result["Results"]["series"]}
    missing = sorted(set(series_ids) - returned)
    empty = sorted(item["seriesID"] for item in result["Results"]["series"] if not item.get("data"))
    if missing or empty:
        raise ValueError(f"BLS series incomplete; missing={missing}, empty={empty}")
    retrieved_at = datetime.now(timezone.utc)
    payload = {
        "schema_version": 1,
        "dataset": "industrials_v1_4_segment_cost_drivers",
        "provider": "BLS_PUBLIC_API_V2",
        "source_url": API_URL,
        "retrieved_at": retrieved_at.isoformat(),
        "series_ids": series_ids,
        "response": result,
        "vintage_status": "LATEST_REVISED_SNAPSHOT_NO_HISTORICAL_RELEASE_DATE",
        "historical_pit_eligible": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stamp = retrieved_at.strftime("%Y%m%dT%H%M%S%fZ")
    versioned = OUTPUT / f"segment_cost_drivers_{stamp}.json"
    versioned.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest = OUTPUT / "latest_segment_cost_drivers.json"
    shutil.copyfile(versioned, latest)
    print(json.dumps({"series_count": len(series_ids), "versioned_path": str(versioned), "latest_path": str(latest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
