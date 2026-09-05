from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v272_fifteenth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v272_fifteenth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the first V2.7.2 prediction on the
# issuer- and document-disjoint fifteenth holdout.  ARR and free cash flow are
# not weakened into GAAP revenue or issuer-cash facts.  Tables are routing-only.
EXPECTED = {
    # Adobe
    "88a472e0a985b95f8fb0": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 6_620_000_000.0),
    ],
    "2dc10a6564f1f173f96b": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 2_240_000_000.0),
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 2_950_000_000.0),
    ],
    "eb55ed943eada5b02de2": [
        _frame("REVENUE", "CHANGE_TO", 1_850_000_000.0, change=16.0),
        _frame("REVENUE", "CHANGE_BY", 15.0),
    ],
    "2069511ae238b6df059b": [
        _frame("REVENUE", "CHANGE_TO", 4_540_000_000.0, change=13.0),
        _frame("REVENUE", "CHANGE_BY", 11.0),
    ],
    # Axon
    "5fe937091f538db41c46": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 47_000_000.0, change=48_000_000.0),
    ],
    "417efdf212e4d7f85fe4": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 53.4),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 51.1),
    ],
    "154d6e80b020a86c6336": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 75.1),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 78.9),
    ],
    "a22334fffcb74ba235f6": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            33.0,
            lower_value=32.0,
            upper_value=34.0,
        ),
    ],
    "a1d420b8325863c841e8": [
        _frame("REVENUE", "CHANGE_TO", 398_000_000.0, change=36.0),
    ],
    # CrowdStrike
    "74bd43a493e0a3f0bfb0": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 78.0),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 77.0),
    ],
    # Fortinet
    "d7120e55d9ddd3b88025": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            2_055_000_000.0,
            lower_value=2_010_000_000.0,
            upper_value=2_100_000_000.0,
        ),
    ],
    "de8b910dea581304941e": [
        _frame("REVENUE", "CHANGE_TO", 773_000_000.0, change=52.0),
    ],
    "ea44988a96754c2ddb35": [
        _frame(
            "GROSS_MARGIN_GUIDANCE",
            "RANGE_GUIDANCE",
            80.0,
            lower_value=79.0,
            upper_value=81.0,
        ),
    ],
    "0fe80004d59eca89b708": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            5_200_000_000.0,
            lower_value=5_180_000_000.0,
            upper_value=5_220_000_000.0,
        ),
    ],
    # Home Depot
    "44b122964c625f1c63ef": [
        _frame(
            "OPERATING_MARGIN_GUIDANCE",
            "RANGE_GUIDANCE",
            12.5,
            lower_value=12.4,
            upper_value=12.6,
        ),
    ],
    # Microsoft
    "1f9de96f7c682e33fddc": [
        _frame("REVENUE", "CHANGE_TO", 90_000_000_000.0, change=18.0),
        _frame("REVENUE", "CHANGE_BY", 17.0),
    ],
    "e2ad10051f16c032f74e": [
        _frame("REVENUE", "CHANGE_BY", 13.0),
        _frame("REVENUE", "CHANGE_BY", 12.0),
        _frame("REVENUE", "CHANGE_TO", 39_300_000_000.0, change=32.0),
        _frame("REVENUE", "CHANGE_BY", 31.0),
    ],
    "c696485786385a73eecd": [
        _frame("REVENUE", "CHANGE_BY", 10.0, polarity="NEGATIVE"),
    ],
    "d7705584ce6872705c9c": [
        _frame("REVENUE", "CHANGE_BY", 7.0, polarity="NEGATIVE"),
    ],
    "e5aa94b95478ddaea73d": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 40_600_000_000.0, change=18.0),
    ],
    "5eaf62e3f8d3137c55b4": [
        _frame("REVENUE", "CHANGE_BY", 24.0),
        _frame("REVENUE", "CHANGE_BY", 22.0),
    ],
    "19ee03c5c68397fd6088": [
        _frame("REVENUE", "CHANGE_BY", 14.0),
    ],
    # Oracle
    "6bf31479a804e28003b2": [
        _frame("REVENUE", "CHANGE_TO", 67_400_000_000.0, change=17.0),
        _frame("REVENUE", "CHANGE_BY", 16.0),
    ],
    "0e606eb7f80b9df8d56d": [
        _frame("REVENUE", "CHANGE_TO", 19_200_000_000.0, change=21.0),
    ],
    "08ac70946a6b2ce71c5d": [
        _frame("REVENUE", "CHANGE_TO", 9_900_000_000.0, change=47.0),
        _frame("REVENUE", "CHANGE_BY", 46.0),
        _frame("REVENUE", "CHANGE_TO", 5_800_000_000.0, change=93.0),
        _frame("REVENUE", "CHANGE_BY", 92.0),
        _frame("REVENUE", "CHANGE_TO", 4_100_000_000.0, change=10.0),
        _frame("REVENUE", "CHANGE_BY", 9.0),
    ],
    "14d367f67a1dc549f617": [
        _frame("REVENUE", "CHANGE_TO", 1_500_000_000.0, change=13.0),
        _frame("REVENUE", "CHANGE_TO", 900_000_000.0, change=9.0),
    ],
    "96d16d9238ed72befde9": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 20_600_000_000.0, change=17.0),
        _frame("OPERATING_INCOME", "CHANGE_TO", 28_900_000_000.0, change=16.0),
    ],
    "fe962d67304653da08bc": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            28.0,
            lower_value=27.0,
            upper_value=29.0,
        ),
    ],
    # PayPal
    "f0d6122b1cd97b2f4865": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 1_400_000_000.0, change=5.0, polarity="NEGATIVE"),
        _frame("OPERATING_INCOME", "CHANGE_TO", 1_500_000_000.0, change=8.0, polarity="NEGATIVE"),
    ],
    "b07508267138ca24489f": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 16.4, change=171.0, polarity="NEGATIVE"),
        _frame("OPERATING_MARGIN", "CHANGE_TO", 17.4, change=248.0, polarity="NEGATIVE"),
    ],
    # UnitedHealth Group
    "4e5e8e1abcfafcd94e07": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 112_000_000_000.0),
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 8_000_000_000.0),
    ],
    "050341cff714ffd212ab": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 1_200_000_000.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 5.1),
    ],
    "45c8d433ac543f3b580b": [
        _frame("REVENUE", "CHANGE_TO", 23_500_000_000.0, change=5.0, polarity="NEGATIVE"),
    ],
    # Walmart
    "ecc0095ef8aee24cfb09": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 177_800_000_000.0),
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 7_300_000_000.0),
    ],
    "984f9e1ee25e02574260": [
        _frame("REVENUE", "CHANGE_BY", 23.0),
        _frame("REVENUE", "COMPOSITION", 24.0),
    ],
    "e217d5c709f630b2de7e": [
        _frame("REVENUE", "CHANGE_BY", 19.0),
    ],
}


