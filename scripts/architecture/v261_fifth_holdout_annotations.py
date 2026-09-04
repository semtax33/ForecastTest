from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v261_fifth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v261_fifth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# This label set was written without inspecting V2.6.1 predictions.  It is
# deliberately exhaustive only for company KPI facts expressible by the
# platform's semantic-frame contract.  Definitions, disclaimers, industry
# forecasts and non-company market statistics remain NO_FACT.
EXPECTED = {
    "a411769cd6f1b8bcde57": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            5.5,
            lower_value=5.0,
            upper_value=6.0,
        )
    ],
    "15c60be3584b003267c7": [
        _frame("REVENUE", "CHANGE_TO", 21_900_000_000, change=7.0),
        _frame("REVENUE", "CHANGE_BY", 6.0),
    ],
    "c03b9bd94a30ca0fdeb9": [
        _frame("OPERATING_MARGIN", "CHANGE_BY", 90.0),
        _frame("OPERATING_MARGIN", "CHANGE_BY", 60.0),
    ],
    "a3622d4d9561ff81223b": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            4.0,
            lower_value=3.0,
            upper_value=5.0,
        )
    ],
    "786d563bb054ca19fe07": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            5.5,
            lower_value=5.0,
            upper_value=6.0,
        ),
        _frame(
            "OPERATING_MARGIN_GUIDANCE",
            "RANGE_GUIDANCE",
            80.0,
            lower_value=70.0,
            upper_value=90.0,
        ),
    ],
    "884efffbaf6d74eedb2d": [
        _frame("EBIT", "CHANGE_TO", 5_900_000_000, change=10.0),
        _frame("OPERATING_MARGIN", "CHANGE_TO", 26.8, change=80.0),
    ],
    "cb57681b4a0eb7ab5d73": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            5.5,
            lower_value=5.0,
            upper_value=6.0,
        )
    ],
    "c47b17a01206826725f6": [
        _frame("OPERATING_MARGIN", "CHANGE_BY", 81.0, polarity="NEGATIVE")
    ],
    "829a3121c3997e449082": [
        _frame("GROSS_MARGIN", "CHANGE_BY", 77.0, polarity="NEGATIVE")
    ],
    "3934146fc76d0c46d30c": [
        _frame("REVENUE", "CHANGE_BY", 563_000_000, polarity="NEGATIVE")
    ],
    "c79478ad30aede24ab87": [
        _frame("REVENUE", "CHANGE_BY", 1_125_000_000, polarity="NEGATIVE")
    ],
    "358358090ac7f54823c2": [
        _frame("CASH", "CHANGE_BY", 250_000_000, polarity="NEGATIVE")
    ],
    "8ab577fd52e06b35e60d": [
        _frame("REVENUE", "CHANGE_BY", 129_000_000)
    ],
    "5db4922c86fe78451a79": [
        _frame("REVENUE", "COMPARATIVE", 1_090_000_000),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 1_080_000_000),
    ],
    "b7a31b6ddb3b26bff681": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 138_700_000)
    ],
    "b9f5d515a9ecac8b98ab": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 14_320_000_000)
    ],
    "a431cbf5cd5d4209808a": [
        _frame("REVENUE", "COMPARATIVE", 14_320_000_000),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 14_950_000_000),
    ],
    "92ae183886ca3cf416d4": [
        _frame("REVENUE", "COMPARATIVE", 549_700_000),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 547_700_000),
    ],
    "1328efe56d0e5f162b97": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 7_550_000_000)
    ],
    "c8a52fbd74b0fe4580c5": [
        _frame("DELIVERIES", "ABSOLUTE_VALUE", 38_700)
    ],
    "7b17db9a8c7bce8e543e": [
        _frame("REVENUE", "CHANGE_TO", 15_000_000_000, change=3.0)
    ],
    "367e28647b7b950e70eb": [
        _frame("REVENUE", "CHANGE_BY", 5.0)
    ],
    "c66ae0c5a89ec5db5033": [
        _frame("REVENUE", "CHANGE_BY", 19.0)
    ],
    "b6a8d2ad54ca42deb100": [
        _frame("REVENUE", "CHANGE_BY", 95.0, polarity="NEGATIVE")
    ],
    "8c62d59d689275e5d110": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 9_900_000_000),
        _frame("REVENUE_GUIDANCE", "CHANGE_TO", 40_000_000_000),
    ],
    "79867939407c17eb7a90": [
        _frame("REVENUE", "CHANGE_BY", 13.0),
        _frame("REVENUE", "CHANGE_BY", 23.0),
    ],
    "c439e002246198aad4a2": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            5_900_000_000,
            lower_value=5_650_000_000,
            upper_value=6_150_000_000,
        )
    ],
    "da4d021129f59ce1d627": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 3_300_000_000)
    ],
    "85ec7e4d7076555b32b4": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 5_460_000_000)
    ],
}


TABLE_IDS = {
    "3e7a0e39f726f6e01f40",
    "114863224f82c4e0d29f",
    "0f1456040713c182d53d",
    "34c554015939397c72c3",
    "80d2953138c9890f098f",
    "5b2ad433c49fc70bd724",
    "2086f79ea2223c1ed30f",
    "2bcc83f50fe8cb0d081d",
    "ca9d0f2f38208ef02a32",
    "81581765bdff639fe708",
    "57f5a1a4e3d705ef263f",
    "79aecde8abd314414f6e",
    "c8415c532e81fbef8ed9",
    "e4b6c24a9b65860f7a65",
    "4665a0965404fbfc61ba",
    "55140e5324025f467a14",
    "fe9c38dc2622cec6efb4",
    "152b6630366e37d26fa0",
    "17900ab7de5bff86ef54",
}


NOTES = {
    "786d563bb054ca19fe07": "adjusted EBIT margin maps to operating-margin economics; exposes ontology coverage",
    "884efffbaf6d74eedb2d": "one clause contains EBIT level and EBIT-margin level/delta",
    "358358090ac7f54823c2": "conditional transaction cash reduction is a forecast change, not a current cash balance",
    "98b9fd2f1c019065016b": "industry truck sales forecast is context, not a company KPI fact",
    "8c62d59d689275e5d110": "press-release lead is text despite dense headline quantities",
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
                    "exhaustive manual fifth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.6.1 fifth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown fifth-holdout candidate ids: {sorted(unknown)}")
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
