from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v267_tenth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v267_tenth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before any V2.6.7 prediction is run.
EXPECTED = {
    # General Dynamics
    "c65cfed5e82c0f9fa717": [
        _frame("ORDERS", "ABSOLUTE_VALUE", 14_700_000_000.0),
        _frame("ORDERS", "ABSOLUTE_VALUE", 5_300_000_000.0),
        _frame("ORDERS", "ABSOLUTE_VALUE", 20_000_000_000.0),
    ],
    "3be082ad38fc2d983f64": [
        _frame("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.4),
        _frame("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.5),
        _frame("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.4),
    ],
    "d520ff3d8eaf3295b23c": [
        _frame("REVENUE", "CHANGE_TO", 14_100_000_000.0, change=8.1),
    ],
    "bbd74121e4807d2e2eca": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 52_600_000_000.0),
    ],
    "3193c31e22c970b0e05a": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 234_000_000.0),
        _frame("DEBT", "CHANGE_BY", 498_000_000.0, polarity="NEGATIVE"),
    ],
    "e5a90ee2ade70c21b652": [
        _frame("BACKLOG", "ABSOLUTE_VALUE", 136_500_000_000.0),
    ],
    # Lockheed Martin
    "72b9d487f78c0f45ca51": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 115_000_000.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 24.0),
    ],
    "22c117c307834ddd9a33": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 1_600_000_000.0),
    ],
    "8a0e005b8583ae05693b": [
        _frame("REVENUE", "CHANGE_BY", 475_000_000.0),
        _frame("REVENUE", "CHANGE_BY", 360_000_000.0),
    ],
    "747d89dafe8761267f85": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 1_700_000_000.0),
    ],
    "3e39fc581626bde89926": [
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 8.0),
        _frame("OPERATING_INCOME_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 28.0),
    ],
    # Northrop Grumman
    "141380bbc6cced41de6d": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 97_000_000.0, polarity="NEGATIVE"),
        _frame("OPERATING_INCOME", "CHANGE_BY", 38.0, polarity="NEGATIVE"),
    ],
    "12e0fe0792de8189cb2f": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 61_000_000.0, polarity="NEGATIVE"),
        _frame("OPERATING_INCOME", "CHANGE_BY", 5.0, polarity="NEGATIVE"),
        _frame("OPERATING_INCOME", "CHANGE_BY", 97_000_000.0, polarity="NEGATIVE"),
        _frame("OPERATING_INCOME", "CHANGE_BY", 44_000_000.0, polarity="NEGATIVE"),
        _frame("OPERATING_INCOME", "CHANGE_BY", 60_000_000.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 41_000_000.0),
    ],
    "d138adad0462a5826209": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 60_000_000.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 14.0),
    ],
    # Norfolk Southern
    "eedc28cbd03d81dab76a": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 3_000_000_000.0),
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 937_000_000.0),
    ],
    "df394d81bd3397bd099b": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 4_400_000_000.0, change=7.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 285_000_000.0),
        _frame("OPERATING_INCOME", "CHANGE_TO", 4_300_000_000.0, change=3.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 122_000_000.0),
    ],
    "0fe3ddec3375599968a5": [
        _frame("REVENUE", "CHANGE_TO", 12_200_000_000.0, change=57_000_000.0),
        _frame("REVENUE", "CHANGE_BY", 134_000_000.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 1.0, polarity="NEGATIVE"),
    ],
    "782c996ecf675c18ef44": [
        _frame("REVENUE", "CHANGE_TO", 3_000_000_000.0, change=2.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 50_000_000.0, polarity="NEGATIVE"),
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 4.0, polarity="NEGATIVE"),
    ],
    "7e81fbc0fcda3250b500": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 1_000_000_000.0, change=3.0, polarity="NEGATIVE"),
        _frame("OPERATING_INCOME", "CHANGE_BY", 31_000_000.0, polarity="NEGATIVE"),
    ],
    "e2bbf85e9ac16bf8e968": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 937_000_000.0, change=17.0, polarity="NEGATIVE"),
        _frame("OPERATING_INCOME", "CHANGE_BY", 194_000_000.0, polarity="NEGATIVE"),
    ],
    # Wabtec
    "d9bdedf2e64fe4fd027e": [
        _frame("CASH", "ABSOLUTE_VALUE", 660_000_000.0),
    ],
    "1fecf6459557a2f096e7": [
        _frame("REVENUE", "CHANGE_BY", 17.7),
    ],
    "649238803c715b65ce8b": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            12_450_000_000.0,
            lower_value=12_300_000_000.0,
            upper_value=12_600_000_000.0,
        ),
        _frame("REVENUE_GUIDANCE", "CHANGE_BY", 110_000_000.0),
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 11.5),
    ],
    "483db585081e3c1b6fa3": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 18.9),
        _frame("OPERATING_MARGIN", "CHANGE_TO", 21.9, change=80.0),
    ],
    "aca0ff82e1427cad9b65": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 18.9),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 21.9),
    ],
    # Abbott
    "9443c78348701dbd159e": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 44_328_000_000.0),
    ],
    # Comcast
    "72be2f503e00bbd46eb3": [
        _frame("REVENUE", "CHANGE_BY", 440_000_000.0),
    ],
    # Gilead
    "0acacd2865fd5717a816": [
        _frame("REVENUE", "CHANGE_TO", 457_000_000.0, change=26.0),
    ],
    "234d14ff1b43db7d08d3": [
        _frame("CASH", "ABSOLUTE_VALUE", 3_200_000_000.0),
        _frame("CASH", "ABSOLUTE_VALUE", 10_600_000_000.0),
    ],
    "8283e15c0922b54fa88a": [
        _frame("REVENUE", "CHANGE_TO", 23_000_000.0, change=81.0, polarity="NEGATIVE"),
    ],
    # Thermo Fisher
    "d03b5b0bf5ca270995ae": [
        _frame("REVENUE", "CHANGE_TO", 11_990_000_000.0, change=10.0),
    ],
    "f28b00c41603da26a695": [
        _frame("OPERATING_MARGIN", "COMPARATIVE", 22.8),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 21.9),
    ],
    "efb915790dad65a5d3b9": [
        _frame("REVENUE", "CHANGE_BY", 5.0),
    ],
    # Verizon
    "4c0a5be6eab55eb0c010": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            2.75,
            lower_value=2.5,
            upper_value=3.0,
        ),
    ],
    "b9fd3b8d6120c1afd02a": [
        _frame("REVENUE", "CHANGE_TO", 34_300_000_000.0, change=0.7, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 20.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_BY", 1_200_000_000.0, polarity="NEGATIVE"),
    ],
    "a72220225e7edd40d0b3": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 138_200_000_000.0),
    ],
}