TABLE_IDS = {
    # Adobe
    "0c09ca2dd1fe808f82a2",
    "90dbbfbf064ee9241750",
    "aa5f9c12f2cd5c229941",
    "c9be13dd15dcce87d416",
    # Axon
    "8f49f88414083be40f3d",
    "714c4c62d575d9d9bdc4",
    "87b7573b42bfcd6794dd",
    # CrowdStrike
    "476a016bf8438cebb72a",
    "4a563ac6cc5a6625769a",
    # Fortinet
    "e0f32fabe269a4d2bacc",
    # Home Depot
    "f538cd13024840ec2069",
    "c5bb58ede9aabaceb96e",
    "7b6201cf8975f54f7ecb",
    # Microsoft
    "a993c731625b79077a01",
    # Oracle
    "5bd9399da6714119a20a",
    # PayPal
    "8e59bf6c6f6811e07b3f",
    "f6da14d4409336b8ab64",
    "f4c67d0ab7f7cc233f7a",
    # UnitedHealth Group
    "49bdc712125a191a5381",
    "d63ab05fcced794bc6ec",
    "b07a2b2c6c55363fe147",
    "30a90a2998e3c396ebee",
    "d1be3c0cd89a1fd0aaa6",
    # Walmart
    "08f348e9cf7b4ae9a6a5",
    "8a1621dd7b0fbb50a8a4",
}


NOTES = {
    "16c53cd7512a78dbce02": "ARR is a recurring-contract balance, not GAAP revenue flow",
    "702e1f900d109373e369": "free cash flow is not an issuer CASH balance",
    "24636f025b6f33632cf1": "free cash flow is not an issuer CASH balance",
    "48117367afa34371c43a": "adjusted free cash flow is not an issuer CASH balance",
    "08ac70946a6b2ce71c5d": "numeric result bullets are prose, not a financial table",
    "b07508267138ca24489f": "two operating-margin result bullets are prose, not a table",
    "b04ee03a568ccc571518": "table heading without usable observations",
    "d63ab05fcced794bc6ec": "numeric continuation of a financial table",
    "8a1621dd7b0fbb50a8a4": "guidance revision grid is a table, not prose",
    "417efdf212e4d7f85fe4": "prior-quarter 50.4 percent is outside the current prior-year frame vocabulary",
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
                    "exhaustive manual fifteenth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.2 fifteenth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown fifteenth-holdout candidate ids: {sorted(unknown)}")
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
