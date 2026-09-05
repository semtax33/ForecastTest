from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v276_nineteenth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v276_nineteenth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the first V2.7.6 prediction on this
# issuer- and document-disjoint holdout. Tables/reconciliation grids are routed
# away from text IE. Dividends, repurchases and free cash flow are not CASH
# balances. Unsupported ratios and inequality-only values remain fail-closed.
EXPECTED = {
    # ADM.
    "97bf9eb935406b088800": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 172_000_000.0, change=51.0),
    ],
    "c506c634715ef1e65620": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 3.0, polarity="NEGATIVE"),
    ],
    "a9b35bc05ffb8c8b5ca8": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 1_500_000_000.0, change=75.0),
    ],
    "bd703da2addd2b5e3193": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 2_200_000_000.0, change=40.0),
    ],
    # Arthur J. Gallagher: consolidated and organic revenue growth are distinct.
    "58efa4ad93417724f748": [
        _frame("REVENUE", "CHANGE_BY", 24.0),
        _frame("REVENUE", "CHANGE_BY", 6.0),
    ],
    # American Tower: five segment guidance ranges and their midpoint growths.
    "e958b98552ac5f0cddae": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            5_090_000_000.0,
            lower_value=5_060_000_000.0,
            upper_value=5_120_000_000.0,
        ),
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            1_800_000_000.0,
            lower_value=1_790_000_000.0,
            upper_value=1_810_000_000.0,
        ),
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            1_630_000_000.0,
            lower_value=1_620_000_000.0,
            upper_value=1_640_000_000.0,
        ),
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            1_040_000_000.0,
            lower_value=1_025_000_000.0,
            upper_value=1_055_000_000.0,
        ),
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            1_210_000_000.0,
            lower_value=1_200_000_000.0,
            upper_value=1_220_000_000.0,
        ),
        _frame("REVENUE_GUIDANCE", "CHANGE_BY", 3.0, polarity="NEGATIVE"),
        _frame("REVENUE_GUIDANCE", "CHANGE_BY", 9.6),
        _frame("REVENUE_GUIDANCE", "CHANGE_BY", 14.6),
        _frame("REVENUE_GUIDANCE", "CHANGE_BY", 10.9),
        _frame("REVENUE_GUIDANCE", "CHANGE_BY", 14.9),
    ],
    # Abercrombie & Fitch.
    "da2a6d06ea7a1a934ec4": [
        _frame("REVENUE", "CHANGE_BY", 8.0),
        _frame("REVENUE", "CHANGE_BY", 2.0),
    ],
    "53eaf9e166960c0be53b": [
        _frame("REVENUE_GUIDANCE", "CHANGE_BY", 5.0),
    ],
    "321f4e0428c44503f85b": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 253_000_000.0),
    ],
    # Autodesk.
    "c04ee7d7e8f677207dc7": [
        _frame("REVENUE", "CHANGE_TO", 2_050_000_000.0, change=16.0),
        _frame("REVENUE", "CHANGE_BY", 14.0),
    ],
    # Assurant.
    "02d60c16210aede9e427": [
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 479_200_000.0, change=24.0),
    ],
    "7f7d49b692385b6b5a2f": [
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 491_400_000.0, change=18.0),
    ],
    # American Eagle Outfitters.
    "1a060e8414da82b45dbf": [
        _frame(
            "OPERATING_INCOME_GUIDANCE",
            "RANGE_GUIDANCE",
            400_000_000.0,
            lower_value=390_000_000.0,
            upper_value=410_000_000.0,
        ),
    ],
    "0aafdc1a63a316ac08f2": [
        _frame("GROSS_MARGIN", "CHANGE_TO", 38.2, change=860.0),
    ],
    "14739041dd27d0c6e389": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 61_000_000.0),
    ],
    "9408e8328ecd90c9f844": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 2.4),
    ],
    "6d0b90b56b5b9b39cee3": [
        _frame("REVENUE", "CHANGE_BY", 25.0),
    ],
    # Allegion.
    "74dc89e80bdd16f58874": [
        _frame("REVENUE", "CHANGE_BY", 16.2),
        _frame("REVENUE", "CHANGE_BY", 1.2, polarity="NEGATIVE"),
    ],
    "a7788e48431df4a28647": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 254_700_000.0, change=35_000_000.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 15.9),
    ],
    "afc230d53c6441387f3c": [
        _frame("REVENUE", "CHANGE_BY", 14.3),
        _frame("REVENUE", "CHANGE_BY", 3.1),
    ],
    "c24b26337d2afdbedb51": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 24.2),
    ],
    "5fca929cd4daab870c8b": [
        _frame("REVENUE", "CHANGE_TO", 1_151_500_000.0, change=12.7),
        _frame("REVENUE", "CHANGE_BY", 6.9),
    ],
    "049efc91d2c02699eda6": [
        _frame("REVENUE", "CHANGE_BY", 5.1),
        _frame("REVENUE", "CHANGE_BY", 0.7),
    ],
}


TABLE_IDS = {
    # Arch Capital.
    "dfb99616cd157db5538d",
    "164dc8378720be0e4889",
    "a8851a1fb99da3052e8e",
    # ADM and Ameren.
    "ea1319b240b66ad226ab",
    "41c5e42e3ace848c7d73",
    # Arthur J. Gallagher.
    "8f66c6cec0ed554f03d2",
    "05524b7698df20f93f59",
    # American Tower.
    "3f47b7e5d088ca652a1b",
    # Abercrombie & Fitch.
    "ab134b967675d6e2d8df",
    "33e7790696f702cdcc18",
    # Autodesk.
    "5d6e674858beaf85322b",
    "8a3e3e81749b4328745b",
    "d3e358daca599927f3dd",
    "68a72fa2ecc527c8aecf",
    # Assurant.
    "0dea0df0edba2c760b74",
    "d12a977b2027e115d595",
    "35ee4ad29eade5ff6dcd",
    "b453452e04971a3298a8",
    # American Eagle Outfitters.
    "d149aa870ddbbcf6ef8b",
    "00dec8e562ca74525f0e",
    # Allegion.
    "697dcbbd19051f0d2a1d",
}


NOTES = {
    "e958b98552ac5f0cddae": "segment guidance prose is text IE despite dense numeric content",
    "26e80872ec9d239bda4b": "over three percent is a lower bound, not an exact-value fact",
    "0cd8eee45f0640b3cea9": "liquidity combines cash and undrawn borrowing capacity",
    "b353be478fda7b0c3879": "share repurchases are not a cash-balance fact",
    "ba8ced36e39338aee513": "cash dividend is not a cash-balance fact",
    "b36d9815745ffb610944": "available cash flow is not a cash-balance fact",
    "0dea0df0edba2c760b74": "flattened constant-currency reconciliation table",
    "d12a977b2027e115d595": "prose lead-in is inseparable from a flattened segment table",
}


def main() -> int:
    candidates = pd.read_csv(CANDIDATES)
    rows = []
    for item in candidates.itertuples(index=False):
        expected = EXPECTED.get(item.candidate_id, [])
        route = (
            "TABLE_DSL"
            if item.candidate_id in TABLE_IDS
            else "TEXT_IE"
            if expected
            else "NO_FACT"
        )
        rows.append(
            {
                "candidate_id": item.candidate_id,
                "ticker": item.ticker,
                "gold_route": route,
                "expected_frames": expected,
                "annotation_note": NOTES.get(
                    item.candidate_id,
                    "exhaustive manual nineteenth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.6 nineteenth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown nineteenth-holdout candidate ids: {sorted(unknown)}")
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
