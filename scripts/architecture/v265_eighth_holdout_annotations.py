from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v265_eighth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v265_eighth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the V2.6.5 extractor is run.
EXPECTED = {
    "d482b7d50ebee521d291": [
        _frame("OPERATING_MARGIN", "COMPARATIVE", 20.9),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 17.3),
    ],
    "00768a03a42f763bdde0": [
        _frame("CASH", "ABSOLUTE_VALUE", 6_700_000_000.0)
    ],
    "7dafb7b508b899a0422f": [
        _frame("REVENUE", "COMPARATIVE", 10_999_000_000.0),
        _frame("REVENUE", "COMPARATIVE", 30_779_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 10_357_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 28_338_000_000.0),
    ],
    "78564f4ec8839abe65f8": [
        _frame("ORDERS", "CHANGE_BY", 41.0),
        _frame("ORDERS", "CHANGE_BY", 33.0),
        _frame("ORDERS", "CHANGE_BY", 17.0),
    ],
    "823c44edf07e52c75883": [
        _frame("REVENUE", "CHANGE_BY", 7.0),
        _frame("REVENUE", "CHANGE_BY", 6.0),
    ],
    "fec1e20351bc3f4a0937": [_frame("ORDERS", "CHANGE_BY", 41.0)],
    "1c58078a109ecdde7218": [_frame("BACKLOG", "CHANGE_BY", 103.0)],
    "1eca68c8c3f511d974cb": [
        _frame("REVENUE", "CHANGE_BY", 18.0),
        _frame("REVENUE", "CHANGE_BY", 25.0),
        _frame("REVENUE", "CHANGE_BY", 1.0),
    ],
    "e120b87cad3c0a642822": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 1_100_000_000.0, change=10.0),
        _frame("OPERATING_MARGIN", "CHANGE_TO", 27.5, change=190.0),
    ],
    "add43bdeb925b27351c3": [
        _frame("REVENUE", "CHANGE_TO", 4_000_000_000.0, change=18.0)
    ],
    "6172d9ff8c5c3396716e": [
        _frame("PRODUCTION", "ABSOLUTE_VALUE", 1_018.0)
    ],
    "ed9151c6d7b4b4f237bf": [
        _frame("REVENUE", "CHANGE_TO", 25_300_000_000.0, change=6.6),
        _frame("REVENUE", "CHANGE_BY", 5.6),
        _frame("REVENUE", "CHANGE_BY", 5.7),
    ],
    "8c7680bf1a28d9a5cbea": [
        _frame("REVENUE_GUIDANCE", "CHANGE_TO", 101_100_000_000.0, change=7.3)
    ],
    "e31310acf51557b35726": [
        _frame("REVENUE", "CHANGE_BY", 3.6),
        _frame("REVENUE", "CHANGE_BY", 10.0, polarity="NEGATIVE"),
    ],
    "05a1b3922b45bb1fc1ec": [
        _frame("REVENUE", "CHANGE_TO", 89_000_000_000.0, change=117.0),
        _frame("REVENUE", "CHANGE_TO", 96_200_000_000.0, change=18.0),
        _frame("REVENUE", "CHANGE_BY", 106.0),
    ],
    "dac66cc44f6232d89e08": [
        _frame("REVENUE", "CHANGE_TO", 89_000_000_000.0, change=18.0),
        _frame("REVENUE", "CHANGE_BY", 117.0),
    ],
    "241601080611c4eb93bf": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            108_000_000_000.0,
            lower_value=105_840_000_000.0,
            upper_value=110_160_000_000.0,
        )
    ],
    "1b8aac8dd142059e563a": [
        _frame("REVENUE", "CHANGE_TO", 26_500_000_000.0, change=5.3),
        _frame("REVENUE", "CHANGE_BY", 5.0),
        _frame("REVENUE", "CHANGE_BY", 20.1),
    ],
    "711af93222c23187b0b4": [
        _frame("OPERATING_MARGIN", "COMPARATIVE", 9.6),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 5.2),
    ],
    "33f95c65dceea08b1acb": [
        _frame("OPERATING_MARGIN_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 50.0),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 4.6),
    ],
    "ff0cc6c0987317404f7e": [
        _frame("REVENUE", "CHANGE_BY", 12.0),
        _frame("REVENUE", "CHANGE_BY", 4.0),
    ],
}


TABLE_IDS = {
    "741b2e721298d9fd25a2",
    "5df8e7214d5656e06fcd",
    "4c4c9b1f26a54e4cdcdd",
    "2c689727d35cd694a90d",
    "da73c87df4402046cd22",
    "4c4574c7df25a30af7fb",
    "6a4b321a6d5191640e7c",
    "69e7a0fa2f2cf7816ecd",
    "a25f94b0a34ad609235e",
    "cb7c8939b417520038c9",
    "3654b0f1fb11269989e3",
    "88bac41436e4ce58c1d5",
    "d3ceccf0918019adcbd5",
    "c22deced30fc93bc746a",
    "a44913bd52bc58e2b28e",
    "2158ee5dc45603ebb63d",
    "a7c9f3cb59e92a28ca9c",
    "c60b9ce970bf5ba47d4c",
    "ebafca0c6ee2410a51c0",
    "88a126ba3265b9d1d53f",
    "c720ac6a54aa40d99dbb",
    "dc0c60eb9e018f8be725",
    "2ec4ab4a3060d684904d",
    "683e73e275c47c3726c5",
    "e6077a1557ee33752084",
}


NOTES = {
    "0075fb7b350e4e99cae": (
        "tariff recoveries are an operating-profit driver, not the profit level"
    ),
    "00768a03a42f763bdde0": (
        "4.4 billion is operating cash flow; 6.7 billion is enterprise cash"
    ),
    "081bce515e527a0529f8": (
        "439 million is acquisition consideration net of cash, not a cash balance"
    ),
    "89c9bb16b46814c3adf1": (
        "amounts belong to expenses and cost of sales, not revenue"
    ),
    "add43bdeb925b27351c3": (
        "run-on prose headline, not a financial table despite the predicted route"
    ),
    "f90cfa3704d9b39cf0d6": (
        "202.95 is a share price, not a cash balance"
    ),
    "2ec4ab4a3060d684904d": (
        "dense GAAP/non-GAAP fiscal summary is table-only"
    ),
    "3828cf9dc8caf6a70be7": (
        "994 million is a cost-of-sales reduction, not revenue"
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
                    "exhaustive manual eighth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.6.5 eighth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown eighth-holdout candidate ids: {sorted(unknown)}")
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
