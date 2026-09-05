from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v275_eighteenth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v275_eighteenth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the first V2.7.5 prediction.
# Cash-flow measures and cash dividends are not cash-balance facts; unsupported
# insurance/bank ratios are not coerced into debt or margin concepts.
EXPECTED = {
    # Marriott: regional RevPAR changes are revenue-driver observations.
    "19bd564e463de28dba3b": [
        _frame("REVENUE", "CHANGE_BY", 5.0),
        _frame("REVENUE", "CHANGE_BY", 0.5, polarity="NEGATIVE"),
    ],
    "adaaa5447539e439e202": [
        _frame("REVENUE", "CHANGE_BY", 5.0),
        _frame("REVENUE", "CHANGE_BY", 3.0),
    ],
    # MetLife: holding-company cash and liquid assets is a balance fact.
    "f1dc308f34bb043a0655": [
        _frame("CASH", "ABSOLUTE_VALUE", 3_400_000_000.0),
    ],
    # Sysco.
    "3379d89e0e49c982692f": [
        _frame("GROSS_MARGIN", "CHANGE_TO", 18.5, change=10.0),
    ],
    "c9b3da9c0ea7a3d9403e": [
        _frame("REVENUE", "CHANGE_BY", 3.9),
    ],
    "77c2bc0faecb92758a22": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 524_000_000.0),
    ],
    "3f62f0235b4f0e7b4c6d": [
        _frame("GROSS_MARGIN", "CHANGE_TO", 18.7, change=17.0, polarity="NEGATIVE"),
    ],
    # Kroger.
    "bfd7b252041529f0e96f": [
        _frame("REVENUE", "CHANGE_BY", 0.5),
    ],
    # McKesson.
    "b276d4b05fcda396fb46": [
        _frame("REVENUE", "CHANGE_TO", 14_200_000_000.0, change=33.0),
    ],
    "8c4f73b9d11717f9376d": [
        _frame("REVENUE", "CHANGE_TO", 2_800_000_000.0, change=4.0),
    ],
    "a5665b4811f03ec09865": [
        _frame(
            "OPERATING_INCOME",
            "CHANGE_TO",
            195_000_000.0,
            change=20.0,
            polarity="NEGATIVE",
        ),
    ],
    # PNC: fee-income and capital-markets revenue changes.
    "9324449f8f2f16edf517": [
        _frame("REVENUE", "CHANGE_BY", 385_000_000.0),
        _frame("REVENUE", "CHANGE_BY", 20.0),
        _frame("REVENUE", "CHANGE_BY", 256_000_000.0),
    ],
    "1995b3dd7b2873601958": [
        _frame("REVENUE", "CHANGE_BY", 114_000_000.0),
    ],
    # U.S. Bancorp.
    "a694fd46a1baba898221": [
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 1_350.0),
    ],
    "97d52b928506d572a045": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 7_712_000_000.0),
        _frame("REVENUE", "CHANGE_BY", 7.5),
        _frame("REVENUE", "CHANGE_BY", 13.2),
    ],
    "5e8907995d3f950f0819": [
        _frame("REVENUE", "CHANGE_BY", 13.7),
    ],
    # AIG: underwriting income is operating income; combined ratios are not margins.
    "fc365bb6556484e8af77": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 686_000_000.0),
    ],
}


TABLE_IDS = {
    # Marriott
    "8b18a7e789d3414a16e5",
    "092a56cadf80bfed1a7a",
    # MetLife
    "a43ffddc955e8ab64357",
    # Roper
    "7b852acc1ddd533e3507",
    "82df51bd9e75d31dd3cc",
    "fa7c63bbdcc650412dc7",
    # Kroger
    "b54b30c62ff4cdb51dbe",
    # McKesson
    "3d6df2b6ad4bc4c86193",
    "dffc162290059028c33b",
    # PNC
    "a7f46783d14eda40b5c3",
    # Travelers
    "63538f9fd70f538e99a3",
    # AIG
    "67d9326285ba5693cd8e",
    "9c9c512b28774ce5fe9f",
    "9be69eaa116dbb6fe7ec",
}


NOTES = {
    "19bd564e463de28dba3b": "regional RevPAR prose followed by a definition footnote, not a table",
    "f1dc308f34bb043a0655": "holding-company cash and liquid assets is a cash-balance fact",
    "d5d28764403f339dc1f2": "operating/free cash flow is not a cash-balance fact",
    "304d41385f5f0384821f": "operating/free cash flow is not a cash-balance fact",
    "77c2bc0faecb92758a22": "capital expenditures amount is distinct from later liquidity prose",
    "7611fa7bb8fceaf0bc85": "debt-to-capital is not a debt amount",
    "c0412aa1b57f5f0cb8a8": "unsupported debt-to-capital ratio and target range are not coerced",
    "24534a9e476787da36d8": "cash dividend is not a cash-balance fact",
    "aef1902835d7f562762e": "macro forecast mentions capex but is not issuer CAPEX guidance",
    "b6c00dbbab325c3481f2": "cash dividend is not a cash-balance fact",
    "fc365bb6556484e8af77": "underwriting income is operating income; loss ratios are not margins",
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
                    "exhaustive manual eighteenth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.5 eighteenth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown eighteenth-holdout candidate ids: {sorted(unknown)}")
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
