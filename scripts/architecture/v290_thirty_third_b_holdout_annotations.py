from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v290_thirty_third_b_holdout_candidates import CANDIDATES


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v290_thirty_third_b_holdout_annotations.jsonl"


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


# Exhaustive manual labels frozen before the first V2.9.0 prediction on this
# issuer/document-disjoint sample.  Definitions, disclaimers, operating cash
# flow, transaction consideration and non-issuer metrics are out of scope.
EXPECTED = {
    # Ampco-Pittsburgh.
    "970b6a4a69907d3a27a2": [_frame("ADJUSTED_EBITDA", "CHANGE_TO", 9_800_000.0, change=22.0)],
    "410b9639b964abb70b85": [_frame("ORDERS", "CHANGE_TO", 144_000_000.0, change=50.0)],
    "5dff34cc674dc2c55b17": [_frame("OPERATING_INCOME", "CHANGE_TO", 5_300_000.0, change=34.2)],
    "c9599aeab0f3e67bf5d1": [_frame("CASH", "ABSOLUTE_VALUE", 7_000_000.0)],
    # ARKO Corp.
    "3d11c7562c9c29e0ce36": [_frame("ACTIVITY_VOLUME_GUIDANCE", "ABSOLUTE_VALUE", 20.0)],
    # American Public Education.
    "e0ba09f6219df0c24aa9": [
        _frame("CASH", "CHANGE_TO", 222_800_000.0, change=46_300_000.0),
    ],
    "6376fc1a846e384ba64d": [
        _frame("REVENUE", "CHANGE_TO", 171_700_000.0, change=5.5),
        _frame("REVENUE", "CHANGE_BY", 7.8),
        _frame("REVENUE", "CHANGE_TO", 86_200_000.0, change=11.0),
        _frame("REVENUE", "CHANGE_TO", 85_500_000.0, change=4.7),
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 20_700_000.0, change=36.8),
    ],
    # Applied Digital.
    "0b60c93cca8e53928717": [_frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 39_900_000.0)],
    "73835645492404b50f97": [
        _frame("REVENUE", "COMPARATIVE", 37_300_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 38_000_000.0),
    ],
    "80dd305102f6e4dafca9": [
        _frame("REVENUE", "COMPARATIVE", 539_700_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 144_200_000.0),
    ],
    # AppLovin.
    "768b2917cd79aa525f29": [_frame("SHARES", "ABSOLUTE_VALUE", 335_000_000.0)],
    # AppFolio.
    "0434a8e08bb333817432": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            1_122_000_000.0,
            lower_value=1_117_000_000.0,
            upper_value=1_127_000_000.0,
        ),
    ],
    "99b762925197014d39b4": [
        _frame("REVENUE", "CHANGE_BY", 19.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 1_000_000_000.0),
    ],
    "d1f59c97ffc1f71010d9": [
        _frame(
            "OPERATING_MARGIN_GUIDANCE",
            "RANGE_GUIDANCE",
            27.25,
            lower_value=26.5,
            upper_value=28.0,
        ),
    ],
    "79b3680f4e954fbd8079": [_frame("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 36_000_000.0)],
    "588b0bd248f998f5de37": [_frame("REVENUE", "CHANGE_TO", 281_000_000.0, change=19.0)],
    "8362f9dcc2fbe0335e8c": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 76_000_000.0, change=24.0),
        _frame("OPERATING_MARGIN", "COMPARATIVE", 27.1),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 26.2),
    ],
    # Appian.
    "d606f5f6e94406c3313f": [_frame("REVENUE", "CHANGE_TO", 203_300_000.0, change=19.0)],
    "a09c6c060c3fbebf2835": [_frame("REVENUE", "CHANGE_TO", 45_600_000.0, change=20.0)],
    "7bdc5c7651c6be8495e9": [_frame("REVENUE", "CHANGE_TO", 131_700_000.0, change=23.0)],
    "09d40b184b4dda6b768b": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            134_000_000.0,
            lower_value=133_000_000.0,
            upper_value=135_000_000.0,
        ),
        _frame("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 18.0, lower_value=17.0, upper_value=19.0),
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            216_000_000.0,
            lower_value=214_000_000.0,
            upper_value=218_000_000.0,
        ),
        _frame("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 15.5, lower_value=14.0, upper_value=17.0),
        _frame(
            "ADJUSTED_EBITDA_GUIDANCE",
            "RANGE_GUIDANCE",
            31_500_000.0,
            lower_value=30_000_000.0,
            upper_value=33_000_000.0,
        ),
        _frame("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 72_600_000.0),
    ],
    # Digital Turbine.
    "941f3cf5fc60c45b530c": [_frame("REVENUE", "CHANGE_BY", 56.0)],
    "8145393773183ca5a613": [_frame("ADJUSTED_EBITDA", "CHANGE_TO", 42_500_000.0, change=69.0)],
    "e6e9bae582c86f414ae5": [_frame("REVENUE", "CHANGE_TO", 166_000_000.0, change=27.0)],
    "235aec6dfb91ebdf80ce": [
        _frame("REVENUE", "CHANGE_TO", 166_000_000.0, change=27.0),
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 42_500_000.0, change=69.0),
    ],
    # Alpha Pro Tech.
    "dd87791e6949fb581dd7": [
        _frame("REVENUE", "COMPOSITION", 90.0),
        _frame("REVENUE", "COMPOSITION", 6.0),
        _frame("REVENUE", "COMPOSITION", 4.0),
    ],
    "09dd135407ed550d55b5": [
        _frame("REVENUE", "CHANGE_TO", 18_700_000.0, change=12.0),
        _frame("REVENUE", "CHANGE_TO", 11_700_000.0, change=5.5),
        _frame("REVENUE", "CHANGE_TO", 7_000_000.0, change=24.9),
        _frame("CASH", "ABSOLUTE_VALUE", 18_900_000.0),
    ],
    "ba9b746b950b44d9a5d5": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 35.8),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 36.8),
    ],
    "341027351f13edd0e382": [
        _frame("REVENUE", "COMPOSITION", 93.0),
        _frame("REVENUE", "CHANGE_BY", 29.0),
    ],
    "a9d49b820d764729b81f": [_frame("SHARES", "ABSOLUTE_VALUE", 21_900_000.0)],
    "6d1811637d166180c45d": [_frame("REVENUE", "CHANGE_TO", 7_000_000.0, change=24.9)],
    "8980291633eab0ac727f": [
        _frame("CASH", "COMPARATIVE", 18_900_000.0),
        _frame("PRIOR_YEAR_CASH", "COMPARATIVE", 17_000_000.0),
    ],
    "f0c0bb8a239d559ecc2c": [
        _frame("REVENUE", "COMPOSITION", 7.0),
        _frame("REVENUE", "CHANGE_BY", 64_000.0, polarity="NEGATIVE"),
    ],
    "e712ad79173d82070043": [
        _frame("REVENUE", "CHANGE_BY", 608_000.0),
        _frame("REVENUE", "CHANGE_BY", 1_400_000.0),
    ],
    # Aptiv.
    "bbc299045a8d1a2bfb29": [_frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 613_000_000.0)],
    "838c10b82a856e66f581": [_frame("REVENUE", "CHANGE_BY", 2.0)],
    "8e32b9b9945be582f7d0": [
        _frame("ADJUSTED_EBITDA", "COMPARATIVE", 613_000_000.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 547_000_000.0),
    ],
}


