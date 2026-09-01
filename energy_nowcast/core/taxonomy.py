from __future__ import annotations


SUBINDUSTRY_TICKERS = {
    "integrated": ("XOM", "CVX"),
    "refining": ("VLO", "MPC", "PSX"),
    "midstream": ("KMI", "WMB", "ET", "EPD"),
    "services": ("SLB", "HAL", "BKR"),
}


def subindustry_for_ticker(ticker: str) -> str:
    for subindustry, tickers in SUBINDUSTRY_TICKERS.items():
        if ticker in tickers:
            return subindustry
    raise KeyError(f"Ticker is not registered in the Phase 2-4 taxonomy: {ticker}")


def phase_for_subindustry(subindustry: str) -> int:
    return {"integrated": 2, "refining": 2, "midstream": 3, "services": 4}[
        subindustry
    ]


def all_phase_tickers() -> tuple[str, ...]:
    return tuple(
        ticker for tickers in SUBINDUSTRY_TICKERS.values() for ticker in tickers
    )
