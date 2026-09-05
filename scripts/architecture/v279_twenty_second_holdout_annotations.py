from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v279_twenty_second_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v279_twenty_second_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the first V2.7.9 prediction on this
# issuer- and document-disjoint holdout.  Unsupported concepts (cash flow,
# debt-maturity ladders, pretax margin, EPS) remain fail-closed.  Economically
# explicit ticket/traffic, bookings, prior-period, and bridge components are
# retained even when the frozen candidate vocabulary may not recover them.
EXPECTED = {
    # Dollar Tree.
    "1a8988bc44a20580d595": [
        _frame("GROSS_MARGIN", "CHANGE_TO", 39.8, change=480.0),
        _frame("GROSS_MARGIN", "CHANGE_BY", 340.0),
    ],
    "72e34c98d5c50060aed5": [
        _frame("REVENUE", "CHANGE_TO", 9_900_000_000.0, change=7.1),
    ],
    "7fccebe6129168e9c737": [
        _frame("OPERATING_MARGIN", "CHANGE_BY", 500.0),
        _frame("OPERATING_MARGIN", "CHANGE_BY", 320.0),
    ],
    "88b5b36c5261575eaa26": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 690_000_000.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 14.1),
    ],
    "8a1e03627e974a1693ba": [
        _frame("GROSS_MARGIN", "CHANGE_TO", 42.9, change=850.0),
        _frame("GROSS_MARGIN", "CHANGE_BY", 680.0),
    ],
    "9f0cceab0e4db921826f": [
        _frame("PRICE_REALIZATION", "CHANGE_BY", 3.3),
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 0.4),
    ],
    "f15a633a6adc000d6e6b": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 1_160_000_000.0, change=89.1),
        _frame("OPERATING_MARGIN", "CHANGE_TO", 11.8, change=510.0),
    ],
    # IQVIA.
    "06e1aef069127c5a8ec8": [
        _frame("REVENUE", "CHANGE_TO", 4_972_000_000.0, change=7.5),
        _frame("REVENUE", "CHANGE_TO", 4_972_000_000.0, change=6.4),
    ],
    "84df51875f0c4876a5b3": [
        _frame("REVENUE", "CHANGE_TO", 4_368_000_000.0, change=8.7),
        _frame("REVENUE", "CHANGE_TO", 4_368_000_000.0, change=8.5),
    ],
    "a48205b85f94b0c98547": [
        _frame("ORDERS", "CHANGE_TO", 3_150_000_000.0, change=19.0),
        _frame("BOOK_TO_BILL", "ABSOLUTE_VALUE", 1.22),
    ],
    "c1bf0ca7b3579c805d4c": [
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 6.5),
        _frame("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 100.0),
        _frame("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 50.0),
        _frame("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 80.0, polarity="NEGATIVE"),
    ],
    "d4f3ff90300fd20e7479": [
        _frame("REVENUE", "CHANGE_TO", 2_575_000_000.0, change=8.8),
    ],
    "e9335acc27fd9479157f": [
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 994_000_000.0, change=9.2),
    ],
    # Kimberly-Clark.
    "3d88a574e9739ba69ed2": [
        _frame("DEBT", "COMPARATIVE", 6_500_000_000.0),
        _frame("PRIOR_YEAR_DEBT", "COMPARATIVE", 7_200_000_000.0),
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "CHANGE_BY",
            100.0,
            polarity="NEGATIVE",
        ),
    ],
    "9f8c1a1329a3fedf471b": [
        _frame("REVENUE", "CHANGE_BY", 2.5),
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 2.2),
        _frame("REVENUE", "CHANGE_BY", 1.2),
    ],
    "a153d4ba625e0b04a2fd": [
        _frame("REVENUE", "CHANGE_BY", 0.5),
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 0.8),
    ],
    "e379e9ce764edb57cb30": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 38.3),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 35.0),
        _frame("GROSS_MARGIN", "CHANGE_BY", 50.0, polarity="NEGATIVE"),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "CHANGE_BY", 200.0, polarity="NEGATIVE"),
    ],
    # Paychex.
    "543f1265a7a21708a266": [
        _frame("OPERATING_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 44.0),
    ],
    "abbb084527aeb44592e3": [
        _frame("DEBT", "ABSOLUTE_VALUE", 4_600_000_000.0),
    ],
    "b5b71619e50423cdc4e7": [
        _frame("REVENUE", "CHANGE_BY", 8.0),
    ],
    # Royal Caribbean.
    "32a2c917d423b34fb33c": [
        _frame("GROSS_MARGIN", "CHANGE_BY", 5.6, polarity="NEGATIVE"),
    ],
    "5c81c30384456ff104c9": [
        _frame("REVENUE", "CHANGE_BY", 6.0),
    ],
    "c023e1ebce5366a4a853": [
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 9.0),
    ],
    "c8195df4d43ebcafb72a": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 4_800_000_000.0),
        _frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 1_800_000_000.0),
    ],
    # Ross Stores.
    "0f70df652657b9598013": [
        _frame("REVENUE", "CHANGE_BY", 13.0),
    ],
    "3aba4e5a7bd2fbd43dea": [
        _frame("REVENUE", "CHANGE_BY", 10.0),
        _frame("PRIOR_YEAR_REVENUE", "CHANGE_BY", 2.0),
    ],
    "4937fad21339a9f67337": [
        _frame("OPERATING_MARGIN", "CHANGE_BY", 205.0),
        _frame(
            "OPERATING_MARGIN_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            140.0,
            lower_value=130.0,
            upper_value=150.0,
        ),
    ],
    "66d8bb6b3819768c2daf": [
        _frame("REVENUE", "COMPARATIVE", 12_300_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 10_500_000_000.0),
        _frame("REVENUE", "CHANGE_BY", 17.0),
    ],
    "6beb93444d8ebc111376": [
        _frame("REVENUE", "CHANGE_BY", 13.0),
        _frame("REVENUE", "CHANGE_BY", 10.0),
    ],
    "c52ef175a15620b329a5": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            6.5,
            lower_value=6.0,
            upper_value=7.0,
        ),
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            4.5,
            lower_value=4.0,
            upper_value=5.0,
        ),
    ],
    # TJX.
    "07d6e31a7ca6d3efa601": [
        _frame("REVENUE", "CHANGE_TO", 29_500_000_000.0, change=7.0),
    ],
    "351b16425c2e887a3e5f": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 33.4),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 30.7),
        _frame("GROSS_MARGIN", "CHANGE_BY", 2.7),
    ],
    "a696b01c27364da5fc3f": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            2.5,
            lower_value=2.0,
            upper_value=3.0,
        ),
    ],
    # Zoetis.
    "358333ea2abd10f32fac": [
        _frame("REVENUE", "CHANGE_TO", 1_200_000_000.0, change=8.0),
        _frame("REVENUE", "CHANGE_TO", 1_200_000_000.0, change=6.0),
    ],
    "3c35c85292fb3d7d295b": [
        _frame("REVENUE", "CHANGE_BY", 11.0, polarity="NEGATIVE"),
    ],
    "dd55c5a915a231152d4b": [
        _frame("REVENUE", "CHANGE_BY", 1.0, polarity="NEGATIVE"),
    ],
    # Las Vegas Sands.
    "2ed8cc4c04949c77d8bc": [
        _frame("CASH", "ABSOLUTE_VALUE", 3_380_000_000.0),
    ],
    "4936e2cd24cd75cab21a": [
        _frame("REVENUE", "CHANGE_TO", 1_780_000_000.0, change=0.8, polarity="NEGATIVE"),
    ],
    "5057d319aa0caa315c81": [
        _frame("OPERATING_INCOME", "COMPARATIVE", 618_000_000.0),
        _frame("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 783_000_000.0),
    ],
    "aa3598c538cbc570fa69": [
        _frame("REVENUE", "COMPARATIVE", 3_150_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 3_180_000_000.0),
    ],
    "bb020a13e5e4dac9d7de": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 3_150_000_000.0),
    ],
}


