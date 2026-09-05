from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v288_thirty_first_holdout_candidates import CANDIDATES


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v288_thirty_first_holdout_annotations.jsonl"


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


# Exhaustive manual labels frozen before the first V2.8.8 prediction. Cash-flow
# measures are not cash balances, dollar gross profit is not a percent margin,
# and press-release KPI headlines remain prose even when visually list-like.
EXPECTED = {
    # Ambow Education.
    "dc50f375fa88ec6ecd22": [_frame("REVENUE", "CHANGE_TO", 2_400_000.0, change=14.3, polarity="NEGATIVE")],
    "305d96431d78978bba70": [
        _frame("REVENUE", "CHANGE_TO", 5_200_000.0, change=2.0),
        _frame("REVENUE", "CHANGE_TO", 2_400_000.0, change=14.3, polarity="NEGATIVE"),
        _frame("GROSS_MARGIN", "COMPARATIVE", 55.8),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 54.9),
        _frame("CASH", "ABSOLUTE_VALUE", 7_200_000.0),
    ],
    "e4a4c99028c3572d951f": [_frame("REVENUE", "CHANGE_TO", 5_200_000.0, change=2.0)],
    "1ea804a7888740e3f577": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 50.0),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 53.6),
    ],
    "4033c79249eef28183ae": [
        _frame("OPERATING_INCOME", "COMPARATIVE", 300_000.0),
        _frame("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 500_000.0),
    ],
    "32829b3cf6082a86bb06": [
        _frame("OPERATING_INCOME", "COMPARATIVE", 100_000.0, polarity="NEGATIVE"),
        _frame("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 300_000.0),
    ],
    "5941b24e8ce7666b4d3f": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 55.8),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 54.9),
    ],
    # AMC Entertainment.
    "1776cf075665f32f8082": [_frame("DEBT", "CHANGE_BY", 282_000_000.0, polarity="NEGATIVE")],
    "2115e2e83884c9b7ae51": [_frame("CASH", "ABSOLUTE_VALUE", 778_400_000.0)],
    "0536b46abcb7d0a47552": [_frame("ADJUSTED_EBITDA", "CHANGE_BY", 336.7)],
    # Amplify Energy.
    "b4588f155678b88579e6": [_frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 8_600_000.0)],
    "d4f19c3147c5d7f5d6c0": [_frame("CAPEX", "ABSOLUTE_VALUE", 20_700_000.0)],
    # Amarin.
    "a668ca04a3defb5b0e28": [_frame("CASH", "CHANGE_BY", 10.0)],
    # American Shared Hospital Services.
    "b1ceb025f0090150ace1": [_frame("REVENUE", "CHANGE_TO", 6_565_000.0, change=3_000.0)],
    "c47779fa67f6edc8efaa": [
        _frame("REVENUE", "COMPARATIVE", 4_300_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 3_600_000.0),
    ],
    "8d57bf29012f4be80119": [_frame("REVENUE", "CHANGE_TO", 2_300_000.0, change=22.0)],
    "a42c328540a5f35fe02f": [
        _frame("REVENUE", "CHANGE_TO", 8_400_000.0, change=19.0),
        _frame("REVENUE", "CHANGE_TO", 4_900_000.0, change=40.0),
        _frame("REVENUE", "CHANGE_TO", 2_300_000.0, change=22.0),
        _frame("REVENUE", "CHANGE_TO", 2_700_000.0, change=56.0),
        _frame("CASH", "COMPARATIVE", 6_800_000.0),
        _frame("PRIOR_YEAR_CASH", "COMPARATIVE", 3_700_000.0),
    ],
    # American Superconductor.
    "2841f065226b3c8d2b7a": [_frame("ORDERS", "ABSOLUTE_VALUE", 130_000_000.0)],
    "99025fdc2c957da4e49c": [_frame("ORDERS", "ABSOLUTE_VALUE", 130_000_000.0)],
    # Amerant Bancorp.
    "1e561cb73c4cf5a24c6c": [_frame("CASH", "CHANGE_TO", 301_100_000.0, change=59.6)],
    "f131254ccdecc4b20668": [_frame("REVENUE", "CHANGE_TO", 82_600_000.0, change=2.9)],
    # Amentum.
    "b7bf8348cd3e31d6fe2d": [
        _frame("DEBT", "ABSOLUTE_VALUE", 3_875_000_000.0),
        _frame("CASH", "ABSOLUTE_VALUE", 459_000_000.0),
        _frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 1_128_000_000.0),
    ],
    "ba39f9829c9dc7c83d46": [_frame("REVENUE", "CHANGE_BY", 5.0, polarity="NEGATIVE")],
    "9c50bb543c1fdac3de24": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 3_500_000_000.0),
        _frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 290_000_000.0),
        _frame("BACKLOG", "ABSOLUTE_VALUE", 48_200_000_000.0),
        _frame("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.1),
        _frame("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.3),
    ],
    # Aemetis.
    "ae2d1dc49a2bcb626276": [
        _frame("CASH", "COMPARATIVE", 1_000_000.0),
        _frame("PRIOR_YEAR_CASH", "COMPARATIVE", 4_900_000.0),
    ],
    "c92528f38d13e38cea72": [_frame("REVENUE", "ABSOLUTE_VALUE", 2_500_000.0, polarity="NEGATIVE")],
    "f69141540e2d7d2dd977": [
        _frame("OPERATING_INCOME", "COMPARATIVE", 600_000.0, polarity="NEGATIVE"),
        _frame("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 26_200_000.0, polarity="NEGATIVE"),
    ],
    # American Well.
    "173c62801521f4c5101d": [
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 47_000_000.0, lower_value=46_000_000.0, upper_value=48_000_000.0),
    ],
    "60a8b59ec0bd01fef1d9": [
        _frame(
            "ADJUSTED_EBITDA_GUIDANCE",
            "RANGE_GUIDANCE",
            8_000_000.0,
            lower_value=7_000_000.0,
            upper_value=9_000_000.0,
            polarity="NEGATIVE",
        ),
    ],
}


