from __future__ import annotations

import argparse
from pathlib import Path
from energy_nowcast.research.v35.adapters import _table_rows


MARKERS = (
    "production", "sales volume", "equivalent", "mmcfe", "bcfe", "mboe",
    "oil (", "natural gas (", "ngl (", "liquids (",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ir-root", type=Path, required=True)
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--files", type=int, default=24)
    parser.add_argument("--relaxed", action="store_true")
    args = parser.parse_args()
    for ticker in args.tickers:
        print(f"\n===== {ticker} =====")
        shown = 0
        for path in sorted((args.ir_root / ticker).glob("*.htm"), reverse=True)[: args.files]:
            selected = []
            for table in _table_rows(path):
                text = " ".join(" ".join(row) for row in table).lower()
                if not args.relaxed and "three months ended" not in text and "selected operating" not in text:
                    continue
                rows = [row for row in table if any(marker in " ".join(row).lower() for marker in MARKERS)]
                if rows:
                    selected.extend(rows)
            if selected:
                print(f"--- {path.name}")
                for row in selected[:30]:
                    print(" | ".join(row[:8]))
                shown += 1
            if shown >= 2:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
