from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v278_twenty_first_b_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v278_twenty_first_b_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive, model-independent labels frozen before the first V2.7.8
# prediction on this issuer- and document-disjoint holdout.  Labels retain
# multiple reported/operational rates and distinct economic bridge components
# even when they share a financial concept and level.
EXPECTED = {
    # AbbVie.
    "23273784873c2a3678a3": [
        _frame("REVENUE", "CHANGE_TO", 1_282_000_000.0, change=0.3),
        _frame("REVENUE", "CHANGE_TO", 1_282_000_000.0, change=0.9, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_TO", 728_000_000.0, change=5.2),
        _frame("REVENUE", "CHANGE_TO", 728_000_000.0, change=3.4),
        _frame("REVENUE", "CHANGE_TO", 245_000_000.0, change=6.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_TO", 245_000_000.0, change=6.6, polarity="NEGATIVE"),
    ],
    "2571491f473560d6b2af": [
        _frame("REVENUE", "CHANGE_TO", 8_786_000_000.0, change=15.1),
        _frame("REVENUE", "CHANGE_TO", 8_786_000_000.0, change=14.6),
        _frame("REVENUE", "ABSOLUTE_VALUE", 5_505_000_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 2_525_000_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 756_000_000.0),
    ],
    "2cb595121e2bc0a1c200": [
        _frame("REVENUE", "CHANGE_TO", 3_228_000_000.0, change=20.3),
        _frame("REVENUE", "CHANGE_TO", 3_228_000_000.0, change=19.8),
        _frame("REVENUE", "ABSOLUTE_VALUE", 1_071_000_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 1_042_000_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 742_000_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 256_000_000.0),
    ],
    "983fda115bdda6907686": [
        _frame("REVENUE", "CHANGE_TO", 1_650_000_000.0, change=1.5, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_TO", 1_650_000_000.0, change=2.4, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_TO", 771_000_000.0, change=11.6),
        _frame("REVENUE", "CHANGE_TO", 771_000_000.0, change=9.6),
        _frame("REVENUE", "CHANGE_TO", 532_000_000.0, change=29.4, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_TO", 211_000_000.0, change=33.1),
        _frame("REVENUE", "CHANGE_TO", 211_000_000.0, change=31.8),
    ],
    # Dell.
    "05d14ce5f6a365044aac": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            167_000_000_000.0,
            lower_value=165_000_000_000.0,
            upper_value=169_000_000_000.0,
        ),
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 47.0),
    ],
    "07a6cb4f9a324202125d": [
        _frame("REVENUE", "CHANGE_TO", 8_500_000_000.0, change=92.0),
    ],
    "6421f65e25c0ae5522e6": [
        _frame("ORDERS", "ABSOLUTE_VALUE", 24_400_000_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 16_100_000_000.0),
    ],
    "fc3aa34f2f4adc5eab5c": [
        _frame("REVENUE", "CHANGE_TO", 29_000_000_000.0, change=181.0),
    ],
    # General Mills.
    "1139a30352cb5fa6f6b1": [
        _frame("REVENUE", "CHANGE_TO", 4_600_000_000.0, change=1.0),
        _frame("REVENUE", "CHANGE_BY", 7.0),
        _frame("REVENUE", "CHANGE_BY", 1.0),
        _frame("REVENUE", "CHANGE_BY", 7.0, polarity="NEGATIVE"),
    ],
    "2b8f6f6bbfc78f691b21": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 886_000_000.0, change=73.0, polarity="NEGATIVE"),
    ],
    "96347815411530766247": [
        _frame("GROSS_MARGIN", "CHANGE_TO", 33.6, change=100.0, polarity="NEGATIVE"),
        _frame("GROSS_MARGIN", "CHANGE_TO", 33.5, change=100.0, polarity="NEGATIVE"),
    ],
    "dd55751293b9acfd239a": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 15.3, change=160.0),
    ],
    "ff01fef3fb50775125df": [
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 2.0, polarity="NEGATIVE"),
    ],
    # Keurig Dr Pepper.
    "af91754fec310c0e772d": [
        _frame("REVENUE", "CHANGE_BY", 7.3),
        _frame("PRICE_REALIZATION", "CHANGE_BY", 4.2),
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 3.1),
    ],
    # Molina Healthcare.
    "306686bb5c12838cf3b6": [
        _frame("REVENUE", "CHANGE_TO", 10_200_000_000.0, change=6.0, polarity="NEGATIVE"),
    ],
    "4a4ee2bfbcc4e614bd0b": [
        _frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 42_000_000_000.0),
    ],
    "5001587071a335e58830": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 10_200_000_000.0),
    ],
    "9bc48b29929012e4dd51": [
        _frame("CASH", "COMPARATIVE", 290_000_000.0),
        _frame("PRIOR_YEAR_CASH", "COMPARATIVE", 223_000_000.0),
    ],
    # Nike.
    "0e5d1c3b73a1aebd43bd": [
        _frame("GROSS_MARGIN", "CHANGE_TO", 49.2, change=890.0),
        _frame("GROSS_MARGIN", "CHANGE_BY", 900.0),
    ],
    "93796f76e520713781e3": [
        _frame("GROSS_MARGIN", "CHANGE_BY", 900.0),
    ],
    "9c86d6f4d79f57c2b73b": [
        _frame("CASH", "CHANGE_TO", 9_000_000_000.0, change=100_000_000.0, polarity="NEGATIVE"),
    ],
    # Starbucks.
    "57482f91451dfa9a84f5": [
        _frame("OPERATING_MARGIN", "COMPARATIVE", 19.1),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 13.6),
    ],
    "8072df8a8949c3e8132a": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 10.5, change=60.0),
        _frame("OPERATING_MARGIN", "CHANGE_TO", 14.4, change=430.0),
    ],
    # SLB.
    "6aa6dbac59c6aa30ef2f": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 16.0, change=138.0),
    ],
}


