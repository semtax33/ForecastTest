from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v26_fourth_holdout_candidates import CANDIDATES


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v26_fourth_holdout_annotations.jsonl"


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


EXPECTED = {
    "30f42353cee3ccd340aa": [_frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 34.3)],
    "db80960c2f0243f195c1": [_frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 23.5)],
    "866ad24fc18cbd2a608c": [_frame("REVENUE", "CHANGE_TO", 4_000_000_000, change=24.0)],
    "8f16764a164cb23026f8": [_frame("REVENUE", "CHANGE_BY", 936_000_000)],
    "581d8c1efb263faa0518": [_frame("REVENUE", "CHANGE_BY", 794_000_000)],
    "3cf8d6cc7a893302eaf8": [_frame("REVENUE", "CHANGE_TO", 16_700_000_000, change=16.3)],
    "32c6a8cb2d78118df6ad": [
        _frame("REVENUE", "CHANGE_BY", 26.0),
        _frame("REVENUE", "CHANGE_BY", 4.0),
    ],
    "764cfad2cb4fd2d87381": [_frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 4_400_000_000)],
    "f04b1593064d864f1c60": [_frame("CAPEX", "ABSOLUTE_VALUE", 1_300_000_000)],
    "741976e0a0c113012e1a": [
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 272_500_000, lower_value=255_000_000, upper_value=290_000_000),
        _frame("GROSS_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 29.75, lower_value=29.0, upper_value=30.5),
    ],
    "a17b63b685797c7ef7a0": [
        _frame("REVENUE", "COMPARATIVE", 191_900_000),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 103_000_000),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 151_100_000),
        _frame("GROSS_MARGIN", "COMPARATIVE", 27.7),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 30.3),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 29.1),
    ],
    "bd48980497a68969e10d": [_frame("CAPEX", "ABSOLUTE_VALUE", 50_200_000)],
    "41e8e13d4bbadf02edc0": [_frame("REVENUE", "CHANGE_TO", 79_700_000, change=39.3)],
    "c6cbd0999e6b858c2509": [
        _frame("REVENUE", "CHANGE_TO", 8_200_000, change=5.1),
        _frame("CASH", "CHANGE_TO", 50_300_000, change=31.0),
        _frame("DEBT", "ABSOLUTE_VALUE", 0.0),
    ],
    "3cfe153032ea8106dc55": [_frame("PRODUCTION", "ABSOLUTE_VALUE", 33_000)],
    "8b70a97524d71c6a3cb1": [
        _frame("REVENUE", "CHANGE_BY", 17_400_000),
        _frame("REVENUE", "CHANGE_BY", 5.8),
    ],
    "b387da7e2275a04cadb7": [_frame("REVENUE", "CHANGE_BY", 4_500_000, polarity="NEGATIVE")],
}


TABLE_IDS = {
    "d624cc327bb23ba139a1", "f13e89692566a5009273", "66a3f3644062c4e4241b",
    "69e7fae86ab93faa05e4", "4c4ff69581a729185163", "89da00b6cdb30792b2c6",
    "acff8ae74ef3168ccc24", "0e3c12551b2895487101", "49535c1de78285aad7bf",
    "402ecff577fb480d557f", "e2cf1169b95fa26216b7", "27aa97ac1056f3051b36",
    "756b47427fb7a90136a7", "af61d8e9541e90a2b321", "d2617efb6d4433717995",
    "1e46e09be3db8bab75a4", "88731cc47aee22864981", "3c715b9971258665884a",
    "b7d6efdb4a2804f0fb21", "bc71e9e6355d6deb7c8c", "0f75e5865d837445b1d7",
    "2545492185e047844687", "5ab5f47d2361f3009cb5",
}


NOTES = {
    "f04b1593064d864f1c60": "single capex sentence with aircraft detail; not a financial grid",
    "a17b63b685797c7ef7a0": "bullet comparisons remain text semantics",
    "c6cbd0999e6b858c2509": "bullet KPI list remains text semantics",
    "332d2f138131ff786efc": "transaction prose with many quantities; no operating KPI fact",
    "52b3fe74a152c979b894": "Internal Revenue Code glossary false metric mention",
}


def main() -> int:
    candidates = pd.read_csv(CANDIDATES)
    rows = []
    for item in candidates.itertuples(index=False):
        expected = EXPECTED.get(item.candidate_id, [])
        route = "TABLE_DSL" if item.candidate_id in TABLE_IDS else "TEXT_IE" if expected else "NO_FACT"
        rows.append({
            "candidate_id": item.candidate_id,
            "ticker": item.ticker,
            "gold_route": route,
            "expected_frames": expected,
            "annotation_note": NOTES.get(item.candidate_id, "exhaustive manual fourth-holdout annotation"),
        })
    if len(rows) != 100 or len({item["candidate_id"] for item in rows}) != 100:
        raise ValueError("V2.6 fourth holdout annotations must cover 100 unique blocks")
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS.write_text(
        "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in rows),
        encoding="utf-8",
    )
    print(f"ANNOTATED={len(rows)} EXPECTED_FRAMES={sum(len(item['expected_frames']) for item in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
