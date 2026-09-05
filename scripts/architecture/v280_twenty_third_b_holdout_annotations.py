from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v280_twenty_third_b_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v280_twenty_third_b_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the first V2.8.0 prediction.  Labels
# follow economic meaning even when the frozen candidate vocabulary does not:
# passenger-unit revenue is price realization, shipments/supply are activity,
# operating/free cash flow is not a cash balance, and numeric grids stay table-only.
EXPECTED = {
    # Agilent.
    "c5b052f6466c0fff071b": [
        _frame("REVENUE", "CHANGE_TO", 346_000_000.0, change=7.0),
    ],
    "30f42353cee3ccd340aa": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 34.3),
    ],
    "6690fca53fc72b6cbf9e": [
        _frame("REVENUE", "CHANGE_TO", 746_000_000.0, change=11.0),
        _frame("REVENUE", "CHANGE_TO", 746_000_000.0, change=10.0),
    ],
    "9bce8dd7c2cf5f224252": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 28.3, change=320.0),
        _frame("OPERATING_MARGIN", "CHANGE_BY", 110.0),
        _frame("OPERATING_MARGIN", "CHANGE_BY", 190.0),
    ],
    "c0417dd7c3d3905dec8d": [
        _frame("REVENUE", "CHANGE_TO", 786_000_000.0, change=6.0),
        _frame("REVENUE", "CHANGE_TO", 786_000_000.0, change=5.0),
    ],
    # Alcoa.
    "08d4ec59be32f837573e": [
        _frame("REVENUE", "CHANGE_BY", 3.0, polarity="NEGATIVE"),
    ],
    "31ff28acc65564824325": [
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 18.0),
    ],
    "7b40ae1be283df4dfd27": [
        _frame(
            "PRODUCTION_GUIDANCE",
            "RANGE_GUIDANCE",
            2.5,
            lower_value=2.4,
            upper_value=2.6,
        ),
        _frame(
            "ACTIVITY_VOLUME_GUIDANCE",
            "RANGE_GUIDANCE",
            2.7,
            lower_value=2.6,
            upper_value=2.8,
        ),
    ],
    "c357d1a0f4ad00ebb928": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 186_000_000.0),
    ],
    # American Airlines.
    "8dd3c590dd15040fb2e3": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            17.5,
            lower_value=16.0,
            upper_value=19.0,
        ),
    ],
    "e5e45c0689906aad8ee6": [
        _frame("PRICE_REALIZATION", "CHANGE_BY", 13.4),
        _frame("PRICE_REALIZATION", "CHANGE_BY", 8.8),
    ],
    "2b314003daafeb01b82a": [
        _frame("PRICE_REALIZATION", "CHANGE_BY", 8.9),
        _frame("PRICE_REALIZATION", "CHANGE_BY", 15.1),
        _frame("PRICE_REALIZATION", "CHANGE_BY", 6.6),
    ],
    # Abbott.
    "0fd498d4638f2802353b": [
        _frame("REVENUE", "CHANGE_BY", 13.0),
        _frame("REVENUE", "CHANGE_BY", 4.8),
    ],
    "0c8c0eb4dbb49a2b2322": [
        _frame("REVENUE", "CHANGE_BY", 127_000_000.0),
    ],
    "9f551c7873b9f52752d4": [
        _frame("REVENUE", "CHANGE_BY", 9.8),
        _frame("REVENUE", "CHANGE_BY", 10.7),
    ],
    # Airbnb.
    "daf13af558e29d085d86": [
        _frame("ADJUSTED_EBITDA", "COMPARATIVE", 1_300_000_000.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 1_000_000_000.0),
        _frame("ADJUSTED_EBITDA", "CHANGE_BY", 21.0),
    ],
    "4f768ef5dfab2ebaee0d": [
        _frame("ORDERS", "CHANGE_BY", 10.0),
        _frame("ORDERS", "CHANGE_BY", 12.0),
    ],
    "54a0dec54343ca18bd71": [
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 80.0),
    ],
    # Accenture.
    "47fd0fcc3b923e008d3d": [
        _frame("ORDERS", "COMPARATIVE", 19_300_000_000.0),
        _frame("PRIOR_YEAR_ORDERS", "COMPARATIVE", 19_700_000_000.0),
    ],
    "24c0762cea9bc53af2fb": [
        _frame("ORDERS", "CHANGE_TO", 19_320_000_000.0, change=2.0, polarity="NEGATIVE"),
    ],
    "d2b63da9fafbeacd981b": [
        _frame("REVENUE", "CHANGE_TO", 18_700_000_000.0, change=6.0),
        _frame("REVENUE", "CHANGE_BY", 1_000_000_000.0),
    ],
    "cf102fdd9af5f5662e79": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            4.5,
            lower_value=4.0,
            upper_value=5.0,
        ),
    ],
    # ADP.
    "42f6577e9935fd6867e4": [
        _frame(
            "ORDERS_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            5.5,
            lower_value=4.0,
            upper_value=7.0,
        ),
    ],
    "a411769cd6f1b8bcde57": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            5.5,
            lower_value=5.0,
            upper_value=6.0,
        ),
    ],
    "ee4c01016d1e34f55469": [
        _frame("REVENUE", "CHANGE_BY", 7.0),
    ],
    "d27b2833d805e93fa0ff": [
        _frame("REVENUE", "CHANGE_BY", 7.0),
        _frame("REVENUE", "CHANGE_BY", 6.0),
        _frame("REVENUE", "CHANGE_BY", 5.0),
    ],
    "57c019b3dc3bde954e69": [
        _frame("OPERATING_MARGIN", "CHANGE_BY", 100.0, polarity="NEGATIVE"),
        _frame("OPERATING_MARGIN", "CHANGE_BY", 110.0, polarity="NEGATIVE"),
    ],
    # Allstate.
    "5a4d36dc03d81ee285fa": [
        _frame("REVENUE", "CHANGE_TO", 935_000_000.0, change=7.8),
    ],
    "cb687ff91ab6068bf6ec": [
        _frame("REVENUE", "CHANGE_TO", 18_600_000_000.0, change=11.8),
        _frame("REVENUE", "CHANGE_BY", 2_000_000_000.0),
    ],
    "1578c5472a101cf802f3": [
        _frame("REVENUE", "CHANGE_TO", 615_000_000.0, change=9.2),
        _frame("REVENUE", "CHANGE_BY", 52_000_000.0),
    ],
    "c001e505a3ab91b937bd": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 147_000_000.0),
    ],
    "68d87168255dafe4c288": [
        _frame("REVENUE", "CHANGE_TO", 40_000_000.0, change=2.4, polarity="NEGATIVE"),
    ],
    # AES.
    "8b60a6e80b74d9633d1b": [
        _frame("ADJUSTED_EBITDA", "CHANGE_BY", 50.0),
    ],
    "743a96d1060df572c605": [
        _frame(
            "ADJUSTED_EBITDA_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            6.0,
            lower_value=5.0,
            upper_value=7.0,
        ),
    ],
    "a305e21e7d38ab5c5a26": [
        _frame("CAPEX_GUIDANCE", "ABSOLUTE_VALUE", 1_400_000_000.0),
    ],
    # Albemarle.
    "20670424efa10743e43b": [
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 858_000_000.0, change=155.0),
    ],
}


