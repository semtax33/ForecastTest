from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v282_twenty_fifth_c_holdout_candidates import CANDIDATES


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v282_twenty_fifth_c_holdout_annotations.jsonl"


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


# Exhaustive labels prepared before the first V2.8.2 prediction. Segment
# comparable operating earnings is operating income economically; cash flow,
# FFO, EPS, combined investments, and expense ratios are not retyped as CASH or
# REVENUE merely because those words occur in their descriptions.
EXPECTED = {
    # Asbury Automotive.
    "dedc7f3d51c1c5d8f911": [_frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 17.2)],
    "ade4394d068f4d618cdf": [_frame("REVENUE", "ABSOLUTE_VALUE", 2_000_000_000.0)],
    "1a0e63f046f86b370dc4": [_frame("REVENUE", "ABSOLUTE_VALUE", 1_100_000_000.0)],
    "253c0815da5e6b7c523b": [_frame("REVENUE", "ABSOLUTE_VALUE", 2_300_000_000.0)],
    # Albertsons.
    "1c48abe5d0693ff75f11": [_frame("REVENUE", "CHANGE_BY", 13.0)],
    "700fd82cfc2a5e97b931": [
        _frame("ADJUSTED_EBITDA_GUIDANCE", "RANGE_GUIDANCE", 3_587_500_000.0, lower_value=3_550_000_000.0, upper_value=3_625_000_000.0),
    ],
    "81992130d12042854c0c": [
        _frame("ADJUSTED_EBITDA", "COMPARATIVE", 1_013_200_000.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 1_111_000_000.0),
        _frame("ADJUSTED_EBITDA_MARGIN", "COMPARATIVE", 4.1),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA_MARGIN", "COMPARATIVE", 4.5),
    ],
    "26a3cd4f5a1e85569ba2": [_frame("REVENUE", "CHANGE_BY", 13.0)],
    "4059a146914c7bb63c22": [_frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 1_013_000_000.0)],
    # ADMA Biologics.
    "87fb6e335ace40bb4c4a": [
        _frame("ADJUSTED_EBITDA_GUIDANCE", "RANGE_GUIDANCE", 282_500_000.0, lower_value=265_000_000.0, upper_value=300_000_000.0),
    ],
    "fedcb6b3fea4ec290ab8": [_frame("ADJUSTED_EBITDA", "CHANGE_TO", 61_800_000.0, change=22.0)],
    "e3c8df3b57a91f6f79ea": [
        _frame("REVENUE", "CHANGE_TO", 200_400_000.0, change=26.0),
        _frame("REVENUE", "CHANGE_TO", 34_800_000.0, change=51.0, polarity="NEGATIVE"),
    ],
    "6f6ee819895e1d1439d5": [
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 545_000_000.0, lower_value=530_000_000.0, upper_value=560_000_000.0),
    ],
    # Amkor.
    "9d06c30c31017ba99a03": [
        _frame("CASH", "ABSOLUTE_VALUE", 2_500_000_000.0),
        _frame("DEBT", "ABSOLUTE_VALUE", 2_500_000_000.0),
    ],
    "d45784cda07da8dffbaf": [
        _frame("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 2_000_000_000.0, lower_value=1_950_000_000.0, upper_value=2_050_000_000.0),
    ],
    "5f1c6e80781993aa0711": [
        _frame("CAPEX_GUIDANCE", "RANGE_GUIDANCE", 2_750_000_000.0, lower_value=2_500_000_000.0, upper_value=3_000_000_000.0),
    ],
    "e08b6b83b25696e76cea": [
        _frame("GROSS_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 19.0, lower_value=18.5, upper_value=19.5),
    ],
    # Ball.
    "c95a0eac5e347ba8d425": [
        _frame("OPERATING_INCOME", "COMPARATIVE", 162_000_000.0),
        _frame("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 152_000_000.0),
        _frame("REVENUE", "COMPARATIVE", 1_240_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 1_120_000_000.0),
    ],
    # Best Buy.
    "7cc27b14c1f32bb8ebf3": [
        _frame("REVENUE", "CHANGE_BY", 4.1),
        _frame("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 2.45, lower_value=1.9, upper_value=3.0),
    ],
    "21aca07c65186c83ff0d": [
        _frame("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 2.45, lower_value=1.9, upper_value=3.0),
    ],
    "a3e5911f407029f63b68": [
        _frame("CAPEX_GUIDANCE", "ABSOLUTE_VALUE", 750_000_000.0),
        _frame("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 2.0, lower_value=1.0, upper_value=3.0),
        _frame("OPERATING_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 4.15, lower_value=4.1, upper_value=4.2),
    ],
    "43ea72c390c430388033": [_frame("REVENUE", "CHANGE_TO", 709_000_000.0, change=4.2, polarity="NEGATIVE")],
    # Franklin Resources.
    "4a6abff3037124f57f37": [
        _frame("OPERATING_INCOME", "COMPARATIVE", 215_800_000.0),
        _frame("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 323_300_000.0),
        _frame("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 154_100_000.0),
    ],
    # Brown & Brown.
    "47215e326c457d30f921": [
        _frame("REVENUE", "CHANGE_TO", 1_700_000_000.0, change=30.4),
        _frame("REVENUE", "CHANGE_BY", 391_000_000.0),
        _frame("REVENUE", "CHANGE_BY", 0.7, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 0.7),
    ],
    # Carrier.
    "0538eecc6d4b649cf659": [_frame("OPERATING_MARGIN", "CHANGE_BY", 350.0, polarity="NEGATIVE")],
    "564f489f495695d2ed04": [_frame("REVENUE", "CHANGE_BY", 3.0)],
    "e3a43e3ec8ac4babba78": [_frame("REVENUE", "CHANGE_BY", 4.0)],
}


TABLE_IDS = {
    "7ef6c6298e26bae0e3bf",
    "8cfc92cff7a454960432",
    "ec50387293fd1be403fd",
    "853b8f4e80c336eb0f93",
    "3982d15ca74c32fe42e6",
    "319ce7ce783f13be49d2",
    "f13f31b4d462fe36af85",
    "19e1673d1259165375df",
    "191bf6d1f133c228c2a6",
    "90d96914706512cfe537",
    "431b0af6ea0bd8f7af58",
    "a2ea3a18ee4163dd0728",
    "affa62637070087cfbf1",
    "407ab6d989b4122b8f06",
    "a2b352c7107d87268bc7",
    "6104e585c197464d8a6a",
    "64979a50226572aa6990",
    "062d24a741595c8b17d9",
    "8cb01f71f84ff2c77b59",
}


NOTES = {
    "9b1c0fc4069b3392e6ec": "non-cash asset impairments are not a cash-balance fact",
    "98151f24a213e2b84f0f": "expense as a percentage of revenue is not revenue growth",
    "99089a9279a338b381a1": "unadjusted EBITDA is outside the current adjusted-EBITDA ontology",
    "c95a0eac5e347ba8d425": "comparable operating earnings is operating income economically",
    "7cc27b14c1f32bb8ebf3": "headline numeric prose is not a flattened table",
    "f5409bd61630f2ab061a": "cash and investments related to deferred compensation is not cash balance",
    "564f489f495695d2ed04": "press-release lead with organic sales growth is prose despite table-like route",
}


def main() -> int:
    candidates = pd.read_csv(CANDIDATES)
    rows = []
    for item in candidates.itertuples(index=False):
        expected = EXPECTED.get(item.candidate_id, [])
        route = "TABLE_DSL" if item.candidate_id in TABLE_IDS else "TEXT_IE" if expected else "NO_FACT"
        rows.append(
            {
                "candidate_id": item.candidate_id,
                "ticker": item.ticker,
                "gold_route": route,
                "expected_frames": expected,
                "annotation_note": NOTES.get(item.candidate_id, "exhaustive manual twenty-fifth-C annotation before prediction"),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.8.2 twenty-fifth-C holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twenty-fifth-C candidate ids: {sorted(unknown)}")
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    print(f"ANNOTATED={len(rows)} EXPECTED_FRAMES={sum(len(row['expected_frames']) for row in rows)} TABLE_BLOCKS={len(TABLE_IDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
