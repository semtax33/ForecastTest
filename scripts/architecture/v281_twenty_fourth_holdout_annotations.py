from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v281_twenty_fourth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v281_twenty_fourth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


# Exhaustive issuer-disjoint labels prepared from candidate text without
# executing or inspecting V2.8.1 predictions. Economic meaning controls the
# label: combined operating cash flow is not CASH, client flows are activity,
# adjusted EBIT margin is an operating margin, and flattened grids are table-only.
EXPECTED = {
    # American Homes 4 Rent.
    "220de839f690a7f09207": [
        _frame("REVENUE", "CHANGE_TO", 470_100_000.0, change=2.8),
    ],
    "31a537f6f0f17fd19bfd": [
        _frame("REVENUE", "CHANGE_TO", 735_800_000.0, change=2.4),
        _frame("PRICE_REALIZATION", "CHANGE_BY", 2.8),
    ],
    "a4cc887fb4cbd28ed3d5": [
        _frame("REVENUE", "CHANGE_BY", 2.7),
    ],
    # Autoliv.
    "b7c6a7efe072aa971a6d": [
        _frame("REVENUE", "CHANGE_BY", 44.0),
        _frame("REVENUE", "CHANGE_BY", 24.0, polarity="NEGATIVE"),
    ],
    "2d4744660b0d3709cb2b": [
        _frame("REVENUE", "CHANGE_BY", 1.0, polarity="NEGATIVE"),
    ],
    "ab5d3d2af26033ecb687": [
        _frame(
            "OPERATING_MARGIN_GUIDANCE",
            "RANGE_GUIDANCE",
            10.75,
            lower_value=10.5,
            upper_value=11.0,
        ),
    ],
    "9720651100fe93fc0be5": [
        _frame("GROSS_MARGIN", "CHANGE_BY", 30.0, polarity="NEGATIVE"),
    ],
    "e71633dc51ca3a689726": [
        _frame("OPERATING_MARGIN", "CHANGE_BY", 35.0, polarity="NEGATIVE"),
    ],
    "0110dcd3b38ad74c3c85": [
        _frame("REVENUE", "CHANGE_BY", 36.0),
    ],
    # Akamai.
    "7089ba08b97db939e655": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 7.0, change=800.0, polarity="NEGATIVE"),
    ],
    # Amcor.
    "60a0382fcd644afc8b5e": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 11.0, change=220.0),
    ],
    "cd391575919ff24d5883": [
        _frame("EBIT", "CHANGE_TO", 2_813_000_000.0, change=63.0),
        _frame("EBIT", "CHANGE_TO", 842_000_000.0, change=49.0),
    ],
    "47c30f21455b7a62b25a": [
        _frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 1_045_000_000.0),
    ],
    "e4e12670d3b4b180752f": [
        _frame("REVENUE", "CHANGE_BY", 240_000_000.0),
        _frame("REVENUE", "CHANGE_BY", 2.0),
    ],
    "a0dd9c430e031fc91b1c": [
        _frame("EBIT", "CHANGE_TO", 1_176_000_000.0, change=161.0),
        _frame("EBIT", "CHANGE_TO", 635_000_000.0, change=146.0),
    ],
    # AECOM.
    "7255a438a160076f067e": [
        _frame("REVENUE", "CHANGE_TO", 800_000_000.0, change=4.0),
    ],
    "1aed97d0b36f14c4a5f5": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 16_100_000_000.0),
    ],
    "666454460fdbaa546ba5": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 14.3, change=240.0),
    ],
    "f3f51561632b4af51e6a": [
        _frame("REVENUE", "CHANGE_TO", 2_600_000_000.0, change=20.0, polarity="NEGATIVE"),
    ],
    "e4c95ec8d3c68e9ed972": [
        _frame("REVENUE", "CHANGE_TO", 953_000_000.0, change=6.0),
    ],
    # AMC Networks.
    "69401dcf8ee63ace3849": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            212_500_000.0,
            lower_value=200_000_000.0,
            upper_value=225_000_000.0,
        ),
    ],
    # Affiliated Managers Group.
    "b95e9703b66939e1ffba": [
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 13_000_000_000.0),
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 35_000_000_000.0),
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 29_000_000_000.0),
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 58_000_000_000.0),
    ],
    "6645d0b8cf79eda371c1": [
        _frame("ADJUSTED_EBITDA", "CHANGE_BY", 44.0),
    ],
    # Alnylam.
    "d967f0c729e5824d3cc1": [
        _frame("SHARES", "COMPARATIVE", 138_281_000.0),
        _frame("PRIOR_YEAR_SHARES", "COMPARATIVE", 137_089_000.0),
    ],
    "ba9e7dbb6ae94fbb28dc": [
        _frame("CASH", "COMPARATIVE", 3_300_000_000.0),
        _frame("PRIOR_YEAR_CASH", "COMPARATIVE", 2_900_000_000.0),
    ],
    "041e26f15cfa508e9a92": [
        _frame("REVENUE", "CHANGE_BY", 106_000_000.0),
    ],
    "1cb3ad34ac944063be2f": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 90_000_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 52_000_000.0),
        _frame("REVENUE", "CHANGE_TO", 142_000_000.0, change=11.0),
    ],
    "c916846499eb53bf0c88": [
        _frame("REVENUE", "CHANGE_BY", 14_000_000.0),
    ],
    # Antero Midstream.
    "9f4bdca42c5b0606c80e": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 45_000_000.0),
    ],
    "2f161d8ccfac7107517e": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 327_000_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 272_000_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 79_000_000.0),
    ],
    "6853a9d0880bf043a334": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 47_000_000.0),
    ],
    "1355291270bbb3555abe": [
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 19.0),
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 17.0),
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 289_000_000.0, change=2.0),
        _frame("CAPEX", "ABSOLUTE_VALUE", 47_000_000.0),
        _frame("PRODUCTION", "CHANGE_TO", 4.1, change=19.0),
    ],
}