TABLE_IDS = {
    "d4309570b03e5937b709",  # Agilent cash-flow grid.
    "0c32034acd1d29900ea0",  # Agilent balance sheet.
    "69e7fae86ab93faa05e4",  # Alcoa net-debt table.
    "546a60fed6c2c7d869b7",  # Alcoa free-cash-flow table.
    "e778612af3a72a7710d7",  # American cash-flow statement.
    "592da23d2105945a239d",  # Abbott quarterly tax reconciliation.
    "b90028b3fa73bea21885",  # Abbott YTD tax reconciliation.
    "f3c4c074696326ca1bdc",  # Abbott geographic/segment grid fragment.
    "83f33006c9195ea55b8e",  # Abbott specified-items table.
    "e3b11478e640fad792e4",  # Accenture revenue grid.
    "803bf63144658af52f98",  # Accenture cash-flow statement.
    "3f82674bb0699f15f2ac",  # Accenture outlook grid.
    "03d655a2551f0073037a",  # ADP adjusted EBIT reconciliation.
    "41d9abf7e4d0af8638ee",  # ADP outlook table.
    "114863224f82c4e0d29f",  # ADP margin row fragment.
    "ad502d2f88c906ce5643",  # Allstate homeowners results.
    "a89ac28f6a8bd495a615",  # Allstate auto results.
    "ba43ace1aa3508174bbd",  # Allstate financial statements.
    "d40b06cb717c4c1e3eb1",  # AES non-GAAP reconciliation.
    "e75d8f473a9647597fe1",  # Albemarle Energy Storage table.
    "bc23347332c5cd16a977",  # Albemarle Specialties table with prose.
    "c3cb2d615977a556a167",  # Albemarle corporate outlook grid.
}


NOTES = {
    "9bce8dd7c2cf5f224252": "numeric bullet is prose: level, tariff component, YoY and sequential margin changes",
    "31ff28acc65564824325": "shipments are an ACTIVITY_VOLUME anchor; production is only the causal driver",
    "7b40ae1be283df4dfd27": "respectively aligns production and shipment guidance ranges",
    "e5e45c0689906aad8ee6": "passenger unit revenue is realized price, not GAAP revenue",
    "2b314003daafeb01b82a": "regional passenger unit revenue rates are price-realization facts",
    "daf13af558e29d085d86": "single comparative sentence is prose despite frozen router classification",
    "54a0dec54343ca18bd71": "80 percent modifies Experiences supply, not guest bookings",
    "cf102fdd9af5f5662e79": "guidance sentence fragment is prose, not a flattened table",
    "51e75aeea8213cb62f41": "cash from operations is outside the cash-balance ontology",
    "00604e9e0e4a3c74266e": "cash returns to shareholders are not a cash balance",
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
                    "exhaustive manual twenty-third-B annotation before prediction",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.8.0 twenty-third-B holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twenty-third-B candidate ids: {sorted(unknown)}")
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
