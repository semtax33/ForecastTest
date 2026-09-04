from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v264_seventh_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v264_seventh_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the V2.6.4 extractor is run on this set.
EXPECTED = {
    "2ed9d0ba1e02edd0ce1b": [_frame("ORDERS", "CHANGE_BY", 24.0)],
    "e4ce46bfcaa50da48b06": [
        _frame(
            "OPERATING_MARGIN",
            "CHANGE_TO",
            22.1,
            change=180.0,
            polarity="NEGATIVE",
        )
    ],
    "ec5a80444157fd8b9bb4": [_frame("REVENUE", "CHANGE_BY", 4.0)],
    "438936753530f24806a7": [
        _frame("REVENUE", "CHANGE_BY", 1.0, polarity="NEGATIVE")
    ],
    "060e2f90a3eac6d46616": [
        _frame("REVENUE", "CHANGE_BY", 17.0),
        _frame("REVENUE", "CHANGE_BY", 7.0),
    ],
    "1e04ff50d185947f231a": [
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 2_199_000_000.0, change=12.0)
    ],
    "842f8d75230b106cdecc": [
        _frame(
            "OPERATING_MARGIN",
            "CHANGE_TO",
            12.3,
            change=20.0,
            polarity="NEGATIVE",
        )
    ],
    "8310a97fa56eb5313249": [
        _frame("ORDERS", "ABSOLUTE_VALUE", 7_300_000_000.0),
        _frame("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.2),
        _frame("BACKLOG", "CHANGE_TO", 42_000_000_000.0),
    ],
    "5dcf904f6896cfadb1dc": [
        _frame("REVENUE", "CHANGE_TO", 5_900_000_000.0, change=8.0)
    ],
    "85cbf536d8155886de62": [
        _frame("REVENUE", "CHANGE_BY", 44_000_000.0)
    ],
    "964b8fcd331608639cc9": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 26.9, change=230.0)
    ],
    "22aa15367dde3efd4574": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 24.9, change=40.0)
    ],
    "cc2fe971b241f89569fa": [
        _frame(
            "OPERATING_MARGIN_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            75.0,
            lower_value=70.0,
            upper_value=80.0,
        )
    ],
    "571b07d63e13cdd72f25": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 25.0)
    ],
    "5a89d159224ed8ace7a1": [
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 4.5),
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 3.5),
    ],
    "7ce88efb545c01e930b1": [
        _frame("CASH", "ABSOLUTE_VALUE", 7_800_000_000.0),
        _frame("CASH", "ABSOLUTE_VALUE", 1_000_000_000.0),
    ],
    "5c90cecd3bf9b7001bc5": [
        _frame("ADJUSTED_EBITDA", "COMPARATIVE", 8_500_000_000.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 3_300_000_000.0),
    ],
    "e7d67f444be7eb3c7595": [
        _frame("THROUGHPUT", "ABSOLUTE_VALUE", 2_900_000.0)
    ],
    "6f6976af7326f6e14af9": [
        _frame("PRODUCTION", "ABSOLUTE_VALUE", 1_433.0)
    ],
    "369cda72e3a78832340b": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 1_600_000_000.0)
    ],
    "811723459c86d695fff5": [
        _frame("REVENUE", "CHANGE_TO", 24_700_000_000.0, change=14.0),
        _frame("REVENUE", "CHANGE_BY", 16.0),
    ],
    "ed117e4f240f3f1270e4": [
        _frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 91_200_000_000.0)
    ],
    "88fb77f83e5d70e8e3bb": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 22_800_000_000.0)
    ],
    "bb515a4be113cebb44ac": [_frame("REVENUE", "CHANGE_BY", 7.8)],
    "c7fcb2f394c848f2ab63": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 12.4)
    ],
    "0dcebd691100fcd73b57": [
        _frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 91_200_000_000.0),
        _frame(
            "OPERATING_INCOME_GUIDANCE",
            "ABSOLUTE_VALUE",
            8_650_000_000.0,
        ),
    ],
    "b65dc609727afdd57ab3": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 22_800_000_000.0)
    ],
    "43ec87bb75fc98b534a1": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 4.1)
    ],
    "24c1ffdb7d6fa5194f18": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 0.1),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 8.0),
    ],
    "9308877f17e20ac6041a": [
        _frame("OPERATING_INCOME", "COMPARATIVE", 318_000_000.0),
        _frame("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 54_000_000.0),
    ],
    "45f5853085006ab05205": [
        _frame("OPERATING_INCOME", "COMPARATIVE", 717_000_000.0),
        _frame(
            "PRIOR_YEAR_OPERATING_INCOME",
            "COMPARATIVE",
            79_000_000.0,
            polarity="NEGATIVE",
        ),
    ],
    "00cbae34465927794df4": [
        _frame("PRODUCTION", "ABSOLUTE_VALUE", 1.8)
    ],
    "d35b826319fa1e670482": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 13_000_000_000.0)
    ],
    "b13aa0c47e71a74f3539": [
        _frame("PRODUCTION_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 9.0)
    ],
}


TABLE_IDS = {
    "cedcaecba5b3aa90de8b",
    "99d756164e9dab982b8a",
    "233a2ff2665a890c509b",
    "30b025274f9c172fa31f",
    "bdf4627e33ee325e2887",
    "d77e9ea81d2604e7c890",
    "61fb7dda1f2db3534f98",
    "b76666cc151086519e7e",
    "3d2ac9a0400fe7ab00e6",
    "bb0ebc4d55c3ae549011",
    "49b788234adcf5dcb4d3",
    "b5d599d3155cd48e9d45",
    "fc21236f4c31195d65c2",
}


NOTES = {
    "890e52ce381d778275ae": (
        "cash flow and FCF are explicit, but capex is only described as a deduction"
    ),
    "571b07d63e13cdd72f25": (
        "about 25 percent is an operating-margin level even though revenue selected the block"
    ),
    "762830fbcb6fee28bbcf": (
        "50 percent is affiliate ownership attribution, not a capex level or change"
    ),
    "d35b826319fa1e670482": (
        "equal cash-capex and PP&E-addition amounts collapse under the duplicate contract"
    ),
    "00cbae34465927794df4": (
        "more than 1.8 Moebd is a production level despite a candidate quantity miss"
    ),
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
                    "exhaustive manual seventh-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.6.4 seventh holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown seventh-holdout candidate ids: {sorted(unknown)}")
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