TABLE_IDS = {
    "9a68875c0004e98ae5e0",
    "1af4944ef06a19c3632d",
    "090768094551ce182fa3",
    "6ab58e7f73ad2719e8ac",
    "38b2114748248ae72ed1",
    "056cf8bd32a96299467f",
    "266b63547842e20ef855",
    "2cae0f5f8eec2163b6ac",
    "fdc55b3758d3955a49e4",
    "f952eddf1c8073e36d3e",
    "d3ea4cccb3b78b507f64",
    "8c7819a206b726915d25",
    "a0025a3b942f7e29d8d2",
    "37552ed974933341f43d",
    "f63df60e8cc45f3737fc",
    "251914961b70e0a9c9bb",
    "604cc3f5974f83d0098e",
    "ce30385c778a0a82609c",
    "1f2a67368f89e8a1e6f9",
    "8e01b2d4ce8f1267cf60",
    "6bd4a051d69fa6b089ff",
}


NOTES = {
    "9a68875c0004e98ae5e0": "development pipeline is a flattened multi-column grid",
    "ab5d3d2af26033ecb687": "operating cash flow is not a cash-balance fact",
    "e4e12670d3b4b180752f": "raw-material pass-through is a revenue delta, not a revenue level",
    "b95e9703b66939e1ffba": "client cash flows and net inflows are activity, not cash balances",
    "ba9e7dbb6ae94fbb28dc": "cash plus marketable securities is an explicitly reported liquidity comparison",
    "1355291270bbb3555abe": "bullet highlights are semantic prose despite a table-like frozen route",
}


def main() -> int:
    candidates = pd.read_csv(CANDIDATES)
    rows = []
    for item in candidates.itertuples(index=False):
        expected = EXPECTED.get(item.candidate_id, [])
        route = "TABLE_DSL" if item.candidate_id in TABLE_IDS else "TEXT_IE" if expected else "NO_FACT"
        rows.append(
            {
                "candidate_id": item.candidate_id,
                "ticker": item.ticker,
                "gold_route": route,
                "expected_frames": expected,
                "annotation_note": NOTES.get(item.candidate_id, "exhaustive manual twenty-fourth annotation before prediction"),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.8.1 twenty-fourth holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twenty-fourth candidate ids: {sorted(unknown)}")
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(
        f"ANNOTATED={len(rows)} "
        f"EXPECTED_FRAMES={sum(len(row['expected_frames']) for row in rows)} "
        f"TABLE_BLOCKS={len(TABLE_IDS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