TABLE_IDS = {
    "ac8c887804fd44b59bef",  # Dollar Tree balance sheet.
    "b60fa1b9f5fb4a3d6d34",  # IQVIA EBITDA reconciliation header/table.
    "f716c12f3bf8beb99a23",  # IQVIA EBITDA reconciliation rows.
    "5afdd22b4ac290e33352",  # Kimberly-Clark statements and segment results.
    "aed6d8c92dc25f48b16f",  # Kimberly-Clark income statement rows.
    "76f439786d73f5fd0141",  # Paychex cash-flow statement.
    "c0e8b50d2be1e147b759",  # Ross Stores statements of earnings.
    "0361f7be76f0ede24132",  # TJX financial statements and segments.
    "55ca269afda6dca94f5b",  # TJX segment grid followed by prose.
    "cc494827d28b92e9d90e",  # Williams segment/volume/capex tables.
    "2f8e388e1e4f34208a61",  # Zoetis segment table.
    "41c53e24f77f76af2276",  # Zoetis product table.
    "53580dd3655a96900e85",  # Zoetis U.S. table fragment.
    "066b895369a60b1b236c",  # Las Vegas Sands mall statistics table.
    "7f5b0a58ec1da153c48a",  # Las Vegas Sands operating statistics tables.
}


NOTES = {
    "9f0cceab0e4db921826f": "average ticket and traffic are explicit price and activity bridge components",
    "a48205b85f94b0c98547": "net new bookings are ORDERS; book-to-bill is a separate ratio fact",
    "3d88a574e9739ba69ed2": "numeric prose with debt comparison and outlook is not a table",
    "51679585044741fc43eb": "debt-maturity ladder lacks a safe DEBT_MATURITY ontology and is prose, not a grid",
    "9e06cfcb132c86a2fb70": "actual multi-segment 6%-to-7% range has no lossless actual-range frame",
    "0ad95488fd7b89a6762b": "only EPS ranges are numeric; sales projections are referenced but not quantified",
    "543f1265a7a21708a266": "approximately 44% is point guidance, not an inequality",
    "e379e9ce764edb57cb30": "current/prior transformation charges have explicit margin effects",
    "aa3598c538cbc570fa69": "stock-repurchase authorization is not revenue or cash balance",
    "a5e2c9cec9a791c70084": "operating cash flow is outside the cash-balance ontology",
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
                    "exhaustive manual twenty-second holdout annotation before prediction",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.9 twenty-second holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twenty-second-holdout candidate ids: {sorted(unknown)}")
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
