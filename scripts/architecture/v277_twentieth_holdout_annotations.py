from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v277_twentieth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v277_twentieth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the first V2.7.7 prediction on this
# issuer- and document-disjoint holdout.  The labels describe the semantic
# contract, not the current implementation's capabilities.  In particular,
# percentage-of-sales gross profit is a gross-margin observation even when the
# candidate generator fails to recognize that paraphrase.
EXPECTED = {
    # Cigna.
    "a003990b5b0b21eb1cec": [
        _frame("REVENUE", "CHANGE_BY", 8.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 27.0, polarity="NEGATIVE"),
    ],
    "f14f65edf4c13ce2c41c": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 2_100_000_000.0),
    ],
    "982b298b8b16cd84e803": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 6.0),
    ],
    "97d57b68a7f55202440e": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 71_700_000_000.0),
    ],
    "b086b2234a7d4ee413f9": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 67_200_000_000.0),
    ],
    # HCA Healthcare.
    "363905fbfa0da2f9785d": [
        _frame("REVENUE", "CHANGE_BY", 6.4),
    ],
    "e5d77fb1d2bc3472bead": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 1_231_000_000.0),
    ],
    # Truist.  Short- and long-term borrowings are separate debt components.
    "78ec17032e12a238487d": [
        _frame("REVENUE", "CHANGE_BY", 23_000_000.0),
        _frame("REVENUE", "CHANGE_BY", 0.6),
    ],
    "d0ba70110d812317a825": [
        _frame("DEBT", "CHANGE_BY", 1_800_000_000.0, polarity="NEGATIVE"),
        _frame("DEBT", "CHANGE_BY", 5.8, polarity="NEGATIVE"),
        _frame("DEBT", "CHANGE_BY", 3_500_000_000.0),
        _frame("DEBT", "CHANGE_BY", 9.4),
    ],
    # Linde.  The first item is a bullet summary, not a financial grid.
    "018932fbab30e80b98c7": [
        _frame("REVENUE", "CHANGE_TO", 9_300_000_000.0, change=9.0),
        _frame("REVENUE", "CHANGE_BY", 4.0),
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 2_600_000_000.0),
        _frame("OPERATING_INCOME", "CHANGE_TO", 2_700_000_000.0, change=7.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 27.5),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 29.5),
        _frame("BACKLOG", "ABSOLUTE_VALUE", 11_000_000_000.0),
    ],
    "0449405d1f43113890cd": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 2_554_000_000.0),
    ],
    "513f05b4f82af6cb61a5": [
        _frame("BACKLOG", "ABSOLUTE_VALUE", 8_100_000_000.0),
    ],
    "60283274e20bb2c8e2b7": [
        _frame("OPERATING_MARGIN", "CHANGE_BY", 60.0, polarity="NEGATIVE"),
    ],
    "77119d7afd9b4ade9b88": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 1_438_000_000.0),
    ],
    "99d018794a4840ae1e10": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 29.5),
    ],
    "c31c9aae7d98d973cb4a": [
        _frame("REVENUE", "CHANGE_TO", 1_870_000_000.0, change=13.0),
    ],
    "f29dd6eac5db2a0ecb28": [
        _frame("REVENUE", "CHANGE_TO", 9_289_000_000.0, change=9.0),
        _frame("REVENUE", "CHANGE_BY", 2.0),
    ],
    # Mondelez.
    "3aefd54a0f736af9ac32": [
        _frame("REVENUE", "CHANGE_BY", 4.1),
        _frame("REVENUE", "CHANGE_BY", 2.2),
    ],
    # Republic Services.
    "31751675190c1b0b57d3": [
        _frame("REVENUE", "CHANGE_BY", 4.0),
        _frame("REVENUE", "CHANGE_BY", 1.9, polarity="NEGATIVE"),
    ],
    # Centene.
    "19f60043daa6d1e76951": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            175_000_000_000.0,
            lower_value=173_000_000_000.0,
            upper_value=177_000_000_000.0,
        ),
        _frame("REVENUE_GUIDANCE", "CHANGE_BY", 2_000_000_000.0),
    ],
    # O'Reilly.  The gross-profit percentages are economically gross margins;
    # the shares are the diluted EPS denominator, not period-end shares.
    "f3267b7df89d26226e10": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 51.5),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 51.4),
    ],
    "867dbed67bdcabff14ce": [
        _frame("SHARES", "COMPARATIVE", 836_000_000.0),
        _frame("PRIOR_YEAR_SHARES", "COMPARATIVE", 861_000_000.0),
    ],
    # Philip Morris.
    "426ff0245ab9e26e3d87": [
        _frame("REVENUE", "CHANGE_BY", 16.5, polarity="NEGATIVE"),
    ],
    "8493ee35b20ce71b53f5": [
        _frame("OPERATING_INCOME", "CHANGE_BY", 6.1),
    ],
    "f90dfbcbee27560e57ef": [
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 8.0),
    ],
    "c7456e4701ec34b58ce9": [
        _frame(
            "ACTIVITY_VOLUME_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            2.5,
            lower_value=2.0,
            upper_value=3.0,
            polarity="NEGATIVE",
        ),
    ],
    # Vertex.
    "28533ad1d4da7424fb56": [
        _frame("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 150.0),
    ],
    "c5347a295ec803d26753": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            13_150_000_000.0,
            lower_value=13_100_000_000.0,
            upper_value=13_200_000_000.0,
        ),
    ],
    "563f3adbe5d715f626e8": [
        _frame("REVENUE", "CHANGE_TO", 2_060_000_000.0, change=11.0),
    ],
    "d10cfbb5dacd945af346": [
        _frame("REVENUE", "CHANGE_TO", 76_000_000.0, change=78.0),
        _frame("REVENUE", "CHANGE_TO", 76_000_000.0, change=151.0),
    ],
    "17f1b1d827a781abca40": [
        _frame("REVENUE", "CHANGE_TO", 1_280_000_000.0, change=14.0),
    ],
    "8c7c4faaf54d2001de03": [
        _frame("CASH", "COMPARATIVE", 13_600_000_000.0),
        _frame("PRIOR_YEAR_CASH", "COMPARATIVE", 12_300_000_000.0),
    ],
    "f7648af430aad0d349a3": [
        _frame("REVENUE", "CHANGE_TO", 3_330_000_000.0, change=12.0),
    ],
}


