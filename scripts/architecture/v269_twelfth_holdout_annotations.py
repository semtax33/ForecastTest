from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v269_twelfth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v269_twelfth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the first V2.6.9 prediction on this
# issuer- and document-disjoint holdout.  Flow measures are not cash balances,
# and table footnote adjustments are not reported revenue levels.
EXPECTED = {
    # Netflix
    "c9d604889d7027bc5c41": [
        _frame("OPERATING_MARGIN_GUIDANCE", "ABSOLUTE_VALUE", 33.2),
    ],
    # Mastercard
    "d6ef085f65db3a3aef7d": [
        _frame("ACTIVITY_VOLUME", "CHANGE_BY", 8.0),
    ],
    "666bcb238fbcd4d32b3b": [
        _frame("REVENUE", "CHANGE_BY", 20.0),
        _frame("REVENUE", "CHANGE_BY", 18.0),
    ],
    # Goldman Sachs
    "09c9acf3ab8464f001e3": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 37_570_000_000.0),
    ],
    "6e61e892d8d57dd43439": [
        _frame("REVENUE", "CHANGE_TO", 7_420_000_000.0, change=72.0),
    ],
    # Morgan Stanley
    "4e715f453352c73ae115": [
        _frame("REVENUE", "COMPARATIVE", 8_900_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 7_800_000_000.0),
    ],
    # Palo Alto Networks
    "4eb09bf439bfdfd27dd8": [
        _frame("REVENUE", "CHANGE_TO", 3_000_000_000.0, change=31.0),
    ],
    "79057dd41372d782191e": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            3_350_000_000.0,
            lower_value=3_345_000_000.0,
            upper_value=3_355_000_000.0,
        ),
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 32.0),
    ],
    "b737c5bcc2ecc4942142": [
        _frame(
            "SHARES_GUIDANCE",
            "RANGE_GUIDANCE",
            835_000_000.0,
            lower_value=830_000_000.0,
            upper_value=840_000_000.0,
        ),
    ],
    # Lam Research
    "e04e7b891bff725475a9": [
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 51.7),
    ],
    "e81156d6fca5b26c5e89": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 6_720_000_000.0),
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 51.7),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 37.4),
    ],
    "54eb15ffa6103f7f21be": [
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 52.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 38.4),
    ],
    # Intuitive Surgical
    "b67a380591a9f2e21839": [
        _frame("OPERATING_INCOME", "COMPARATIVE", 1_220_000_000.0),
        _frame("PRIOR_YEAR_OPERATING_INCOME", "COMPARATIVE", 950_000_000.0),
    ],
    # Medtronic
    "833cb53cf99d3ca55f72": [
        _frame("REVENUE", "CHANGE_TO", 2_388_000_000.0, change=8.0),
        _frame("REVENUE", "CHANGE_BY", 5.1),
    ],
    "f15597cedb2901a3bd14": [
        _frame("REVENUE", "CHANGE_BY", 78.0),
        _frame("REVENUE", "CHANGE_BY", 124.0),
    ],
    "808d7de1543a62d6484c": [
        _frame("REVENUE", "CHANGE_TO", 2_751_000_000.0, change=5.0),
        _frame("REVENUE", "CHANGE_BY", 3.0),
    ],
    "bdaf07c3c7c7a428ac43": [
        _frame("REVENUE", "CHANGE_BY", 308_000_000.0),
    ],
    # ServiceNow
    "813e6237e26eb047ff9f": [
        _frame("REVENUE", "CHANGE_TO", 3_877_000_000.0, change=24.5),
        _frame("REVENUE", "CHANGE_BY", 23.0),
    ],
}


TABLE_IDS = {
    # Netflix
    "e7899dc7e61724099723",
    "49313f7b1b084edf24cd",
    # Mastercard
    "680c09891df55fd8b582",
    "7c6ab55c3f637e70445c",
    "cbb87b931e3bccfd585d",
    "7dd18436b821d013a6be",
    "60995644dcdafe4e4065",
    # Goldman Sachs
    "ca36a1452bcafeee7be1",
    "b638387b30ad605dfbbc",
    "eef22369d1217cb8836c",
    # Morgan Stanley
    "9c57abcf82daf1f322ac",
    "5d44f13996598a84c964",
    # Prologis
    "eb5168b430db8197497f",
    "d2b1994f0e74b1e4ae97",
    "03671d207dcd128ab862",
    "8b03ed73dd5185cd94da",
    # Palo Alto Networks
    "c1733fd896c847a37362",
    # Lam Research
    "35b4e786d9f7cf46a495",
    "db6c0126ee5fc19dbe5c",
    "46ca1c3b9ff77bdb94cf",
    "39c78355f20b1bf5d9f0",
    # Intuitive Surgical
    "ea60b6d1c968a91efefc",
    # Medtronic
    "73ff35bcc9e2a6c7a73a",
    # ServiceNow
    "c0dcc0f0733dc942afaf",
    "1ba0703b2850daa8e6db",
}


NOTES = {
    "49313f7b1b084edf24cd": "flattened net-debt reconciliation, not prose cash facts",
    "60995644dcdafe4e4065": "three-column KPI mini-grid despite prose sampling",
    "b638387b30ad605dfbbc": "compact segment row followed by a provision comparison",
    "9c57abcf82daf1f322ac": "compact financial grid despite prose routing",
    "46ca1c3b9ff77bdb94cf": "GAAP/non-GAAP current/prior operating-margin grid",
    "0c3d58248ac09a0a2cee": "table footnote prose; adjustments are not reported revenue facts",
    "c7b66936768cec6cdf11": "operating cash flow is not a CASH balance",
    "69fe65bdf4f4cb5feeeb": "operating cash flow is not a CASH balance",
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
                    "exhaustive manual twelfth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.6.9 twelfth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twelfth-holdout candidate ids: {sorted(unknown)}")
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
