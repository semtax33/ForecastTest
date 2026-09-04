from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v262_sixth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v262_sixth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


EXPECTED = {
    "62a55084b5f0a1e4bb64": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 18.1)
    ],
    "64c38a0800b1776a85aa": [_frame("ORDERS", "ABSOLUTE_VALUE", 246.0)],
    "04d677580d4d8f98ef7f": [
        _frame("BACKLOG", "ABSOLUTE_VALUE", 33_000_000_000)
    ],
    "3cfc59a7d7c89cca9fe8": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", -0.2)
    ],
    "9930d018718f895a09cb": [
        _frame("BACKLOG", "ABSOLUTE_VALUE", 85_000_000_000),
        _frame("ORDERS", "COMPOSITION", 27.0),
    ],
    "d6cbda5989ed01c46f29": [
        _frame("DEBT", "CHANGE_BY", 8_400_000_000, polarity="NEGATIVE")
    ],
    "7827ddcfe9e701c336e8": [_frame("PRODUCTION", "CHANGE_BY", 20.0)],
    "1fda1aee1537909efb97": [
        _frame("OPERATING_INCOME_GUIDANCE", "ABSOLUTE_VALUE", 4_900_000_000)
    ],
    "8d2e2c4d4b04931c50ab": [
        _frame("OPERATING_INCOME_GUIDANCE", "ABSOLUTE_VALUE", 4_900_000_000)
    ],
    "020c87dbd0fa9ec3fdcf": [
        _frame("REVENUE", "CHANGE_BY", 4.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 1.0),
        _frame("REVENUE", "CHANGE_BY", 1.0),
    ],
    "a1eb2d14bc782e8edde3": [
        _frame("REVENUE", "CHANGE_BY", 10.0),
        _frame("REVENUE", "CHANGE_BY", 2.0),
        _frame("REVENUE", "CHANGE_BY", 2.0),
    ],
    "d516d263338afc265fea": [
        _frame("CAPEX_GUIDANCE", "ABSOLUTE_VALUE", 9_000_000_000)
    ],
    "e3739a65b48881e5a552": [
        _frame("REVENUE", "CHANGE_BY", 8.0),
        _frame("REVENUE", "CHANGE_BY", 4.0, polarity="NEGATIVE"),
    ],
    "badd7d1032b0c9d006e7": [
        _frame("REVENUE", "CHANGE_TO", 25_200_000_000, change=7.0)
    ],
    "5f04078f297915dafa81": [_frame("REVENUE", "CHANGE_BY", 3.0)],
    "4e1d270c940fad8a9646": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 20.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 4.0),
    ],
    "f7accc14cdf7f5035647": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 2_700_000_000, change=18.0)
    ],
    "1a1f511a392b7e927c64": [
        _frame("ORDERS", "CHANGE_TO", 16_500_000_000, change=17.0)
    ],
    "ec15a7e91a1187a7ffd5": [_frame("REVENUE", "CHANGE_BY", 20.0)],
    "65ebe2a1d4f3456dda2f": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 12.0)
    ],
    "76ce3b14b928c05fa6a6": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 23.0)
    ],
    "eab0528557d4bb899402": [
        _frame("REVENUE", "CHANGE_BY", 7.0),
        _frame("REVENUE", "CHANGE_BY", 6.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 9.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 6.0),
        _frame("OPERATING_MARGIN", "COMPARATIVE", 34.9),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 34.1),
        _frame("OPERATING_MARGIN", "COMPARATIVE", 35.6),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 34.7),
    ],
    "50aec10c926e2b7080ab": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 2_200_000_000)
    ],
    "85c8e1cde2e6bbd2ef06": [
        _frame("OPERATING_MARGIN", "COMPARATIVE", 34.9),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 34.1),
        _frame("OPERATING_MARGIN", "COMPARATIVE", 35.6),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 34.7),
    ],
    "57c7747e774b135f7d84": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 1.0, polarity="NEGATIVE")
    ],
}


TABLE_IDS = {
    "749e08e4a44c6d368812",
    "4330f525f68f17b16964",
    "bfc037c2e656da87812d",
    "5e2addeefcacc155e7b7",
    "d7ff3b77e6d48baf14e6",
    "e07e2064ad1c3b2e3454",
    "8ee7cc6060ed269f8ab6",
    "824d0368a796caca9972",
    "b221afe99d9e6e48e7ff",
    "0dc1620caf081add6b4b",
}


NOTES = {
    "64c38a0800b1776a85aa": "booked order count is a company KPI despite omitted lexical unit after 246",
    "3cfc59a7d7c89cca9fe8": "parenthesized negative percentage is a negative absolute margin",
    "680e0794045b2db26a0e": "50 percent is affiliate ownership, not sales or revenue change",
    "41e8e13d4bbadf02edc": "cost values belong to SG&A, not the trailing sales phrase",
    "5e2addeefcacc155e7b7": "guidance reconciliation is a flattened table even though the router predicted prose",
    "590029f9d5a8d37706d6": "non-reconciliation disclaimer is prose and contains no company KPI value",
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
                    "exhaustive manual sixth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.6.2 sixth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown sixth-holdout candidate ids: {sorted(unknown)}")
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
