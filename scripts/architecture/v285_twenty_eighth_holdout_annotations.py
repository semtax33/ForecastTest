from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v285_twenty_eighth_holdout_candidates import CANDIDATES


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v285_twenty_eighth_holdout_annotations.jsonl"


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


# Exhaustive manual labels frozen before the first V2.8.5 prediction. The
# financial role, not a surface token, decides the concept; cash-flow measures,
# dividends, transaction costs and ratios are not CASH balance facts.
EXPECTED = {
    # Adeia.
    "b31e8451f39ba6c587e7": [_frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 56_400_000.0)],
    "b4d4c3e1b43847de7f89": [
        _frame("REVENUE", "CHANGE_BY", 54.0),
        _frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 600_000_000.0),
        _frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 200_000_000.0),
    ],
    "76e51730ee8d65fa2608": [
        _frame("REVENUE", "COMPARATIVE", 96_100_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 104_800_000.0),
    ],
    "ab049d606ada9416a33b": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 96_000_000.0),
        _frame("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 59.0),
    ],
    # Adaptive Biotechnologies.
    "40142d0ff02536b1fc93": [_frame("REVENUE", "CHANGE_TO", 71_600_000.0, change=22.0)],
    "1011312e8982c6814f89": [_frame("REVENUE", "CHANGE_BY", 30.0)],
    "f8fc043c36842b0f822f": [_frame("ACTIVITY_VOLUME", "CHANGE_TO", 36_111.0, change=43.0)],
    "c9cf5c4592983d7a8ce4": [_frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 11_100_000.0, polarity="NEGATIVE")],
    # Aehr Test Systems.
    "6692c1ce19084dbdd000": [_frame("BACKLOG", "ABSOLUTE_VALUE", 100_000_000.0)],
    "2ac26f0a161a181536c5": [
        _frame("BACKLOG", "ABSOLUTE_VALUE", 100_600_000.0),
        _frame("CASH", "COMPARATIVE", 116_500_000.0),
        _frame("PRIOR_YEAR_CASH", "COMPARATIVE", 37_100_000.0),
    ],
    "d5ddab6915a58ac5f271": [
        _frame("BACKLOG", "ABSOLUTE_VALUE", 100_000_000.0),
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 140_000_000.0, lower_value=130_000_000.0, upper_value=150_000_000.0),
        _frame("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 180.0, lower_value=160.0, upper_value=200.0),
    ],
    # Atlas Energy Solutions.
    "0a31a4566fdf1637a817": [_frame("REVENUE", "CHANGE_TO", 27_000_000.0, change=54.3)],
    "977e09aa957a0e9c67a7": [_frame("REVENUE", "CHANGE_TO", 162_700_000.0, change=17.0)],
    "0240018a6db265cb84ca": [_frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 5_600_000.0)],
    "a94ac24ef2a929893e89": [_frame("REVENUE", "CHANGE_TO", 293_200_000.0, change=10.4)],
    "59e51a228c1642c1cc15": [_frame("REVENUE", "CHANGE_TO", 103_500_000.0, change=5.0, polarity="NEGATIVE")],
    # agilon health.
    "44e54f8ba810657817d2": [_frame("CASH", "ABSOLUTE_VALUE", 83_000_000.0)],
    # Agilysys.
    "237a3723f750795fd4a9": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 63.5),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 61.7),
    ],
    "4086eb44139ec4f95dab": [
        _frame("ADJUSTED_EBITDA", "COMPARATIVE", 18_300_000.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 12_500_000.0),
    ],
    "e04cf34bc2b8fabd5d29": [
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 32.0),
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 370_500_000.0, lower_value=368_000_000.0, upper_value=373_000_000.0),
    ],
    "27cf9335664fbe2c57aa": [
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 32.0),
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 370_500_000.0, lower_value=368_000_000.0, upper_value=373_000_000.0),
    ],
    "9c47d193dee0eda1ad7b": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 87_700_000.0),
        _frame("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 20.8),
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 32.0),
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 370_500_000.0, lower_value=368_000_000.0, upper_value=373_000_000.0),
    ],
    "3f4e9a3d79b5ed6611b5": [_frame("REVENUE", "CHANGE_TO", 87_700_000.0, change=14.3)],
    # AdaptHealth.
    "266c554193edebcb734e": [_frame("ADJUSTED_EBITDA", "CHANGE_TO", 132_000_000.0, change=3.2, polarity="NEGATIVE")],
    # C3.ai.
    "16858106bb8cf8ca5777": [_frame("REVENUE", "ABSOLUTE_VALUE", 250_300_000.0)],
    "821f79f07d3ad895583e": [_frame("CASH", "ABSOLUTE_VALUE", 673_000_000.0)],
    "27c8c22a58701b445a21": [_frame("REVENUE", "COMPOSITION", 91.0)],
    "c2414b1919a2104ddd77": [_frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 22.0)],
    "a5367839da7130d7901e": [_frame("REVENUE", "ABSOLUTE_VALUE", 227_100_000.0)],
    "4415eaf7dee88123e90b": [_frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 37.0)],
    # Applied Industrial Technologies.
    "920b7fa2c9b76d134e2b": [_frame("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 5.25, lower_value=4.0, upper_value=6.5)],
    "240eefae6a6179ab65dc": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 159_300_000.0),
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 177_600_000.0, change=16.1),
    ],
    "d754913af91a27491ab4": [_frame("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 5.25, lower_value=4.0, upper_value=6.5)],
    "1ac0a8c77e89934aca27": [_frame("REVENUE", "CHANGE_BY", 7.0)],
    "0933423b4740da1b03d6": [_frame("ADJUSTED_EBITDA_MARGIN", "CHANGE_BY", 60.0)],
    # Astera Labs.
    "e395086699374ae9366b": [_frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 39.1)],
    "e11f2dd231f950b47735": [_frame("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 185_000_000.0)],
    "96eaed297e2faf12e5b8": [_frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 73.7)],
    "1bd41be66eb9a8d0f8e9": [_frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 550_000_000.0, lower_value=540_000_000.0, upper_value=560_000_000.0)],
    "4582500c5780039b1456": [
        _frame("REVENUE", "CHANGE_TO", 392_400_000.0, change=27.0),
        _frame("REVENUE", "CHANGE_BY", 104.0),
    ],
    "ff6f52fc8452b5f51afd": [_frame("GROSS_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 72.0)],
}


TABLE_IDS = {
    "d65de0d1a84587603c55", "d522037c4167cff82e69", "480127da4c087887ff34",  # ADEA
    "7f2f5326eec1f658a7da",  # ADPT
    "b9a50d75d2fc1c576cd6",  # AEHR
    "bf69b575086358982428", "bfc281cfb6fb56db0eef",  # AESI
    "67eb1ec43d346e1a56e4", "a89103dd4ea7e21b7544", "5661292ac4147bed3d13", "05cadede159120e18857", "a11747c17b2d8ba87e34",  # AGL
    "32dbf17865f7efbdd59c", "13eb293ab24782338ef5",  # AGYS
    "0209f4d12912bf3b25a4", "22539175fb6cec679004",  # AHCO
    "f7a8b9cf894b1fff7fb0", "9210fa76a20d4e222902",  # AI
    "4eb4946f4ff5ef0e36ce", "3ca4efd29b9cfe3a574f", "eaa53d9ad33397b31de2", "80f2b162f1dfaa173708",  # AIT
    "c42dd4067c64077c8879",  # ALAB
}


NOTES = {
    "58603943de3ffd0c72ab": "cash from operations is not a cash balance",
    "faae04ace345227a8669": "cash dividend is not a cash balance",
    "bf69b575086358982428": "balance-sheet grid remains TABLE_DSL despite appended prose",
    "9c47d193dee0eda1ad7b": "press-release headline is prose despite compact numeric density",
    "32dbf17865f7efbdd59c": "reconciliation is a table despite a prose route prediction",
    "e11f2dd231f950b47735": "outlook sentence is text evidence, not a positional grid",
    "4582500c5780039b1456": "sequential and year-over-year growth are separate comparison facts",
}


def main() -> int:
    candidates = pd.read_csv(CANDIDATES)
    rows = []
    for item in candidates.itertuples(index=False):
        expected = EXPECTED.get(item.candidate_id, [])
        route = "TABLE_DSL" if item.candidate_id in TABLE_IDS else "TEXT_IE" if expected else "NO_FACT"
        rows.append({
            "candidate_id": item.candidate_id, "ticker": item.ticker, "gold_route": route,
            "expected_frames": expected,
            "annotation_note": NOTES.get(item.candidate_id, "exhaustive manual twenty-eighth annotation before prediction"),
        })
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.8.5 twenty-eighth holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twenty-eighth candidate ids: {sorted(unknown)}")
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    print(f"ANNOTATED={len(rows)} EXPECTED_FRAMES={sum(len(row['expected_frames']) for row in rows)} TABLE_BLOCKS={len(TABLE_IDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
