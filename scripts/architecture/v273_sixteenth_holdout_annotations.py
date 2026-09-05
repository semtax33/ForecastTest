from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v273_sixteenth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v273_sixteenth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive labels frozen before the first V2.7.3 prediction on this issuer-
# and document-disjoint holdout.  Definitions, transactions, free cash flow,
# and table-only observations are deliberately not weakened into issuer KPIs.
EXPECTED = {
    # Baker Hughes
    "4d2dd9ccbee5f3e92495": [
        _frame("REVENUE", "CHANGE_TO", 933_000_000.0, change=1.0),
        _frame("REVENUE", "CHANGE_BY", 5_000_000.0),
    ],
    "0b18181d5428b436f5d9": [
        _frame("ORDERS", "ABSOLUTE_VALUE", 10_500_000_000.0),
        _frame("ORDERS", "ABSOLUTE_VALUE", 7_100_000_000.0),
    ],
    "6d7047bbcf61b810eaa9": [
        _frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 1_231_000_000.0),
    ],
    "262d2065c4a8c1c1002c": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 6_700_000_000.0),
    ],
    # Boston Scientific
    "ca3493a9e55ce1581fbb": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            4.0,
            lower_value=3.0,
            upper_value=5.0,
        ),
    ],
    "bc6e0db84ff1b0016e73": [
        _frame("REVENUE", "CHANGE_TO", 5_442_000_000.0, change=7.5),
        _frame("REVENUE", "CHANGE_BY", 7.0),
    ],
    # Carnival
    "b3377554d6bedfdc5301": [
        _frame("GROSS_MARGIN", "CHANGE_BY", 3.9, polarity="NEGATIVE"),
    ],
    # Cisco
    "56cb02878c7a3d304b36": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 22_000_000_000.0, change=13.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 34.8),
    ],
    "63274d475e4e6a499f0a": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 15_400_000_000.0, change=31.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 24.3),
    ],
    "bae407f7862821fc4f76": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 6_200_000_000.0, change=23.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 35.9),
    ],
    "6fbfd99fa255fea7d338": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 17_300_000_000.0),
    ],
    "a90b89b7f5b176c52e2c": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            18_100_000_000.0,
            lower_value=18_000_000_000.0,
            upper_value=18_200_000_000.0,
        ),
    ],
    # Deckers
    "7e281549c06f69439aa5": [
        _frame("OPERATING_INCOME", "COMPARATIVE", 155_300_000.0),
        _frame("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 165_300_000.0),
    ],
    "e0f1a840b33efbbd0273": [
        _frame("CASH", "COMPARATIVE", 1_603_000_000.0),
        _frame("PRIOR_YEAR_CASH", "COMPARATIVE", 1_720_000_000.0),
    ],
    "79db5a1fae8017352fe0": [
        _frame("REVENUE", "CHANGE_TO", 1_020_000_000.0),
    ],
    "37b055679de1b57d056f": [
        _frame("REVENUE", "COMPARATIVE", 1_020_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 964_500_000.0),
    ],
    "a7567fef9a588563aab9": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            5_885_000_000.0,
            lower_value=5_860_000_000.0,
            upper_value=5_910_000_000.0,
        ),
    ],
    "08fec61a21bb538b1dde": [
        _frame("GROSS_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 56.5),
    ],
    "515ecb50ed3ccbaa776a": [
        _frame("OPERATING_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 21.5),
    ],
    "81e76b8c761bb93a5761": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 1_000_000_000.0),
    ],
    # Dow
    "4a310a75a2c8c8137dec": [
        _frame("EBIT", "CHANGE_TO", 133_000_000.0, change=19_000_000.0, polarity="NEGATIVE"),
    ],
    "033270f07842a182604f": [
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 1.0, polarity="NEGATIVE"),
    ],
    "330999fe2ab5ffe6db12": [
        _frame("EBIT", "CHANGE_TO", 1_600_000_000.0, change=1_700_000_000.0),
    ],
    "ce19e12e393896058d9f": [
        _frame("REVENUE", "CHANGE_BY", 1.0),
    ],
    # eBay
    "867cdbe6c49de0513e0b": [
        _frame("CASH", "ABSOLUTE_VALUE", 4_900_000_000.0),
    ],
    "e28a0e369a1dceda92e2": [
        _frame("REVENUE", "CHANGE_TO", 570_000_000.0, change=25.0),
        _frame("REVENUE", "CHANGE_BY", 24.0),
    ],
    "0548bbfbe848fbacd59b": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 596_000_000.0),
    ],
}


TABLE_IDS = {
    # Apollo
    "3a1ed079c9517f8e5820",
    "e2bcf0fa8ad95d58872d",
    "e96c09098dccafcb3b91",
    # Becton Dickinson
    "a4b0dfb30e774be968ba",
    "9cf797f0faa7cbdd3f33",
    "6339db385ec68f83e3b7",
    # Boston Scientific
    "028a3b39975e28fc98ca",
    # Carnival
    "447a9693a3d3da9b302d",
    "6dc917028cea499a844d",
    # Cisco
    "9e2a7e57b8d1dece87b6",
    # Dow
    "9d504ac6a2009a6033d4",
    # eBay
    "c29a8bf88f696c852594",
    "53e780a880195f9a1388",
    # Freeport-McMoRan
    "df5765950548ad6a523e",
    "6b6ba9c91aa8658297d7",
    "886f99738d5016f3d72e",
}


NOTES = {
    "3a1ed079c9517f8e5820": "narrative lead-in followed by a multi-column balance-sheet grid",
    "e96c09098dccafcb3b91": "flattened presentation/chart layout rather than prose",
    "1f0cbe38c0243913f524": "non-GAAP explanatory prose, not the referenced reconciliation table",
    "a90b89b7f5b176c52e2c": "short guidance bullets remain text facts, not a multi-period table",
    "37b055679de1b57d056f": "explicit current/prior values own the comparative frame; reported growth is redundant",
    "53e780a880195f9a1388": "flattened multi-metric guidance grid routed to TABLE_DSL",
    "867cdbe6c49de0513e0b": "cash and non-equity investment liquidity portfolio is an issuer cash anchor",
    "fd7a10c0f3b182bf09da": "acquisition consideration is not an issuer cash balance",
    "1fd12b61dc85fb6070c7": "operating cash flow is not an issuer cash balance",
    "886f99738d5016f3d72e": "flattened milestone slide with layout-dependent production percentages",
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
                    "exhaustive manual sixteenth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.3 sixteenth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown sixteenth-holdout candidate ids: {sorted(unknown)}")
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