TABLE_IDS = {
    # Correctly detected tables/mixed blocks.
    "748324773e91ee30ec32",
    "b643b0809e5774d8282e",
    "3de15626098f46fb7f7b",
    "4116f420a3a202a3bbfe",
    "77e2a4043c3ba1a7e0dd",
    "b90028b3fa73bea21885",
    "592da23d2105945a239d",
    "aca92a72b84d3301fb6c",
    "a46487f6459d56444efd",
    "87a013dc724ec63dfbc6",
    "bb342c8452fbce9aec9f",
    "a46bee876363a2b71056",
    "866c1c103a339d038050",
    "d545c9bc00ffa130b0a7",
    "e4cd91d19e0fc06c8c45",
    "ca3f695688bc43981d0e",
    "303dfd74403db89bd9f4",
    "ca712b696fc55bd5dbd1",
    "7bae9bbdef6c6a1d0a60",
    # Flattened table fragments that V2.6.7 routed as prose.
    "b81a096d9f90abdbd0ca",
    "9b295879905afd2a7108",
    "cc486653900b89d4caf2",
    "8037f1cb80b10ab8d474",
    "f3c4c074696326ca1bdc",
    "28abe4166d0885bb367c",
    "88f32ac8759c5c62bd1c",
    "392e061199fcb01c9bbb",
    "cce645f0caf6367e7355",
}


NOTES = {
    "8a0e005b8583ae05693b": "a complete causal prose sentence despite V2.6.7 table routing",
    "d9bdedf2e64fe4fd027e": "cash balance is 0.66B; total liquidity and undrawn facilities are not cash",
    "117d3a7bc77f82e87484": "free cash flow is not a cash-balance fact",
    "a7c5e151563e0c0a1e61": "free cash flow is not a cash-balance fact",
    "26606725d698cd349989": "all numeric values belong to EPS, not revenue",
    "7568838e8391e3afb03e": "950M is a prior contract loss, not a revenue value",
    "a832ffdad26f47663aa7": "68M is an EAC cost adjustment, not production volume",
    "93cd6166669d121a651c": "150M is a divestiture benefit; backlog and guidance statements are qualitative",
    "1baf8fc43e9e4aeef419": "values are leverage ratios, not adjusted EBITDA levels",
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
                    "exhaustive manual tenth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.6.7 tenth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown tenth-holdout candidate ids: {sorted(unknown)}")
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
