from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v289_thirty_second_holdout_candidates import CANDIDATES


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v289_thirty_second_holdout_annotations.jsonl"


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


# Exhaustive manual labels frozen before the first V2.8.9 prediction on this
# issuer/document-disjoint sample.  Operating cash flow is not a CASH balance;
# transaction prices, credit spreads and acquisition-target sales are not
# issuer revenue.  Economically meaningful activity anchors remain in scope
# even where candidate concept tagging missed their surface form.
EXPECTED = {
    # AutoNation.
    "a33de4d53a4babded4f7": [_frame("CASH", "ABSOLUTE_VALUE", 53_000_000.0)],
    "daf7665ef06c14951d3c": [_frame("CAPEX", "ABSOLUTE_VALUE", 126_000_000.0)],
    "c52a8dd4da7ebf9d0367": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 600_000_000.0),
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 9_700.0),
    ],
    "af03222d99a2f2b759cb": [
        _frame("SHARES", "CHANGE_BY", 6.0, polarity="NEGATIVE"),
        _frame("REVENUE", "CHANGE_TO", 6_900_000_000.0, change=1.0, polarity="NEGATIVE"),
    ],
    # AnaptysBio.
    "4bd350031424682633c7": [_frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 95.0)],
    "f6f311afa178c34b3cf1": [
        _frame("CASH", "CHANGE_TO", 286_500_000.0, change=25_100_000.0, polarity="NEGATIVE"),
    ],
    "fb2f95eaa634ac96fb10": [_frame("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 390_000_000.0)],
    "9f85eefd9c162c79e454": [_frame("REVENUE", "CHANGE_TO", 24_700_000.0, change=44.0)],
    # The Andersons.
    "4c47ce3efc6442565c00": [
        _frame("ADJUSTED_EBITDA", "COMPARATIVE", 53_000_000.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 46_000_000.0),
    ],
    "f968db457d611e1bfee0": [
        _frame("ADJUSTED_EBITDA", "COMPARATIVE", 103_000_000.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 30_000_000.0),
    ],
    # Andersen Group.
    "19d0ebc55e48079f70c5": [
        _frame("REVENUE", "CHANGE_TO", 217_700_000.0, change=23.7),
    ],
    # Angi.
    "19564abaa9f0200c0612": [_frame("REVENUE", "CHANGE_BY", 11.0, polarity="NEGATIVE")],
    # AngioDynamics.
    "93c2b628a514c42b9adf": [
        _frame("REVENUE", "CHANGE_TO", 150_000_000.0, change=18.4),
    ],
    "66ff5302dd02beb63931": [
        _frame("GROSS_MARGIN", "CHANGE_TO", 54.0, change=130.0),
    ],
    "84622e5a826857154252": [
        _frame("REVENUE", "CHANGE_TO", 11_800_000.0, change=64.5),
        _frame("REVENUE", "CHANGE_BY", 47.0),
        _frame("REVENUE", "CHANGE_BY", 132.5),
    ],
    "b64336a0ed8c49243311": [
        _frame("REVENUE", "COMPOSITION", 47.0),
        _frame("REVENUE", "CHANGE_BY", 22.0),
    ],
    # Angel Studios.
    "0b5026b6ec060f192101": [_frame("ACTIVITY_VOLUME", "CHANGE_BY", 99.2)],
    "ae07b66e78113b1125a7": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 54.0),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 69.0),
    ],
    "8a4a3ba191e4d2c6fb59": [
        _frame("ACTIVITY_VOLUME", "CHANGE_TO", 390_000.0, change=69.6),
    ],
    "9b9af6b701dce23067a1": [
        _frame("ADJUSTED_EBITDA", "COMPARATIVE", 7_700_000.0, polarity="NEGATIVE"),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 46_200_000.0, polarity="NEGATIVE"),
    ],
    "1490479610bf5226b357": [
        _frame("CASH", "COMPARATIVE", 48_000_000.0),
        _frame("PRIOR_YEAR_CASH", "COMPARATIVE", 44_100_000.0),
        _frame("PRIOR_YEAR_CASH", "COMPARATIVE", 28_000_000.0),
    ],
    # ANI Pharmaceuticals.
    "b5e11c26b9b0b8f08da1": [
        _frame("CASH", "ABSOLUTE_VALUE", 360_200_000.0),
        _frame("DEBT", "ABSOLUTE_VALUE", 620_900_000.0),
    ],
    "3a666f90b95fb1b8e644": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            1_110_000_000.0,
            lower_value=1_080_000_000.0,
            upper_value=1_140_000_000.0,
        ),
        _frame(
            "ADJUSTED_EBITDA_GUIDANCE",
            "RANGE_GUIDANCE",
            292_500_000.0,
            lower_value=285_000_000.0,
            upper_value=300_000_000.0,
        ),
    ],
    "2c4348b6e8425149400c": [
        _frame("REVENUE", "CHANGE_TO", 99_100_000.0, change=9.7),
    ],
    "125816fff06c48adc3b3": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 8_000_000.0),
        _frame("REVENUE", "ABSOLUTE_VALUE", 9_700_000.0),
    ],
    # Amphenol.
    "2df9c4a78882f259c039": [
        _frame("REVENUE", "CHANGE_TO", 8_800_000_000.0, change=55.0),
    ],
    # Apple Hospitality.
    "8f81117e8e7e2b20c8a8": [_frame("REVENUE", "CHANGE_BY", 5.0)],
    "cb88e40adc0ace9c6b42": [_frame("CAPEX", "CHANGE_BY", 5_000_000.0)],
    "e48e3517faaa4d228fc8": [
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 216.0),
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 29_459.0),
    ],
}


