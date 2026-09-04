from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v268_eleventh_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v268_eleventh_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before any V2.6.8 prediction is run on the
# eleventh holdout.  Only direct company KPI facts expressible by the semantic
# frame contract are included.  Cash-flow measures are not CASH balances.
EXPECTED = {
    # Salesforce
    "5b1cb9cd81ee37419dd3": [
        _frame("OPERATING_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 20.1),
        _frame("OPERATING_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 34.3),
    ],
    "6a69c9c2724434d82501": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 20.5),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 34.1),
    ],
    "1c596681e14341a438d9": [
        _frame("REVENUE", "CHANGE_TO", 10_800_000_000.0, change=12.0),
        _frame("REVENUE", "CHANGE_BY", 11.0),
    ],
    # Broadcom
    "c12d8af140ec38b56b3b": [
        _frame("REVENUE", "CHANGE_TO", 22_187_000_000.0, change=48.0),
    ],
    "d2fa84d33b10cdb837f2": [
        _frame("OPERATING_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 67.0),
    ],
    "bf8cdb8f4e678920c31d": [
        _frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 15_244_000_000.0),
    ],
    "fbbaea43a1eb6079b7aa": [
        _frame("REVENUE", "CHANGE_TO", 10_800_000_000.0, change=143.0),
        _frame("REVENUE_GUIDANCE", "CHANGE_TO", 16_000_000_000.0, change=200.0),
        _frame("REVENUE", "CHANGE_TO", 22_200_000_000.0, change=48.0),
    ],
    "fead62aa72b7c84ae362": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 231_000_000.0),
    ],
    # Micron
    # The combined 30.2B liquidity measure is not a pure cash balance.
    # Amgen
    "bcd6ea8ba3fd49b88413": [
        _frame("REVENUE", "CHANGE_TO", 314_000_000.0, change=17.0, polarity="NEGATIVE"),
    ],
    "aa73c60ff5aab87ab03d": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            38_800_000_000.0,
            lower_value=38_200_000_000.0,
            upper_value=39_400_000_000.0,
        ),
    ],
    "bed26cfe50a04c432aee": [
        _frame("REVENUE", "CHANGE_BY", 19.0),
        _frame("PRICE_REALIZATION", "CHANGE_BY", 15.0),
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 2.0),
    ],
    "ccdea6ba2603ae2360ff": [
        _frame("CASH", "ABSOLUTE_VALUE", 14_000_000_000.0),
        _frame("DEBT", "ABSOLUTE_VALUE", 57_300_000_000.0),
    ],
    "df79ecad957f2880ef1a": [
        _frame("REVENUE", "CHANGE_TO", 486_000_000.0, change=42.0),
    ],
    "6bb60a67f03f7104264d": [
        _frame("REVENUE", "CHANGE_TO", 153_000_000.0, change=20.0, polarity="NEGATIVE"),
        _frame("PRICE_REALIZATION", "CHANGE_BY", 16.0, polarity="NEGATIVE"),
    ],
    # Biogen
    "58e39217930eeb575eb6": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 41_000_000.0),
    ],
    "9b87ca4414c925cf4d4c": [
        _frame("REVENUE", "CHANGE_TO", 197_000_000.0, change=7.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 7.0),
    ],
    "baa25a0e95dbb279bfae": [
        _frame("REVENUE", "CHANGE_TO", 168_000_000.0, change=29.0),
    ],
    # Air Products
    "97fea10a08f0980bdb1d": [
        _frame("REVENUE", "CHANGE_TO", 886_000_000.0, change=9.0),
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 6.0),
    ],
    # Southern Company
    "99a806e4bfabb3b516a4": [
        _frame("REVENUE", "COMPARATIVE", 15_400_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 14_700_000_000.0),
    ],
    "cc3089db2e3b99472f8c": [
        _frame("REVENUE", "COMPARATIVE", 6_980_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 6_970_000_000.0),
    ],
    # S&P Global
    "282b4e84330df6966fd7": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 1_998_000_000.0, change=15.0),
    ],
    "2b153bfe44aa4f6d2dc8": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            6.9,
            lower_value=5.9,
            upper_value=7.9,
        ),
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            7.0,
            lower_value=6.0,
            upper_value=8.0,
        ),
    ],
    "22f4de9342dc3a836180": [
        _frame("REVENUE", "CHANGE_TO", 4_146_000_000.0, change=10.0),
    ],
    "0a2a19324145c38c8d06": [
        _frame("REVENUE", "CHANGE_TO", 3_678_000_000.0, change=11.0),
    ],
    # Intercontinental Exchange
    "c9d5968fdad131ed7291": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 645_000_000.0),
    ],
    "8da61fb00509842074cd": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 1_600_000_000.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 61.0),
    ],
    "a8651115f063347df852": [
        _frame("REVENUE", "CHANGE_TO", 2_700_000_000.0, change=5.0),
    ],
    "ec84ee89f29883c28413": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 268_000_000.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 42.0),
    ],
    # CME Group
    "d2fd2cfaea9cb18224a2": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 1_400_000_000.0),
    ],
    "d4ccc26b3c438e62f39d": [
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 29_800_000.0),
    ],
    "7359f1e616fac3d7d004": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 1_700_000_000.0),
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 1_100_000_000.0),
    ],
    "135205a6cd54cfd5043a": [
        _frame("REVENUE", "CHANGE_TO", 238_000_000.0, change=20.0),
    ],
    "a7f77f6c45f85a078fe2": [
        _frame("CASH", "ABSOLUTE_VALUE", 2_300_000_000.0),
        _frame("DEBT", "ABSOLUTE_VALUE", 3_400_000_000.0),
    ],
    "ffeeea986fc33df8892a": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 1_200_000_000.0),
    ],
}


