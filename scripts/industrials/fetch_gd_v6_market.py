from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import pandas as pd
import requests
import yfinance as yf

from equity_platform.paths import PROJECT_ROOT


OUTPUT = PROJECT_ROOT / "data-lake/bronze/industrials/v6/market/gd"
START = "2021-08-01"
END_EXCLUSIVE = "2026-09-05"
TICKERS = ["GD", "SPY", "LMT", "NOC", "RTX"]


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    downloaded = yf.download(
        TICKERS,
        start=START,
        end=END_EXCLUSIVE,
        auto_adjust=True,
        progress=False,
    )["Close"]
    downloaded = downloaded.sort_index().dropna(how="all")
    downloaded.rename_axis("Date").reset_index().to_csv(
        OUTPUT / "adjusted_close_daily.csv", index=False
    )
    weekly = downloaded.resample("W-FRI").last().dropna(how="all")
    weekly.rename_axis("Date").reset_index().to_csv(
        OUTPUT / "adjusted_close_weekly.csv", index=False
    )

    risk_free_fallback = Path(
        "D:/Programming/python_example/Arcana/data-lake/bronze/fred/rates/us_dgs10.csv"
    )
    risk_free_retrieval = "FRED_DIRECT"
    try:
        response = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
            timeout=15,
            headers={"User-Agent": "Arcana-ForecastTest research contact local"},
        )
        response.raise_for_status()
        (OUTPUT / "fred_dgs10.csv").write_bytes(response.content)
    except requests.RequestException:
        shutil.copyfile(risk_free_fallback, OUTPUT / "fred_dgs10.csv")
        risk_free_retrieval = "ARCANA_BRONZE_FRED_FALLBACK"
    metadata = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "market_provider": "Yahoo Finance through yfinance",
        "market_provider_role": "PRICE_HISTORY_RESEARCH_INPUT",
        "risk_free_source": "Federal Reserve Bank of St. Louis FRED DGS10",
        "risk_free_source_url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
        "risk_free_retrieval": risk_free_retrieval,
        "tickers": TICKERS,
        "start": START,
        "end_exclusive": END_EXCLUSIVE,
        "maximum_market_date": downloaded.index.max().date().isoformat(),
        "rows_daily": len(downloaded),
        "rows_weekly": len(weekly),
    }
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
