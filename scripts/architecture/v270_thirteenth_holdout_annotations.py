from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v270_thirteenth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v270_thirteenth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the first V2.7.0 prediction on this
# issuer- and document-disjoint holdout.  Operating cash flow is not a CASH
# balance; client sweep cash is not issuer cash; multi-purpose deployment is
# not CAPEX; tables and reconciliation grids are routed away from text IE.
EXPECTED = {
    # Analog Devices
    "274c62491e8b508f47fe": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 11_000_000_000.0),
    ],
    "ff528d919db7629036cb": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 4_020_000_000.0),
    ],
    "8c2c24997df75f926410": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            4_300_000_000.0,
            lower_value=4_200_000_000.0,
            upper_value=4_400_000_000.0,
        ),
    ],
    # Applied Materials
    "b95d9e25f29249e2cebe": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            10_250_000_000.0,
            lower_value=9_750_000_000.0,
            upper_value=10_750_000_000.0,
        ),
    ],
    "a0c795c908b8f43ca442": [
        _frame("REVENUE", "CHANGE_TO", 9_120_000_000.0, change=25.0),
    ],
    "fd6a0e3298764b39397f": [
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 50.4),
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 3_100_000_000.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 34.0),
    ],
    "af9a1b3f3ca36700aece": [
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 50.3),
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 3_080_000_000.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 33.7),
    ],
    "8c31dd2e283ce372e1b7": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 9_120_000_000.0),
    ],
    # BlackRock
    "eebacdaab56585740373": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 46.0),
    ],
    "9ea0f49bf948f6dc7004": [
        _frame("REVENUE", "CHANGE_BY", 1_300_000_000.0),
    ],
    # Cadence
    "57166dde8af2fade4601": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 45.5),
    ],
    "c88d5a50ea5c29e5e1b6": [
        _frame(
            "OPERATING_MARGIN_GUIDANCE",
            "RANGE_GUIDANCE",
            44.25,
            lower_value=43.75,
            upper_value=44.75,
        ),
    ],
    "8a11ca4f84c3723fe40b": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 28.4),
    ],
    "c15f0eaf21edce860b50": [
        _frame(
            "OPERATING_MARGIN_GUIDANCE",
            "RANGE_GUIDANCE",
            44.0,
            lower_value=43.5,
            upper_value=44.5,
        ),
    ],
    # Elevance Health
    "1ef1835124af569e97b8": [
        _frame("CASH", "ABSOLUTE_VALUE", 2_100_000_000.0),
    ],
    "3c09e42a554ae855f6fc": [
        _frame("REVENUE", "CHANGE_TO", 42_700_000_000.0, change=3.0),
    ],
    "74791be50ca447c90ada": [
        _frame("REVENUE", "CHANGE_TO", 49_800_000_000.0, change=400_000_000.0),
    ],
    # Equinix
    "d4865bd2519ff33eb2b0": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 665_000_000.0, change=35.0),
    ],
    "96157fb1c79f2a6983c2": [
        _frame(
            "CAPEX_GUIDANCE",
            "RANGE_GUIDANCE",
            5_500_000_000.0,
            lower_value=5_000_000_000.0,
            upper_value=6_000_000_000.0,
        ),
    ],
    # Intuit
    "e50051c44a2c345e291e": [
        _frame("REVENUE", "CHANGE_TO", 12_900_000_000.0, change=16.0),
        _frame("REVENUE", "CHANGE_TO", 9_900_000_000.0, change=19.0),
    ],
    "e834c1ac4c8bae616e41": [
        _frame("REVENUE", "CHANGE_TO", 8_600_000_000.0, change=11.0),
    ],
    "b34104f5a7e98e788703": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 5_900_000_000.0, change=20.0),
        _frame("OPERATING_INCOME", "CHANGE_TO", 8_900_000_000.0, change=18.0),
    ],
    "16749bb8dfc1d6e311f2": [
        _frame("REVENUE", "CHANGE_BY", 21.0),
        _frame("REVENUE", "CHANGE_BY", 10.0),
    ],
    # KLA
    "c4426ef909e301524631": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            4_000_000_000.0,
            lower_value=3_800_000_000.0,
            upper_value=4_200_000_000.0,
        ),
    ],
    "505acf129b35f4e99aa3": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 13_580_000_000.0),
    ],
    "766d0303519bad583c92": [
        _frame(
            "GROSS_MARGIN_GUIDANCE",
            "RANGE_GUIDANCE",
            62.5,
            lower_value=61.5,
            upper_value=63.5,
        ),
    ],
    "9d94112231863d99320a": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 3_660_000_000.0),
    ],
    "81680239846a93e9d27e": [
        _frame(
            "GROSS_MARGIN_GUIDANCE",
            "RANGE_GUIDANCE",
            61.6,
            lower_value=60.6,
            upper_value=62.6,
        ),
    ],
    # Regeneron
    "66f2dc0c3c73a9d8e9d9": [
        _frame("REVENUE", "CHANGE_TO", 489_000_000.0, change=30.0),
    ],
    "5822f1d9155fb9dc6951": [
        _frame("REVENUE", "CHANGE_TO", 6_000_000_000.0, change=38.0),
    ],
    "8eb59e21dd2b65b57b53": [
        _frame("REVENUE", "CHANGE_TO", 596_000_000.0, change=52.0),
    ],
    "a5dafd1e271680977fb8": [
        _frame("REVENUE", "CHANGE_TO", 4_300_000_000.0, change=17.0),
    ],
    # Charles Schwab
    "3f7abb4e7aed8da909f9": [
        _frame("ACTIVITY_VOLUME", "CHANGE_TO", 62_700_000_000.0, change=47.0),
        _frame("REVENUE", "CHANGE_TO", 7_100_000_000.0, change=21.0),
    ],
    "9e367f676e70d67cf39a": [
        _frame("REVENUE", "CHANGE_TO", 1_200_000_000.0, change=28.0),
    ],
    "b0817d2558853eae6722": [
        _frame("REVENUE", "CHANGE_TO", 7_100_000_000.0, change=21.0),
    ],
}


