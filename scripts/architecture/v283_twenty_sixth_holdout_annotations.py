from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v283_twenty_sixth_holdout_candidates import CANDIDATES


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v283_twenty_sixth_holdout_annotations.jsonl"


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


# Exhaustive labels prepared before the first V2.8.3 prediction. Economic roles
# take precedence over surface words: cash flow is not CASH, insurance product
# sales are activity, revenue per advisor/day is realization, and flattened
# statement grids are routed to TABLE_DSL rather than retyped as prose facts.
EXPECTED = {
    # ProFrac.
    "e07b23d4d4d0b35b2409": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 121_000_000.0),
        _frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 6_000_000.0),
        _frame("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 5.0),
    ],
    "1d4ab46ca9eca7d3c66c": [
        _frame("REVENUE", "COMPARATIVE", 498_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 450_000_000.0),
        _frame("ADJUSTED_EBITDA", "COMPARATIVE", 69_000_000.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 54_000_000.0),
        _frame("ADJUSTED_EBITDA_MARGIN", "COMPARATIVE", 14.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA_MARGIN", "COMPARATIVE", 12.0),
        _frame("CAPEX", "COMPARATIVE", 32_000_000.0),
        _frame("PRIOR_YEAR_CAPEX", "COMPARATIVE", 41_000_000.0),
    ],
    "8175ee4fec876e9f1499": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 48_000_000.0),
        _frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 6_000_000.0),
        _frame("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 13.0),
    ],
    "befe290fa84868ae691f": [_frame("DEBT", "ABSOLUTE_VALUE", 173_000_000.0)],
    # Acadia Healthcare.
    "92f76494362d4d3fae1d": [_frame("REVENUE", "CHANGE_BY", 5.7)],
    "9d8b8a8eb6dab107b2de": [_frame("REVENUE", "ABSOLUTE_VALUE", 22_300_000.0)],
    "e771ce671518afff58cd": [
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 0.8),
        _frame("PRICE_REALIZATION", "CHANGE_BY", 0.8, polarity="NEGATIVE"),
    ],
    "9c36ed38fc3d74cf3710": [_frame("REVENUE", "CHANGE_BY", 2.8)],
    # Advanced Energy.
    "de2513aa75b31c2e6207": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            640_000_000.0,
            lower_value=620_000_000.0,
            upper_value=660_000_000.0,
        ),
    ],
    "580fd1d178934026016c": [
        _frame("REVENUE", "COMPARATIVE", 574_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 511_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 442_000_000.0),
    ],
    "72b885f237e821622f4b": [
        _frame("REVENUE", "CHANGE_TO", 574_000_000.0, change=30.0),
        _frame("REVENUE", "CHANGE_BY", 33.0),
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 41.1),
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 41.9),
    ],
    # AAR.
    "da931bbf40a0587fcb9b": [
        _frame("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 13.0),
        _frame("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 12.7),
    ],
    "51cdc9cf52e96efca0a9": [
        _frame("OPERATING_MARGIN", "COMPARATIVE", 8.4),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 6.7),
    ],
    "f261fd59408daf9a59ef": [_frame("ACTIVITY_VOLUME", "CHANGE_BY", 39.0)],
    "bd0c2ab8068a5034b88a": [_frame("ACTIVITY_VOLUME", "CHANGE_BY", 19.0)],
    "b94c8afff3f9ebf79268": [_frame("ORDERS", "ABSOLUTE_VALUE", 305_000_000.0)],
    "4511667c2e1364b1b134": [
        _frame("OPERATING_MARGIN", "COMPARATIVE", 10.2),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 9.6),
    ],
    # Aon.
    "baac0e1be8f4418beb7c": [
        _frame("SHARES", "COMPARATIVE", 213_900_000.0),
        _frame("PRIOR_YEAR_SHARES", "COMPARATIVE", 217_300_000.0),
    ],
    # APA.
    "f5505cdf911092d46f07": [_frame("DEBT", "CHANGE_BY", 2_300_000_000.0, polarity="NEGATIVE")],
    "23f5008df498d357eac1": [
        _frame("PRODUCTION", "ABSOLUTE_VALUE", 410_000.0),
        _frame("PRODUCTION", "ABSOLUTE_VALUE", 347_000.0),
    ],
    "a304a9f3d716f33b7c51": [_frame("DEBT", "ABSOLUTE_VALUE", 3_300_000_000.0)],
    "3fd8a49be7dada28fd93": [_frame("PRODUCTION", "CHANGE_TO", 539_000_000.0)],
    "f8ed27b817ec6a452385": [
        _frame("PRODUCTION", "ABSOLUTE_VALUE", 410_000.0),
        _frame("PRODUCTION", "ABSOLUTE_VALUE", 347_000.0),
    ],
    "114fa18b0da56d6fd9d9": [_frame("PRODUCTION_GUIDANCE", "ABSOLUTE_VALUE", 123_000.0)],
    # Ameriprise.
    "47a77f0eb32a31670a1a": [_frame("REVENUE", "CHANGE_TO", 4_900_000_000.0, change=13.0)],
    "c5cf956553fe9c7a85f9": [_frame("PRICE_REALIZATION", "CHANGE_TO", 1_200_000.0, change=12.0)],
    "982816d094156e361aa9": [_frame("ACTIVITY_VOLUME", "CHANGE_TO", 1_600_000_000.0, change=20.0)],
    "26dc53ec425a32629a8f": [_frame("OPERATING_MARGIN", "CHANGE_TO", 42.7, change=370.0)],
    # A. O. Smith.
    "39799a01e6f048461563": [
        _frame("REVENUE", "CHANGE_TO", 194_900_000.0, change=19.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 6_000_000.0),
    ],
    "0f3d6444ac29fd3f38e1": [
        _frame("REVENUE", "CHANGE_TO", 820_500_000.0, change=5.0),
        _frame("REVENUE", "CHANGE_BY", 16_000_000.0),
    ],
    "6f4a69b6f141b46673f2": [
        _frame("CASH", "ABSOLUTE_VALUE", 181_300_000.0),
        _frame("DEBT", "ABSOLUTE_VALUE", 637_500_000.0),
    ],
    "0dbbaed795d25e51a193": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            2.5,
            lower_value=2.0,
            upper_value=3.0,
        ),
    ],
    # APi Group.
    "671cf08a2c38c65c5fce": [
        _frame(
            "ADJUSTED_EBITDA_GUIDANCE",
            "RANGE_GUIDANCE",
            330_000_000.0,
            lower_value=325_000_000.0,
            upper_value=335_000_000.0,
        ),
    ],
    "3094256a6a08f6e849dd": [
        _frame("REVENUE", "CHANGE_BY", 8.8),
        _frame("REVENUE", "CHANGE_BY", 4.7),
    ],
    "cbd789aec398412c05cd": [_frame("GROSS_MARGIN", "CHANGE_BY", 30.0)],
    "87e149903adb670346cc": [
        _frame("GROSS_MARGIN", "CHANGE_BY", 60.0),
        _frame("GROSS_MARGIN", "CHANGE_BY", 20.0),
    ],
    "8701e82007f9e3a5b5ce": [_frame("OPERATING_MARGIN", "CHANGE_TO", 11.9, change=60.0)],
}