TABLE_IDS = {
    # Salesforce
    "74f6224f9f0c3d866bed",
    # Broadcom (the first block contains an embedded financial table)
    "9b26d25a29785faa118e",
    "6fa25ccce45ba20001bb",
    # Micron
    "6490bfcdf1fed752838f",
    "9202ba7349f68d8744e6",
    "e575dd2eab89036464f8",
    # Amgen: e9c is a flattened grid; 6bb is causal prose.
    "e9c05dbaeb68cfb9740f",
    # Biogen
    "c46559295770d0022433",
    "dccfbed53e7e8535c236",
    # Air Products
    "2f27c32f16477d11f1ba",
    "72a99b60e8d5261dd5fe",
    "d96ab46594527ab679ac",
    # Southern Company
    "577d6f35297ad8f8f474",
    "b074e7d51859654c039d",
    # S&P Global
    "dd05e5038bed0f1830ce",
    "94e5a8e886a5843a4716",
    # Intercontinental Exchange
    "1915dd11bd3faa074c2d",
    "8b84e191f9b00546b415",
    "b117a3fcb01aee56e429",
    "265cf574dadb8f04d2c0",
    # CME Group: operating-statistics block was sampled as prose.
    "19851a95c4efca33eaa8",
    "e5188effdaa06f2a07b1",
}


NOTES = {
    "545f0417c4405924679d": "operating cash flow and free cash flow are not CASH balances",
    "9b26d25a29785faa118e": "prose lead-in contains an embedded financial table",
    "4b6bef0a032faf633973": "30.2B combines cash, investments, and restricted cash",
    "6bb60a67f03f7104264d": "direct causal KPI prose despite source table sampling",
    "52b561fd62c8fa55abde": "table-adjacent explanatory note, not a flattened grid or revenue fact",
    "19851a95c4efca33eaa8": "flattened operating-statistics grid despite prose sampling",
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
                    "exhaustive manual eleventh-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.6.8 eleventh holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown eleventh-holdout candidate ids: {sorted(unknown)}")
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