TABLE_IDS = {
    "1eff1611f01f304ea7e2", "1d609775bdfa1f656414", "d49d300d8c28987ac0f3", "39f6e9ba1899be79216f",  # AN
    "2f5935ad423075c37884", "25a5153e5ae3a5070c21",  # ANAB
    "a30d8b623697280ad16e",  # ANDE
    "bdabaf724edac90776b6", "3585029afcdf43d0676c",  # ANDG
    "bf5405bb06f6ea5f2480", "68f065edb1eea8541f00", "df55e921e7b2b729b8ca",  # ANGI
    "46098bf2a19edddc489d", "5042ad275316c467d991", "49c6a6f66b1989926d57", "54cf24afdadf391dea8a",  # ANGO
    "7984257a7bbd63d27d99", "cc6c154b1db286b4cdd7",  # ANGX
    "76f34e2dac1605e87892", "a2ec26f5308b92e822c5",  # ANIP
    "07220f6c1ce680f20079", "0bec96a13f2cc4aec6e4",  # APH
    "2362279ae71d2c95496e",  # APLE
}


NOTES = {
    "daf7665ef06c14951d3c": "narrative capital-allocation sentence was sampled as a table; only CAPEX is in the critical ontology",
    "bf5405bb06f6ea5f2480": "dense financial statements are TABLE_DSL despite inherited prose routing",
    "0bec96a13f2cc4aec6e4": "flattened net-sales table header fragment is TABLE_DSL despite having no numeric payload",
    "19564abaa9f0200c0612": "parenthesized year-over-year decline is an explicit revenue change despite candidate quantity miss",
    "0b5026b6ec060f192101": "the stated percentage belongs to paying membership activity, not revenue",
    "8a4a3ba191e4d2c6fb59": "membership count and growth form the activity anchor; expense ratios and operating cash flow are out of scope",
    "1490479610bf5226b357": "current cash is explicitly compared with two dated historical balances",
    "5b76b02de9bd4b960645": "annual sales belong to an acquisition target, not the issuer",
    "6d566b4f71cc15c86f46": "SOFR credit spread is financing pricing, not operating PRICE_REALIZATION",
    "985bf2fe5971bdfd6bfa": "hotel disposition sales price is not operating revenue",
    "e48e3517faaa4d228fc8": "owned hotels and rooms are lodging capacity/activity anchors",
}


def main() -> int:
    candidates = pd.read_csv(CANDIDATES)
    rows = []
    for item in candidates.itertuples(index=False):
        expected = EXPECTED.get(item.candidate_id, [])
        route = "TABLE_DSL" if item.candidate_id in TABLE_IDS else "TEXT_IE" if expected else "NO_FACT"
        rows.append({
            "candidate_id": item.candidate_id,
            "ticker": item.ticker,
            "gold_route": route,
            "expected_frames": expected,
            "annotation_note": NOTES.get(
                item.candidate_id,
                "exhaustive manual thirty-second annotation before first V2.8.9 prediction",
            ),
        })
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.8.9 thirty-second holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown thirty-second candidate ids: {sorted(unknown)}")
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    expected_count = sum(len(row["expected_frames"]) for row in rows)
    print(f"ANNOTATED={len(rows)} EXPECTED_FRAMES={expected_count} TABLE_BLOCKS={len(TABLE_IDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