TABLE_IDS = {
    # Acadia.
    "8ea7c61d8583db914cdc",
    "55e0d0324295a5428e26",
    # Adient.
    "9a540fed187f1b9754a7",
    "5f58f33f326a4a39d2c7",
    "06cd373ed307f4ad65ee",
    # Advanced Energy.
    "b0854f0d6324fc10126c",
    "93c40f3e1b6cefc2d170",
    "e8313fbd8848b6c5ee1b",
    # AAR.
    "e5311d515f654ac01f14",
    # Aon.
    "c52edaefdd81f765b731",
    "97e8867778c55f90f15b",
    # APA.
    "87224cf2b951d5794d0f",
    # Ameriprise.
    "c5ff362751254eb5fcd3",
    "5743b4659cf734f71eab",
    "4a6a73bffbbb3df3fa46",
    "664a48601873c01e0951",
    "a3a0907e852acf14ac9e",
    # A. O. Smith.
    "c793c36297efa7dd923d",
    # APi Group.
    "60731bd73d6c4951be36",
    "1697379299fe8a4ead30",
}


NOTES = {
    "1d4ab46ca9eca7d3c66c": "narrative results bullets, not a positional table grid",
    "e771ce671518afff58cd": "patient days are volume; revenue per patient day is realization",
    "de2513aa75b31c2e6207": "cash flow is not a cash balance; embedded plus/minus revenue guidance is in scope",
    "72b885f237e821622f4b": "press-release lead is prose despite table-like numeric density",
    "510bbc4a914bc1356e90": "cash from operations and free cash flow are not cash balances",
    "b94c8afff3f9ebf79268": "awarded dollar contract is an orders/customer-demand fact",
    "c5cf956553fe9c7a85f9": "revenue per advisor is a realization/productivity anchor",
    "982816d094156e361aa9": "annuity and protection sales are business activity, not GAAP revenue",
    "5590eecb2e57401020f6": "operating cash flow and free cash flow are not cash balances",
    "8701e82007f9e3a5b5ce": "segment earnings margin is operating margin, not gross margin",
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
                    "exhaustive manual twenty-sixth annotation before prediction",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.8.3 twenty-sixth holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twenty-sixth candidate ids: {sorted(unknown)}")
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
