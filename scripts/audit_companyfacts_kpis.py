from __future__ import annotations

import argparse
import json
from pathlib import Path


CIKS = {
    "AR": 1433270, "CNX": 1070412, "COP": 1163165, "DVN": 1090012,
    "EOG": 821189, "EQT": 33213, "FANG": 1539838, "MGY": 1698990,
    "MTDR": 1520006, "NOG": 1104485, "OVV": 1792580, "PR": 1658566,
    "RRC": 315852, "SM": 893538,
}
KEYWORDS = ("production", "realized", "oil", "naturalgas", "ngl", "barrel", "mcf")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*", default=sorted(CIKS))
    args = parser.parse_args()
    root = Path(r"D:\Programming\python_example\Arcana\data-lake\bronze\sec\companyfacts")
    for ticker in args.tickers:
        cik = CIKS[ticker]
        path = root / f"CIK{cik:010d}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        matches = []
        for namespace, concepts in payload.get("facts", {}).items():
            for name, fact in concepts.items():
                searchable = f"{name} {fact.get('label', '')} {fact.get('description', '')}".lower()
                if any(keyword in searchable for keyword in KEYWORDS):
                    units = ",".join(fact.get("units", {}).keys())
                    matches.append((namespace, name, fact.get("label", ""), units))
        print(f"\n===== {ticker}: {len(matches)} matches =====")
        for row in matches:
            print(" | ".join(str(value) for value in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
