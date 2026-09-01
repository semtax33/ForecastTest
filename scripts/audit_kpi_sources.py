from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path
import sys

import pandas as pd


DEFAULT_TICKERS = ("EOG", "COP", "FANG", "DVN", "EQT", "AR", "RRC", "MTDR", "PR", "CNX", "SM", "MGY", "NOG")
KEYWORDS = (
    "production", "realized price", "realized prices", "oil price",
    "natural gas price", "ngl price", "barrels per day", "mboe", "mmcfe",
)


def candidate_tables(path: Path) -> list[tuple[int, pd.DataFrame]]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tables = pd.read_html(StringIO(html))
    except (ValueError, ImportError):
        return []
    selected: list[tuple[int, pd.DataFrame]] = []
    for index, table in enumerate(tables):
        text = " ".join(table.astype(str).fillna("").to_numpy().ravel()).lower()
        hits = sum(keyword in text for keyword in KEYWORDS)
        if hits >= 2:
            selected.append((index, table))
    return selected


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--ir-root", type=Path, required=True)
    parser.add_argument("--files-per-ticker", type=int, default=8)
    parser.add_argument("--tickers", nargs="*", default=DEFAULT_TICKERS)
    args = parser.parse_args()
    for ticker in args.tickers:
        directory = args.ir_root / ticker
        files = sorted(directory.glob("*.htm"), reverse=True)[: args.files_per_ticker]
        print(f"\n===== {ticker}: {len(files)} recent files =====")
        shown = 0
        for path in files:
            selected = candidate_tables(path)
            if not selected:
                continue
            print(f"\n--- {path.name} ({len(selected)} candidate tables) ---")
            for index, table in selected[:3]:
                print(f"TABLE {index} shape={table.shape}")
                print(table.head(18).to_string(index=False, header=False, max_cols=12))
            shown += 1
            if shown >= 2:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