TABLE_IDS = {
    "58ba795e73e42396ab44",  # AMBO balance sheet.
    "a9601e2cf6514beaa29f",  # AMC financial results.
    "fb042240594311ec0693",  # AMPY guidance grid.
    "05e948e5901ba879f4c7", "62c56cc46c7474a922c1",  # AMRN header fragment and statements.
    "3b1e0f49217fe7f6b593",  # AMS statements.
    "6d893db812987a352a60",  # AMSC statements.
    "f039ef68dde570a4442d", "44fc044b5daaa715d9b7", "4592275c98a70f328b97",  # AMTB tables.
    "303cb30446be9da8ad29", "551df30d977099973845",  # AMTM guidance and results.
    "1714fc3368b7954f9a79",  # AMTX balance sheet.
    "ffb828780f28ad1ab870",  # AMWL statements.
}


NOTES = {
    "05e948e5901ba879f4c7": "fragment introduces a numeric revenue-comparison table and has no complete prose assertion",
    "9c50bb543c1fdac3de24": "multi-KPI press-release headline is prose, not a positional numeric grid",
    "1baaa43b6759abec3111": "issuer labels dollar gross profit as gross margin; ontology margin requires percent or basis points",
    "462a6a553bfe0d6e4452": "operating, investing and financing cash flows are not cash balance facts",
    "08426cd1f85ed9a96155": "gross profit dollars and corn unit cost are outside the current critical concept ontology",
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
            "annotation_note": NOTES.get(
                item.candidate_id,
                "exhaustive manual thirty-first annotation before prediction",
            ),
        })
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.8.8 thirty-first holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown thirty-first candidate ids: {sorted(unknown)}")
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    expected_count = sum(len(row["expected_frames"]) for row in rows)
    print(f"ANNOTATED={len(rows)} EXPECTED_FRAMES={expected_count} TABLE_BLOCKS={len(TABLE_IDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
