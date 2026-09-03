from __future__ import annotations


E_AND_P_GROUPS = {
    "oil_heavy": ("EOG", "FANG", "PR", "MTDR", "MGY", "NOG"),
    "gas_heavy": ("EQT", "AR", "RRC", "CNX"),
    "mixed": ("COP", "DVN", "OVV", "SM"),
}

GROUP_PRICE_WEIGHTS = {
    "oil_heavy": {"oil": 0.68, "ngl": 0.17, "gas": 0.15},
    "gas_heavy": {"oil": 0.08, "ngl": 0.17, "gas": 0.75},
    "mixed": {"oil": 0.45, "ngl": 0.15, "gas": 0.40},
}


def group_for_ticker(ticker: str) -> str:
    for group, tickers in E_AND_P_GROUPS.items():
        if ticker in tickers:
            return group
    raise KeyError(f"Ticker is not in the fixed V3.5 taxonomy: {ticker}")


def all_tickers() -> tuple[str, ...]:
    return tuple(ticker for tickers in E_AND_P_GROUPS.values() for ticker in tickers)