TABLE_IDS = {
    "34e2fb06d69a059d8d48",
    "509322297a898581509d",
    "7952fbc6e391ad6d84ef",
    "8876c0f429717986c15c",
    "4a32444a0b7d4ae6282e",
    "52c2e6a5720597f3562e",
    "532532be7c62c74395f4",
    "56b5e9563920871aaa11",
    "739b643eb16c766ee51c",
    "2d46e65d0c859d15fa71",
    "98994edc80b71d29b0a3",
    "afcb7d9ffecad1bc8ec8",
    "dddd834c18dc3123c789",
    "677e293c688a9ba7f8c1",
    "8d69cd3db2db3b1327b6",
    "bdb0f5b42dd2e1b47d5a",
    "f4d026c0e03b1c0ed154",
    "d2545304c06cb0813a88",
    "ecf2c3c986866f81b9de",
}


NOTES = {
    "2c2ed1f551955c1186da": "operating cash flow is not a CASH balance",
    "233b10f71eec64b8b4f4": "operating cash flow guidance is not a CASH balance",
    "5f7005c59ea6d8fb0e38": "operating cash flow is not a CASH balance",
    "c0e2e35f580131cda3e1": "client sweep cash is not issuer CASH",
    "6e6dbc86bd93a7759ea6": "client short cash credits are not issuer CASH",
    "55a8ccf2d23d9ede827a": "share-compensation amount is an included adjustment, not operating income",
    "8eb59e21dd2b65b57b53": "bullet prose misrouted as a flattened table by the frozen router",
    "282e1f1483dff5e9e1b7": "multi-purpose capital deployment is not a CAPEX amount and is prose",
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
                    "exhaustive manual thirteenth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.0 thirteenth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown thirteenth-holdout candidate ids: {sorted(unknown)}")
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