TABLE_IDS = {
    "8853979abf3f4537e3b5",  # AP
    "162416f39fdf3f831739", "6b35aed41f7385344868", "b4518c88a7ccf57d77b5", "8c2bd74ed88e45f088b0",  # APC
    "167843ef832d30d6c6b6", "238574c0eea2b83c8a36", "cb9dce63f2bbf1792bcb",  # APEI
    "2d4e3e204601c50b79ba",  # APLD
    "1a2e8425410195ba7e18", "86555c5fef5c42e00e4f",  # APP
    "4b85542f0006d844bdf2",  # APPF
    "2c75e7e0346c50f7c7f7",  # APPN
    "c9abab79b6e00310e6e0",  # APPS
    "67f69abe3f194391b557", "c1d866c94c0fa1d1219b",  # APTV
}


NOTES = {
    "3d11c7562c9c29e0ce36": "targeted new fleet-fueling locations are forward activity guidance; calendar counts are not KPI values",
    "238574c0eea2b83c8a36": "dense multi-period guidance grid is TABLE_DSL despite inherited prose routing",
    "6376fc1a846e384ba64d": "issuer and segment revenue changes plus adjusted EBITDA are in scope; net income and operating cash flow are not",
    "99b762925197014d39b4": "headline growth and explicitly crossed trailing-twelve-month revenue are separate revenue facts",
    "09d40b184b4dda6b768b": "two revenue level ranges, two growth ranges, EBITDA range and share assumption are distinct guidance roles",
    "941f3cf5fc60c45b530c": "App Growth Platform percentage is revenue growth, corroborated by the issuer segment context",
    "09dd135407ed550d55b5": "narrative bullets are TEXT_IE despite inherited flattened-table routing",
    "f0c0bb8a239d559ecc2c": "product mix and the explicit dollar decline are separate revenue roles",
    "c1d866c94c0fa1d1219b": "pro-forma free-cash-flow layout is a positional table, not narrative text",
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
                "exhaustive manual thirty-third-B annotation before first V2.9.0 prediction",
            ),
        })
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.9.0 thirty-third-B holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown thirty-third-B candidate ids: {sorted(unknown)}")
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