TABLE_IDS = {
    # AbbVie.
    "4f69cea36a5ea4cbef9f",
    "aa0534e50869c1a09b26",
    "ac1dc5689ba6f72b3399",
    # Dell.
    "156d16f1ae73e44d5445",
    "66f3e9b7975db3686bc2",
    "c2e91cebbf9e510c2739",
    "db1c208fd23b6594f346",
    # FedEx.
    "2ad14f93030060a822b4",
    "32702679499b2271a3fc",
    "3a149a7f1c9eb2948a56",
    "4316774b783be8183c81",
    "483ec5fbfedc2c9e8c21",
    "be9610bc7fd2ccce61fe",
    # General Mills.
    "6781a1b2ce29d18f181f",
    # Keurig Dr Pepper.
    "077632c5b57736bd1afd",
    "d20bb47c3a1057562735",
    # Molina Healthcare.
    "e3dab1c1a3054ef87556",
    # Nike, PepsiCo, Starbucks, and SLB.
    "1de29ddfa1b32aa81429",
    "4d9ac570d10044d734e5",
    "30c19c036430d95de42c",
    "7639ce6dcdba89277d61",
    "06e0f079e0cc52723ff0",
}


NOTES = {
    "aa0534e50869c1a09b26": "GAAP-to-adjusted multi-column reconciliation is table evidence despite prose route",
    "db1c208fd23b6594f346": "segment-to-consolidated reconciliation is table evidence despite prose route",
    "4316774b783be8183c81": "truncated row fragment retains aligned comparative table cells",
    "4e0c6a1f26e5c4161ba7": "dividend decline is not a shares observation",
    "7efcf84eeca22772cd5a": "cash restructuring charge is not a cash-balance observation",
    "6789d5a6911e73b1e39f": "shareholder distributions are not a cash-balance observation",
    "192d67a74296b769388a": "greater-than margin guidance is inequality-only and remains fail-closed",
    "d74e9ba4a61c550f767d": "operating cash flow is outside the cash-balance ontology",
    "daa934a2932aa6ca7bd3": "medical-cost ratio is not price realization",
    "93796f76e520713781e3": "tariff recovery amount is a driver; only the explicit margin effect is labeled",
    "1520c3c749862d74294b": "demand-creation expense is not customer-demand evidence",
    "9c86d6f4d79f57c2b73b": "cash and short-term investments form the disclosed liquidity level",
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
                    "exhaustive manual twenty-first-B holdout annotation before prediction",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.8 twenty-first-B holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twenty-first-B candidate ids: {sorted(unknown)}")
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
