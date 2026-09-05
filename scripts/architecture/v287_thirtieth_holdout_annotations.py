from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v287_thirtieth_holdout_candidates import CANDIDATES


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v287_thirtieth_holdout_annotations.jsonl"


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


# Exhaustive manual labels frozen before the first V2.8.7 prediction. Banking
# net interest income is a revenue anchor; cash-flow measures, liquidity limits,
# milestone payments and per-share values are not CASH balance facts.
EXPECTED = {
    # Amalgamated Bank.
    "f12b7faa18001cabf203": [_frame("REVENUE", "CHANGE_BY", 1_400_000.0)],
    "17b11a2d71689bf8bac5": [_frame("REVENUE", "CHANGE_TO", 297_800_000.0, change=5.5)],
    # Amanat Acquisition.
    "471089391aada7490ab8": [_frame("DEBT", "ABSOLUTE_VALUE", 134_056.0)],
    # Ambarella.
    "7bb7327e562549ead0e3": [_frame("REVENUE", "CHANGE_TO", 100_400_000.0, change=16.9)],
    "34799c2d1ca601482442": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 59.9),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 62.0),
    ],
    # Ambiq Micro.
    "752f4b31fe7fe5144c67": [_frame("REVENUE", "CHANGE_BY", 90.0)],
    "45aec2d90b9a590321ff": [
        _frame("GROSS_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 47.0, lower_value=46.5, upper_value=47.5),
    ],
    "cd9a446b52f2e1301a69": [_frame("REVENUE", "CHANGE_BY", 90.0)],
    "be4f1faec55fa6136c57": [_frame("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 24_170_000.0)],
    "d490a6abae941abf447b": [
        _frame("REVENUE", "CHANGE_BY", 90.0),
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 36_500_000.0, lower_value=36_000_000.0, upper_value=37_000_000.0),
    ],
    # AMD.
    "3734d1f0e0405bfac407": [
        _frame("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 41.0),
        _frame("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 13.0),
    ],
    "a87bf61bdbcb0289c0b6": [
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 56.0),
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 3_100_000_000.0),
    ],
    "99f5f513843227599227": [_frame("GROSS_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 56.0)],
    # Amphastar Pharmaceuticals.
    "e82d1ee2d2d425d50f66": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 6_900_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 175_000_000.0),
    ],
    "d9c0a8d9a7549791c931": [_frame("REVENUE", "ABSOLUTE_VALUE", 183_900_000.0)],
    # Amplitude.
    "a21b24db596616f755e1": [
        _frame("REVENUE", "CHANGE_TO", 410_000_000.0, change=22.0),
        _frame("REVENUE", "CHANGE_BY", 75_000_000.0),
    ],
    "33ba1282e030ada9332d": [
        _frame("SHARES", "COMPARATIVE", 129_400_000.0),
        _frame("PRIOR_YEAR_SHARES", "COMPARATIVE", 140_200_000.0),
    ],
    # Amprius Technologies.
    "e7699daff350ea4b2a66": [_frame("ADJUSTED_EBITDA_GUIDANCE", "ABSOLUTE_VALUE", 4_000_000.0)],
    "a16d860e53b81c1b9df2": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 27.0),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 20.0),
    ],
    "72bf0a91b36e4cfefae5": [
        _frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 140_000_000.0),
        _frame("ADJUSTED_EBITDA_GUIDANCE", "ABSOLUTE_VALUE", 4_000_000.0),
    ],
    "4c4c4939146cf06a0e13": [_frame("REVENUE", "ABSOLUTE_VALUE", 34_000_000.0)],
    "a26d3ddf6dd459bb9c70": [
        _frame("CAPEX_GUIDANCE", "ABSOLUTE_VALUE", 10_000_000.0),
        _frame("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 136_900_000.0),
    ],
    "20283bfad9ce10a59baf": [_frame("REVENUE", "CHANGE_TO", 34_000_000.0, change=126.0)],
    # Alpha Metallurgical Resources.
    "08f56e4d49019c30411d": [_frame("SHARES", "ABSOLUTE_VALUE", 12_679_045.0)],
    "a50637115682049106da": [_frame("CASH", "ABSOLUTE_VALUE", 307_600_000.0)],
    "80fd9025d69080f24419": [_frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 25_600_000.0)],
    # Ameresco.
    "dafa6ae617a41d0ebe3e": [_frame("REVENUE", "CHANGE_TO", 515_500_000.0, change=9.0)],
}


TABLE_IDS = {
    "c617b5bcb03ca46965c6", "4261fcfb40de4326bbbf",  # AMAL
    "edabf30e047654a3168d",  # AMAN
    "3f0668c2e38d58566a74", "97aa07bade9c35e83ce0",  # AMBA
    "615d8ab749842c607608", "79397898e5490e5ccd27",  # AMBQ
    "79e8cc0854fa826f5f85",  # AMD
    "f7c65ab778b769b8d59d", "c9ed4752bcee742f0fe7", "672330ea11a5b8e0ab13", "62637898b691fd3c1137", "f410f24173ea1e0fc7fb",  # AMPH
    "1d1e9c2303e9199be01d", "0fc2f3cad831573523a2",  # AMPL
    "027fb223067179146775",  # AMPX
    "4f70daa8e0b39c38a5e0", "313fd191434cccbde157",  # AMR
    "aa17008a1ad8d38f25b3", "deffc1f985036d9e38fe", "0ae821a26ce1a0c8a955", "3ecaff88f1b3c8158858",  # AMRC
}


NOTES = {
    "d9c0a8d9a7549791c931": "press-release KPI headline is prose, not a numeric grid",
    "313fd191434cccbde157": "coal sales realization per ton is a positional period table",
    "0ae821a26ce1a0c8a955": "segment EBITDA rows are a table despite inherited prose routing",
    "3ecaff88f1b3c8158858": "fragment contains table headers and metric rows without prose assertions",
    "471089391aada7490ab8": "promissory-note borrowing is debt, not customer demand",
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
                "exhaustive manual thirtieth annotation before prediction",
            ),
        })
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.8.7 thirtieth holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown thirtieth candidate ids: {sorted(unknown)}")
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
