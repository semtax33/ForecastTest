from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v266_ninth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v266_ninth_holdout_annotations.jsonl"
)


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {
        "concept": concept,
        "frame": frame,
        "value": value,
        "tier": "CRITICAL",
        **extra,
    }


# Exhaustive manual labels frozen before any V2.6.6 prediction is run.
EXPECTED = {
    "433dd7f8487a0d53e0a2": [
        _frame("REVENUE", "CHANGE_TO", 145_000_000.0, change=38.0),
    ],
    "bfb3ceb283e49ae3b959": [
        _frame("REVENUE", "CHANGE_BY", 6.0),
        _frame("REVENUE", "CHANGE_BY", 8.0),
    ],
    "33a8f85e30d193532423": [
        _frame("REVENUE", "CHANGE_BY", 1.0),
        _frame("REVENUE", "CHANGE_BY", 23.0),
    ],
    "7b4164032cc143857e1a": [
        _frame("REVENUE", "CHANGE_TO", 3_940_000_000.0, change=10.0),
    ],
    "3763287a3a26cc341c2e": [
        _frame("REVENUE", "CHANGE_BY", 15_000_000.0, polarity="NEGATIVE"),
    ],
    "97d1a69684dd10268e6e": [
        _frame("CAPEX", "ABSOLUTE_VALUE", 1_400_000_000.0),
    ],
    "bcc6af605b9424ef7836": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 1_600_000_000.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 8.8),
    ],
    "88f8cc3d26df44fac9ca": [
        _frame("REVENUE", "CHANGE_BY", 24.0),
        _frame("REVENUE", "CHANGE_BY", 82.0),
    ],
    "c3dd1e76143bc9943251": [
        _frame("REVENUE", "CHANGE_TO", 4_800_000_000.0, change=45.0),
    ],
    "2cda6ee358fbbda9bc81": [
        _frame("REVENUE", "CHANGE_TO", 9_900_000_000.0, change=91.0),
    ],
    "1dee05d676f092d5763b": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "ABSOLUTE_VALUE",
            1.0,
            polarity="NEGATIVE",
        ),
    ],
    "052ecbb0b9a91b615932": [
        _frame("CASH", "ABSOLUTE_VALUE", 90_260_000_000.0),
    ],
    "7edccd1b300da0b418ec": [
        _frame(
            "CAPEX_GUIDANCE",
            "RANGE_GUIDANCE",
            137_500_000_000.0,
            lower_value=130_000_000_000.0,
            upper_value=145_000_000_000.0,
        ),
    ],
    "499a365a3af9ba2c6861": [
        _frame("REVENUE", "COMPARATIVE", 359_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 335_000_000.0),
        _frame("REVENUE", "CHANGE_BY", 7.0),
        _frame("REVENUE", "CHANGE_BY", 4.0),
    ],
    "57d901210bd05068eb0e": [
        _frame("REVENUE", "COMPARATIVE", 161_000_000.0),
        _frame("REVENUE", "COMPARATIVE", 10_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 44_000_000.0),
        _frame("PRIOR_YEAR_REVENUE", "COMPARATIVE", 43_000_000.0),
    ],
    "2bbd7a8e8d8612af155f": [
        _frame("OPERATING_MARGIN", "CHANGE_BY", 220.0, polarity="NEGATIVE"),
    ],
    "5124b3a7c1d2b1fe541a": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            2.0,
            lower_value=1.0,
            upper_value=3.0,
        ),
    ],
    "3779aac6dd49a66f8bb6": [
        _frame(
            "ADJUSTED_EBITDA_GUIDANCE",
            "RANGE_GUIDANCE",
            3_570_000_000.0,
            lower_value=3_490_000_000.0,
            upper_value=3_650_000_000.0,
        ),
    ],
    "e481d9ea5bb11053dd8f": [
        _frame(
            "OPERATING_INCOME",
            "CHANGE_TO",
            400_000_000.0,
            change=57.0,
            polarity="NEGATIVE",
        ),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 1.4),
    ],
    "94e08b21e03409719f8a": [
        _frame("REVENUE", "ABSOLUTE_VALUE", 100_000_000_000.0),
    ],
    "c31ec7258c84795b7e83": [
        _frame("GROSS_MARGIN", "ABSOLUTE_VALUE", 14.0),
    ],
}


TABLE_IDS = {
    "2ffc55dbc1b34a9671a2",
    "7b5d544ff42a81813a35",
    "8c75194325b6c1dd0bba",
    "f0898f559519ca7bbb51",
    "40173e7751339905e5a1",
    "f7352e5e477f671264dd",
    "bdceb949bcec3a44343b",
    "154b9477b0e7d4bd5752",
    "d688abfbf90f454b62a0",
    "2b9de0553bfd0aa1de89",
    "9e88b606b0e931397f96",
    "a7ad6a41878870b9ef0b",
    "1f6ffc3595ce7bc80f36",
    "06f2dbce29f04980afaf",
    "28f34e3cd9a3bf8ab737",
    "e3b5f15c91bef1d87857",
    "2b8e046cf6e5efff584e",
    "3bacb30cd4b74dd00afd",
    "040f7e92da68c46c42f1",
    "5fc076d6b479fd74a0ea",
}


NOTES = {
    "c8b6af7d17baa2956a51": "EBITDA amounts and margins are not revenue facts",
    "97d1a69684dd10268e6e": "operating cash flow and FCF are not cash balances; capex is explicit",
    "6abdf1ee98f3313ad762": "liquidity includes an undrawn revolver and is not a cash balance",
    "d290419c8f8fd9340030": "capital-raise proceeds intended partly for capex are not capex",
    "f5cf838b5871fbb47ed9": "R&D expense and its percent of revenue are not revenue",
    "752c1d2076fac8abb08b": "narrative methodology notes, not a financial grid or direct KPI fact",
    "2fa2073c7471cd845124": "operating/free cash flow are not cash-balance facts",
    "879e2d4b13222d344b41": "debt proceeds and dividends are not cash-balance facts",
    "971ce64067da2a0f1fae": "numeric value belongs to EPS, not revenue or margin",
    "b87bb4c2b794157b1c21": "percentage is FSD attach rate, not deliveries volume",
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
                    "exhaustive manual ninth-holdout annotation before prediction review",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.6.6 ninth holdout must cover 100 unique frozen blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown ninth-holdout candidate ids: {sorted(unknown)}")
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