TABLE_IDS = {
    # Cigna.
    "33f34a73cbf6ef0f66c6",
    # HCA Healthcare.
    "568aa4de4615266b6bad",
    "5f365f3b13794ec62174",
    "8e5374bebf5ab543c5e0",
    "ae3e47d55fe61f0c6492",
    # Truist.
    "a64ee8a0b1204f9effa5",
    "d7e6e9956fceb25faa82",
    # Mondelez.
    "d8172c07d4396be22064",
    "abac2d165d8411db89e6",
    "5d08ee704559d322331a",
    # Republic Services.
    "5daf200e5f11e50b0e59",
    "76fc618671b48563bae1",
    "9955db29ddc1c53ac6d4",
    # Centene.
    "b279c835795804af0b0d",
    "c6d69e215f6f7731664b",
    "d57525191a4b78c820b2",
    # O'Reilly.
    "e72797780045a39e3295",
    # Philip Morris.
    "31085e3b7db5cf92fb5b",
    "52c4c8949a0a4dfa5c99",
    "6169bfe7cddf7052c806",
    "70b584b48b5650ef8bb9",
}


NOTES = {
    "018932fbab30e80b98c7": "multi-KPI highlights are a semantic bullet list, not a financial grid",
    "513f05b4f82af6cb61a5": "quote fragment contains an explicit backlog level and is not a table",
    "35834e6f7ea5bfe710c9": "other earning assets primarily comprising cash are not a pure CASH fact",
    "57e2d0100bf47d3ab0a8": "free cash flow guidance is outside the current cash-balance ontology",
    "6b7c142c1ddfd666aa6b": "headwind overcome is not an observed margin change",
    "bf14708108f09906c123": "free cash flow guidance is outside the current cash-balance ontology",
    "2682021a42e8f17b193b": "SG&A expense and SG&A-to-sales are not revenue or operating margin",
    "f3267b7df89d26226e10": "gross profit as a percentage of sales is a gross-margin paraphrase",
    "867dbed67bdcabff14ce": "diluted EPS denominator is diluted weighted-average shares",
    "8e5168528135f612f87b": "500 million or more is an inequality-only forward-looking threshold",
    "6a486ca20286233d7f98": "500 million or more is an inequality-only guidance threshold",
    "563f3adbe5d715f626e8": "geographic bullet fragment is prose, not a table",
    "17f1b1d827a781abca40": "geographic bullet fragment is prose, not a table",
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
                    "exhaustive manual twentieth-holdout annotation before prediction",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.7 twentieth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twentieth-holdout candidate ids: {sorted(unknown)}")
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
