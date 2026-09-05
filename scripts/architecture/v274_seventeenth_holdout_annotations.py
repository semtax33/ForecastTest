from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v274_seventeenth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v274_seventeenth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the first V2.7.4 prediction.  Numeric
# cash-flow measures are not treated as cash balances, definitions are not
# treated as issuer facts, and flattened multi-axis layouts are table-only.
EXPECTED = {
    # Cardinal Health
    "28ee60cb7da8aaa86872": [
        _frame("REVENUE", "CHANGE_TO", 63_700_000_000.0, change=6.0),
    ],
    "b92fe00cdf9e34f834e1": [
        _frame("REVENUE", "CHANGE_TO", 63_700_000_000.0, change=6.0),
    ],
    # Ford
    "01dc3d2ecb9545537684": [
        _frame("EBIT", "ABSOLUTE_VALUE", 919_000_000.0, polarity="NEGATIVE"),
        _frame("REVENUE", "ABSOLUTE_VALUE", 1_000_000_000.0),
    ],
    "9c6411a4c1c39df5194a": [
        _frame(
            "REVENUE",
            "CHANGE_TO",
            48_300_000_000.0,
            change=1_900_000_000.0,
            polarity="NEGATIVE",
        ),
        _frame("EBIT", "CHANGE_TO", 2_500_000_000.0, change=400_000_000.0),
    ],
    "824d43b633f536f7321d": [
        _frame("EBIT", "CHANGE_TO", 2_500_000_000.0, change=400_000_000.0),
    ],
    # lululemon
    "4715d760c77406427ff3": [
        _frame(
            "OPERATING_INCOME",
            "CHANGE_TO",
            276_900_000.0,
            change=37.0,
            polarity="NEGATIVE",
        ),
        _frame(
            "OPERATING_MARGIN",
            "CHANGE_TO",
            11.2,
            change=730.0,
            polarity="NEGATIVE",
        ),
    ],
    "57feb7bad75d20abc3cf": [
        _frame(
            "GROSS_MARGIN",
            "CHANGE_TO",
            54.2,
            change=410.0,
            polarity="NEGATIVE",
        ),
    ],
    "aa17095d65590970d912": [
        _frame("REVENUE", "CHANGE_TO", 2_500_000_000.0, change=4.0),
        _frame("REVENUE", "CHANGE_BY", 2.0),
    ],
    "1947f33627555f71c2f4": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            11_075_000_000.0,
            lower_value=11_000_000_000.0,
            upper_value=11_150_000_000.0,
        ),
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            0.5,
            lower_value=0.0,
            upper_value=1.0,
            polarity="NEGATIVE",
        ),
    ],
    "0d9e652d1da59876ad3c": [
        _frame("REVENUE", "CHANGE_BY", 1.0),
        _frame("REVENUE", "CHANGE_BY", 2.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 5.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 6.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 13.0),
        _frame("REVENUE", "CHANGE_BY", 8.0),
    ],
    # Bristol Myers Squibb
    "73d0d04452aa7837721c": [
        _frame(
            "REVENUE",
            "CHANGE_TO",
            55_000_000.0,
            change=47.0,
            polarity="NEGATIVE",
        ),
    ],
    # Motorola Solutions
    "19c25f7fe9acd8acf012": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 243_000_000.0),
        _frame("REVENUE", "CHANGE_BY", 35_000_000.0),
    ],
    "5d84ade555f5d918859e": [
        _frame("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 168_000_000.0),
    ],
    # Conagra Brands
    "47d04683d4527841a1a0": [
        _frame(
            "GROSS_MARGIN", "CHANGE_TO", 24.4, change=99.0, polarity="NEGATIVE"
        ),
        _frame(
            "GROSS_MARGIN", "CHANGE_TO", 24.5, change=130.0, polarity="NEGATIVE"
        ),
    ],
    "92b3fe6ffe2406a55c19": [
        _frame("REVENUE", "CHANGE_TO", 2_900_000_000.0, change=3.6),
        _frame("REVENUE", "CHANGE_BY", 0.5),
        _frame("REVENUE", "CHANGE_BY", 4.6, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 7.7),
    ],
    "9a97b58ab99e580cada4": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 11_000_000_000.0),
    ],
    "12037ee6972c90eb9d16": [
        _frame(
            "GROSS_MARGIN", "CHANGE_TO", 23.9, change=194.0, polarity="NEGATIVE"
        ),
        _frame(
            "GROSS_MARGIN", "CHANGE_TO", 24.0, change=175.0, polarity="NEGATIVE"
        ),
        _frame("REVENUE", "CHANGE_TO", 1_200_000_000.0, change=0.3),
        _frame("REVENUE", "CHANGE_BY", 8.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 7.8),
        _frame("REVENUE", "CHANGE_BY", 0.5),
        _frame("PRICE_REALIZATION", "CHANGE_BY", 4.0),
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 3.5, polarity="NEGATIVE"),
        _frame(
            "OPERATING_INCOME", "ABSOLUTE_VALUE", 13_000_000.0, polarity="NEGATIVE"
        ),
    ],
    # Clorox
    "96adc7c407351717d761": [
        _frame("REVENUE", "CHANGE_BY", 1.0),
    ],
    "33d7afa07a824e47ee44": [
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 25.0),
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 10.0),
    ],
    # Entergy
    "4923ac280a0d2b32534f": [
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 2.8),
    ],
    "79714e7f748f3d470f87": [
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 9.9),
    ],
    # Fastenal
    "87d556ff584ceaecf185": [
        _frame("REVENUE", "CHANGE_BY", 306_600_000.0),
        _frame("REVENUE", "CHANGE_BY", 14.7),
    ],
    "24c673b7ed90e63743d8": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 21.0),
    ],
    "48f7003caea7977a571f": [
        _frame("CAPEX", "COMPARATIVE", 60_500_000.0),
        _frame("PRIOR_YEAR_CAPEX", "COMPARATIVE", 64_300_000.0),
    ],
    "1fe40dca5e56864a2856": [
        _frame(
            "ACTIVITY_VOLUME_GUIDANCE",
            "RANGE_GUIDANCE",
            28_000.0,
            lower_value=27_000.0,
            upper_value=29_000.0,
        ),
    ],
    "0cba2563640fb179efea": [
        _frame("REVENUE", "CHANGE_BY", 14.7),
    ],
}


