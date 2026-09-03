from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil

import requests
import yfinance as yf

from equity_platform.paths import PROJECT_ROOT
from equity_platform.sectors.industrials.platform.registry import (
    INDUSTRIALS_SUBINDUSTRIES,
)


OUTPUT = PROJECT_ROOT / "data-lake/bronze/industrials/v8/subindustries/market"
START = "2021-01-01"
END_EXCLUSIVE = "2026-09-05"
TICKERS = sorted(
    {
        profile.representative_ticker
        for profile in INDUSTRIALS_SUBINDUSTRIES
        if profile.sec_form_regime == "10-K_10-Q"
    }
    | {"SPY"}
)


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    downloaded = yf.download(
        TICKERS,
        start=START,
        end=END_EXCLUSIVE,
        auto_adjust=True,
        progress=False,
        threads=True,
    )["Close"].sort_index()
    daily_path = OUTPUT / "adjusted_close_daily.csv"
    weekly_path = OUTPUT / "adjusted_close_weekly.csv"
    downloaded.rename_axis("Date").reset_index().to_csv(daily_path, index=False)
    downloaded.resample("W-FRI").last().rename_axis("Date").reset_index().to_csv(
        weekly_path, index=False
    )
    risk_free_path = OUTPUT / "fred_dgs10.csv"
    fallback = Path(
        "D:/Programming/python_example/Arcana/data-lake/bronze/fred/rates/us_dgs10.csv"
    )
    retrieval = "FRED_DIRECT"
    try:
        response = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
            timeout=20,
            headers={"User-Agent": "Arcana ForecastTest research contact local"},
        )
        response.raise_for_status()
        risk_free_path.write_bytes(response.content)
    except requests.RequestException:
        shutil.copyfile(fallback, risk_free_path)
        retrieval = "ARCANA_BRONZE_FRED_FALLBACK"
    metadata = {
        "schema_version": 1,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "valuation_date": "2026-09-04",
        "market_provider": "Yahoo Finance through yfinance",
        "risk_free_provider": "Federal Reserve Bank of St. Louis FRED DGS10",
        "risk_free_retrieval": retrieval,
        "tickers": TICKERS,
        "start": START,
        "end_exclusive": END_EXCLUSIVE,
        "maximum_market_date": downloaded.index.max().date().isoformat(),
        "daily_rows": len(downloaded),
        "daily_sha256": _sha(daily_path),
        "weekly_sha256": _sha(weekly_path),
        "risk_free_sha256": _sha(risk_free_path),
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
