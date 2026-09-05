from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v284_twenty_seventh_b_holdout_candidates import CANDIDATES


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v284_twenty_seventh_b_holdout_annotations.jsonl"


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


# Exhaustive manual labels fixed before the first V2.8.4 prediction. Ambiguous
# presentation fragments are not converted into facts; explicit economic roles
# are labelled even when the surface candidate used a different accounting noun.
EXPECTED = {
    # Applied Digital / defense portfolio release.
    "467cfe7c7bada7215673": [_frame("REVENUE", "CHANGE_TO", 167_300_000.0, change=47.4)],
    "9c9ce25f1b32fda7ead3": [_frame("REVENUE", "CHANGE_BY", 35_900_000.0)],
    # ABM Industries.
    "42f5845cbc334bbad1c9": [
        _frame("OPERATING_MARGIN", "COMPARATIVE", 7.3),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 7.9),
    ],
    "e9a6a1e97fce500e744e": [
        _frame("REVENUE", "CHANGE_TO", 2_300_000_000.0, change=8.4),
        _frame("REVENUE", "CHANGE_BY", 6.1),
        _frame("REVENUE", "CHANGE_BY", 2.3),
    ],
    "00509bce97e771a7697d": [
        _frame("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 3.5, lower_value=3.0, upper_value=4.0),
        _frame("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 4.5, lower_value=4.0, upper_value=5.0),
    ],
    # Arcosa.
    "ae4f17c2e5224770f403": [_frame("DEBT", "CHANGE_BY", 83_000_000.0, polarity="NEGATIVE")],
    "cdb58042ac1c3e8b5ec7": [
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 61_400_000.0, change=13.0),
        _frame("ADJUSTED_EBITDA_MARGIN", "CHANGE_TO", 20.4, change=180.0),
    ],
    "ed0bd676dc2ab5434b15": [
        _frame("ADJUSTED_EBITDA_MARGIN", "COMPARATIVE", 30.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA_MARGIN", "COMPARATIVE", 31.0),
    ],
    "c4226b77f5599f2bdcd6": [_frame("BACKLOG", "CHANGE_TO", 648_100_000.0, change=49.0)],
    # Acadia Pharmaceuticals.
    "ec804a1e92c83c52fbe1": [_frame("REVENUE", "CHANGE_TO", 125_000_000.0, change=30.0)],
    "69126c4fd5bbe8d01f9e": [
        _frame("REVENUE", "COMPARATIVE", 183_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 168_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 166_000_000.0),
    ],
    "2ee27e905e47400f78ed": [
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 495_000_000.0, lower_value=480_000_000.0, upper_value=510_000_000.0),
    ],
    "6e4c5d496934eff711b3": [_frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 1_700_000_000.0)],
    "03745177d1e226154c07": [
        _frame("REVENUE", "COMPARATIVE", 308_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 265_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 262_000_000.0),
    ],
    # Axcelis.
    "06e73600c96df13c67ee": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 215_200_000.0),
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 42.4),
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 42.7),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 9.4),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 14.7),
    ],
    # ACM Research.
    "4a1dd947645646368529": [_frame("ORDERS", "CHANGE_BY", 105.0)],
    "80d0b50b01a5d21f573d": [
        _frame("GROSS_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 45.0, lower_value=42.0, upper_value=48.0),
    ],
    # Ascent Industries.
    "f0ce31eef0a851a35f5f": [_frame("REVENUE", "CHANGE_BY", 7_000_000.0)],
    "4c1936c810a7c44f6f61": [_frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 100.0)],
    "71ba77f0e057000bcf31": [
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 77_500_000.0, lower_value=5_000_000.0, upper_value=150_000_000.0),
        _frame("ADJUSTED_EBITDA_GUIDANCE", "RANGE_GUIDANCE", 12_500_000.0, lower_value=0.0, upper_value=25_000_000.0),
    ],
    "bcd6143d3b5b6528299b": [_frame("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 14.0)],
    # ADT incremental borrowing.
    "295146576535e0f047b0": [_frame("DEBT", "CHANGE_BY", 100_000_000.0)],
}


TABLE_IDS = {
    "61ab334f1e723d2e7c54",  # AADX statement grid
    "1df92154501386a952c0",  # ABM statements and cash flow grid
    "70696041315fb7162efc",  # ACA leverage table
    "57b38459824fdd5c0aca", "d034fc1a326aeed37162",  # ACAD statements
    "e1251c1418a3a0cb24ab", "6be98ead5a60fdc08b96", "fd2a2980d01d95247b16", "26372dedba6750a1f113",  # ACLS
    "ae86b5c5b523ca949f1f",  # ACNT reconciliation
    "d8ce5835ff6e1ca7324c", "1cd57479c7414dc25511", "b38247de906b44204abf", "71997e694695ef7b5b16", "1cd45043f5c9ed65a5da",  # ACT supplement
    "f29304416b79d44c4995", "c36f44729d3533bb90dc",  # ADT
    "3692d80d651d2bb704c6", "5d904a1b0d1d2b97099b", "7ed6cce9880c97beb289",  # ADTN
}


NOTES = {
    "ae4f17c2e5224770f403": "cash proceeds used to prepay a term loan are a debt reduction, not a cash balance",
    "cdb58042ac1c3e8b5ec7": "narrative EBITDA highlight, not a positional table",
    "59cfeaa602fb50053b74": "all-cash transaction price per share is not a cash balance",
    "e9a6a1e97fce500e744e": "reported, organic, and acquisition growth are distinct revenue facts",
    "71ba77f0e057000bcf31": "target dollar ranges are forward guidance",
    "51e1edb04006c875f58e": "layout-damaged fragment is too ambiguous for automatic binding",
    "295146576535e0f047b0": "incremental borrowing is a positive debt change",
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
            "annotation_note": NOTES.get(item.candidate_id, "exhaustive manual twenty-seventh-B annotation before prediction"),
        })
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.8.4 twenty-seventh-B holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twenty-seventh-B candidate ids: {sorted(unknown)}")
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    print(f"ANNOTATED={len(rows)} EXPECTED_FRAMES={sum(len(row['expected_frames']) for row in rows)} TABLE_BLOCKS={len(TABLE_IDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