TABLE_IDS = {
    # Cardinal Health
    "ad48376eedd1e4169ab3",
    "a5c2f31473f5fe186777",
    # Chubb
    "fcfed6bf0dd35204cf54",
    "d2e1e6ef467d583d3cb1",
    "605c0d3680b2ce6f4583",
    # Ford
    "2d7ca4aacd9404d0838a",
    "65f6ef7834efc76130d9",
    # lululemon
    "8d19574edeae7e7cf70f",
    "a5ffd8e870fc79af1eb5",
    # Bristol Myers Squibb
    "d7869d4957ce221a9ee7",
    "8f9ffafad006465f79d7",
    "01fd5e9655d0e897627a",
    # Motorola Solutions
    "65c92c511c473572a2e8",
    # Conagra Brands
    "ea0af899dd02294b8d77",
    "8c4179fe3e831c8f6c4f",
    # Clorox
    "e23f996f6fb7a4165716",
    # Entergy
    "deca63a7023e7b0f44b9",
    "08dd2898699c509007f7",
    "efa57d2f27b6d25d1cee",
    # Fastenal
    "d0b6329881047f731802",
}


NOTES = {
    "28ee60cb7da8aaa86872": "headline plus grammatical earnings-release sentence, not a table",
    "de020bbf0d5af5acbb70": "operating/free cash flow is not a cash-balance fact",
    "01dc3d2ecb9545537684": "segment EBIT loss and segment revenue are separate local facts",
    "737fa2aa60d6413971a1": "risk-factor prose misrouted by the source layout, not a table",
    "1947f33627555f71c2f4": "level and decline-rate guidance ranges are separate frames",
    "33d7afa07a824e47ee44": "acquisition volume impacts are scoped operational bridge facts",
    "48f7003caea7977a571f": "current and prior property-and-equipment investment are CAPEX comparatives",
    "1fe40dca5e56864a2856": "device-signing goal is activity-volume guidance; prior goal is context only",
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
                    "exhaustive manual seventeenth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.4 seventeenth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown seventeenth-holdout candidate ids: {sorted(unknown)}")
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
