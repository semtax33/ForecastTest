from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from equity_platform.sectors.energy.research.revenue.v35.adapters import (
    PRICE_COLUMNS,
    _metadata,
    _numbers,
    _release_date,
    _source_url,
    _table_rows,
)
from equity_platform.sectors.energy.research.revenue.v35.taxonomy import E_AND_P_GROUPS


GAS_TICKERS = E_AND_P_GROUPS["gas_heavy"]
STRICT_GAS_PRICE_COLUMNS = [
    "ticker",
    "quarter",
    "realized_gas_price",
    "hedge_included",
    "price_semantics",
    "source_label",
    "filing_date",
    "source_url",
    "source_path",
    "quality_score",
]


def classify_gas_price_label(label: str) -> str | None:
    """Accept absolute company gas prices and reject TOC/differential rows."""
    lower = " ".join(label.lower().split())
    if "price" not in lower:
        return None
    gas_identified = "gas" in lower or (
        "realized" in lower and any(unit in lower for unit in ("mcf", "mcfe"))
    )
    if not gas_identified:
        return None
    if not any(unit in lower for unit in ("mcf", "mmbtu", "mcfe")):
        return None
    if label.count(".") >= 12:
        return None
    rejected = (
        "differential",
        "premium",
        "reconciliation",
        "benchmark",
        "nymex",
        "floor price",
        "cap price",
        "collar",
        "swap price",
        "% of",
        "percent of",
        "guidance",
        "forecast",
    )
    if any(marker in lower for marker in rejected):
        return None
    if "including cash settled" in lower or "after effects of hedge" in lower:
        return "HEDGE_ADJUSTED_REALIZED"
    if "before financial hedging" in lower or "before effects of hedge" in lower:
        return "PRE_HEDGE_REALIZED"
    if "realized" in lower or "average sales price" in lower:
        return "PRE_HEDGE_REALIZED"
    if lower.startswith(("natural gas price", "appalachian natural gas price")):
        return "ABSOLUTE_COMPANY_GAS_PRICE"
    return None


def _semantics_priority(semantics: str, preference: str) -> int:
    if preference == "hedge_adjusted":
        order = {
            "HEDGE_ADJUSTED_REALIZED": 3,
            "PRE_HEDGE_REALIZED": 2,
            "ABSOLUTE_COMPANY_GAS_PRICE": 1,
        }
    else:
        order = {
            "PRE_HEDGE_REALIZED": 3,
            "ABSOLUTE_COMPANY_GAS_PRICE": 2,
            "HEDGE_ADJUSTED_REALIZED": 1,
        }
    return order[semantics]


def extract_strict_gas_prices(
    ir_root: Path,
    preference: str = "pre_hedge",
) -> pd.DataFrame:
    if preference not in {"pre_hedge", "hedge_adjusted"}:
        raise ValueError(f"Unknown gas-price preference: {preference}")
    rows: list[dict[str, object]] = []
    for ticker in GAS_TICKERS:
        company_root = ir_root / ticker
        if not company_root.exists():
            continue
        for path in company_root.glob("*.htm*"):
            if path.name.endswith(".json"):
                continue
            metadata = _metadata(path)
            filing_date = _release_date(path, metadata)
            quarter = str(filing_date.to_period("Q") - 1)
            candidates: list[tuple[int, str, str, float]] = []
            for table in _table_rows(path):
                for table_row in table:
                    if not table_row:
                        continue
                    label = str(table_row[0])
                    semantics = classify_gas_price_label(label)
                    values = _numbers(table_row[1:])
                    if semantics is None or not values:
                        continue
                    value = float(values[0])
                    if not 0.10 <= value <= 30.0:
                        continue
                    candidates.append(
                        (_semantics_priority(semantics, preference), semantics, label, value)
                    )
            if not candidates:
                continue
            priority, semantics, label, value = max(candidates, key=lambda item: item[0])
            rows.append({
                "ticker": ticker,
                "quarter": quarter,
                "realized_gas_price": value,
                "hedge_included": semantics == "HEDGE_ADJUSTED_REALIZED",
                "price_semantics": semantics,
                "source_label": label,
                "filing_date": filing_date,
                "source_url": _source_url(path, metadata),
                "source_path": str(path),
                "quality_score": 0.92 if priority == 3 else 0.84,
            })
    result = pd.DataFrame(rows, columns=STRICT_GAS_PRICE_COLUMNS)
    if result.empty:
        return result
    return (
        result.sort_values(["ticker", "quarter", "quality_score", "filing_date"])
        .drop_duplicates(["ticker", "quarter"], keep="last")
        .reset_index(drop=True)
    )


def merge_strict_gas_prices(
    realized_prices: pd.DataFrame,
    strict_gas_prices: pd.DataFrame,
) -> pd.DataFrame:
    """Replace only gas-heavy gas prices; preserve all other realized components."""
    merged = realized_prices.copy()
    gas_mask = merged["ticker"].isin(GAS_TICKERS)
    merged.loc[gas_mask, "realized_gas_price"] = np.nan
    for _, strict in strict_gas_prices.iterrows():
        mask = (
            merged["ticker"].eq(strict["ticker"])
            & merged["quarter"].astype(str).eq(str(strict["quarter"]))
        )
        if mask.any():
            index = merged.index[mask][-1]
        else:
            index = len(merged)
            merged.loc[index, :] = np.nan
            merged.loc[index, "ticker"] = strict["ticker"]
            merged.loc[index, "quarter"] = strict["quarter"]
        for column in (
            "realized_gas_price",
            "hedge_included",
            "filing_date",
            "source_url",
            "source_path",
            "quality_score",
        ):
            merged.loc[index, column] = strict[column]
        merged.loc[index, "adapter"] = "STRICT_GAS_REALIZED_V353"
    merged = merged.dropna(
        subset=["realized_oil_price", "realized_ngl_price", "realized_gas_price"],
        how="all",
    )
    return merged.loc[:, PRICE_COLUMNS].sort_values(
        ["ticker", "quarter", "filing_date"]
    ).reset_index(drop=True)
