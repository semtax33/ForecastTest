from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v271_fourteenth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/v271_fourteenth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before the first V2.7.1 prediction on this
# issuer- and document-disjoint holdout.  Equivalent percentage and money
# changes are retained as separate disclosed facts.  Calculated deltas are not
# invented when a filing only supplies current/prior levels.  The unsupported
# ``$3+ billion`` lower bound is deliberately not weakened into an exact fact.
EXPECTED = {
    # Arista Networks
    "5c2fcca2a3b0fec2acc8": [
        _frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 3_300_000_000.0),
    ],
    "ea1e3b9fb12e9b3aeda9": [
        _frame(
            "OPERATING_MARGIN_GUIDANCE",
            "RANGE_GUIDANCE",
            48.5,
            lower_value=48.0,
            upper_value=49.0,
        ),
    ],
    "85fcd4284c4f250a64c3": [
        _frame("REVENUE", "CHANGE_BY", 37.7),
    ],
    "0a797b5d5143614df389": [
        _frame("REVENUE", "CHANGE_TO", 3_036_000_000.0, change=12.1),
        _frame("REVENUE", "CHANGE_BY", 37.7),
    ],
    # Cboe Global Markets
    "869c7312ed210394927b": [
        _frame("REVENUE", "CHANGE_TO", 27_600_000.0, change=17.0),
        _frame("REVENUE", "CHANGE_BY", 4_000_000.0),
    ],
    "51e957f10dae7d3770c3": [
        _frame("REVENUE", "CHANGE_TO", 30_600_000.0, change=2.0),
        _frame("REVENUE", "CHANGE_BY", 500_000.0),
    ],
    "482cb4c46fc398a3729c": [
        _frame("REVENUE", "COMPARATIVE", 731_600_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 587_300_000.0),
    ],
    # Microchip Technology
    "206c5e311faffaaf183d": [
        _frame("DEBT", "CHANGE_BY", 170_000_000.0, polarity="NEGATIVE"),
    ],
    # Moody's
    "87f42cef88e12b11422f": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 47.9),
    ],
    "3b67156ac284612d2112": [
        _frame("REVENUE", "CHANGE_BY", 4.0),
    ],
    "d800e14736a77ccb9491": [
        _frame("REVENUE", "CHANGE_TO", 1_300_000_000.0, change=25.0),
    ],
    "11f5f5a3b307ee5017b7": [
        _frame("REVENUE", "CHANGE_BY", 72.0, polarity="NEGATIVE"),
    ],
    "1aeac543c00b5f0c1550": [
        _frame("REVENUE", "CHANGE_BY", 8.0),
    ],
    "137d8081d954a1f5c736": [
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 47.9),
        _frame("OPERATING_MARGIN", "CHANGE_TO", 55.3, change=440.0),
    ],
    # Rockwell Automation
    "6cf532bd5bdfd7ffea7e": [
        _frame("OPERATING_MARGIN", "COMPARATIVE", 15.1),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 13.3),
    ],
    "de455552e2d600958fbc": [
        _frame("REVENUE", "COMPARATIVE", 1_100_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 968_000_000.0),
    ],
    "ed308aa8fae2cb6fe425": [
        _frame("OPERATING_MARGIN", "COMPARATIVE", 22.3),
        _frame("PRIOR_YEAR_OPERATING_MARGIN", "COMPARATIVE", 19.5),
    ],
    "eef221850c847db7fe9e": [
        _frame("REVENUE", "COMPARATIVE", 482_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 547_000_000.0),
    ],
    # Synopsys
    "20c03d7714be0a744647": [
        _frame("REVENUE", "COMPARATIVE", 2_477_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 1_740_000_000.0),
    ],
    # Vertiv
    "481e5334f218a513aa57": [
        _frame("OPERATING_MARGIN", "CHANGE_TO", 22.6, change=410.0),
    ],
    "27cba31c585792e9993f": [
        _frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 14_000_000_000.0),
        _frame("REVENUE_GUIDANCE", "CHANGE_BY", 31.0),
    ],
    "739d467c85ae12399fcb": [
        _frame("OPERATING_INCOME", "CHANGE_TO", 638_000_000.0, change=44.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 196_000_000.0),
        _frame("OPERATING_INCOME", "CHANGE_TO", 738_000_000.0, change=51.0),
        _frame("OPERATING_INCOME", "CHANGE_BY", 249_000_000.0),
    ],
    "e22ff65bc61ed814cfa5": [
        _frame("REVENUE", "CHANGE_TO", 3_274_000_000.0, change=24.0),
    ],
}


TABLE_IDS = {
    # Arista Networks
    "a077c196a97ef4b670c9",
    # Blackstone
    "542b3dcc5f2436847f59",
    "2b9d7b4d2a2f4f62a148",
    "bf6d777b32f42573b514",
    # Cboe Global Markets
    "4a674dfe9d43b893da6e",
    # Microchip Technology
    "84355c120121eda1d8ef",
    "5fe0d7c9c5fa0dd93647",
    # Moody's
    "1e6fd61aa144ed12da98",
    "f4d3f33d34511c5ba91e",
    # Rockwell Automation
    "92bab21af7bb23e3bef4",
    # Synopsys
    "cf11326f2186d817b980",
    "44e5b24d9809efc61e40",
    "d3b616dd7f260b9c0ac9",
    # T. Rowe Price
    "f2fe9c1a9b346a620cd4",
    # Vertiv
    "1bde524b56d209428e2a",
    "3d0eb957bb98fc4e89e1",
    # Wells Fargo
    "49df01e602cbf29e08a7",
}


NOTES = {
    "0386a8a6849f70afae51": (
        "unsupported lower-bound revenue milestone is not weakened into an exact fact"
    ),
    "b153f4f375dc0be8e7df": "long risk prose is not a flattened financial table",
    "f678f1415161970f50ac": "long risk prose is not a flattened financial table",
    "057b1c7cf0b8fe835a49": (
        "net accrued performance revenue is an asset balance, not GAAP revenue flow"
    ),
    "066b8bf0bbca1aec5234": "technology and facility costs are not issuer revenue",
    "0dbf743006e11778dfdd": "truncated table heading without observations",
    "39a0d0972c63e0b665e7": "fragmented table tail is not a complete routable table",
    "76aed7a360e842f82233": "table introduction without usable table observations",
    "7e693aed93f47d7cb2bc": "table heading without usable table observations",
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
                    "exhaustive manual fourteenth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.1 fourteenth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown fourteenth-holdout candidate ids: {sorted(unknown)}")
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
