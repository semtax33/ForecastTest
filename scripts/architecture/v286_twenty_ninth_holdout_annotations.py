from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v286_twenty_ninth_holdout_candidates import CANDIDATES


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v286_twenty_ninth_holdout_annotations.jsonl"


def _frame(concept: str, frame: str, value: float, **extra: object) -> dict[str, object]:
    return {"concept": concept, "frame": frame, "value": value, "tier": "CRITICAL", **extra}


# Exhaustive manual labels frozen before the first V2.8.6 prediction. Financial
# definitions and risk boilerplate are NO_FACT. Dense positional grids are
# TABLE_DSL even when a leading prose sentence is present. Industry activity
# anchors remain in scope even when the current candidate ontology misses them.
EXPECTED = {
    # Alico.
    "ec3f235d1ca8646afd49": [
        _frame("DEBT", "COMPARATIVE", 85_400_000.0),
        _frame("DEBT", "COMPARATIVE", 29_800_000.0),
        _frame("PRIOR_YEAR_DEBT", "COMPARATIVE", 85_500_000.0),
        _frame("PRIOR_YEAR_DEBT", "COMPARATIVE", 47_400_000.0),
    ],
    "3b2b0d29e176a1b49a9e": [
        _frame("ADJUSTED_EBITDA", "COMPARATIVE", 4_600_000.0),
        _frame("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 19_300_000.0),
    ],
    # Allegro MicroSystems.
    "0705f14d983064f64202": [
        _frame("REVENUE", "CHANGE_TO", 259_000_000.0, change=27.0),
    ],
    # Align Technology.
    "91a26ab99c9185c28d48": [
        _frame(
            "REVENUE_CHANGE_GUIDANCE",
            "RANGE_GUIDANCE",
            7.0,
            lower_value=6.0,
            upper_value=8.0,
            polarity="NEGATIVE",
        ),
    ],
    "c307347bfc854b32e056": [
        _frame("REVENUE", "CHANGE_TO", 1_056_200_000.0, change=1.5),
        _frame("REVENUE", "CHANGE_BY", 4.3),
    ],
    "19c7d8b38b18758f836a": [
        _frame("GROSS_MARGIN_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 100.0),
    ],
    "f279c8c885fd07bc68d4": [
        _frame("ACTIVITY_VOLUME_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 6.0),
    ],
    # Allegiant Travel.
    "b434ae1e663d70ecf766": [
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 87_100_000.0),
        _frame("OPERATING_MARGIN", "ABSOLUTE_VALUE", 9.2),
    ],
    "6a9a636db9468c82c2ab": [
        _frame("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 157_700_000.0),
        _frame("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 16.7),
    ],
    # Alignment Healthcare.
    "ce0e9db0e1024921c265": [
        _frame("ACTIVITY_VOLUME", "CHANGE_TO", 294_100.0, change=31.5),
        _frame("REVENUE", "CHANGE_TO", 1_335_600_000.0, change=31.6),
        _frame("OPERATING_INCOME", "ABSOLUTE_VALUE", 42_100_000.0),
    ],
    "b859698e5ebb9217b6eb": [
        _frame("ADJUSTED_EBITDA", "CHANGE_TO", 68_100_000.0, change=48.4),
        _frame("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 5.1),
    ],
    # Alight.
    "684c9f8cc5da79b739d6": [
        _frame(
            "ADJUSTED_EBITDA_GUIDANCE",
            "RANGE_GUIDANCE",
            58_000_000.0,
            lower_value=55_000_000.0,
            upper_value=61_000_000.0,
        ),
    ],
    # Alkermes.
    "dd0ea4d631f301fa42c8": [_frame("REVENUE", "ABSOLUTE_VALUE", 27_500_000.0)],
    "40583ba5f8752440e594": [_frame("REVENUE", "ABSOLUTE_VALUE", 96_700_000.0)],
    "58dd20d6c882a6eddbbf": [_frame("REVENUE", "ABSOLUTE_VALUE", 4_000_000.0)],
    "2aa3205cce431b39d360": [
        _frame("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 169_100_000.0),
        _frame("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 172_800_000.0),
    ],
    "b6b019924e65e28267d2": [_frame("REVENUE", "ABSOLUTE_VALUE", 124_500_000.0)],
    "17570922295da22ccdc7": [_frame("REVENUE", "ABSOLUTE_VALUE", 30_600_000.0)],
    # Alkami Technology.
    "1f0d4e153edba256b8c3": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            133_450_000.0,
            lower_value=132_700_000.0,
            upper_value=134_200_000.0,
        ),
    ],
    "cae7ee002aca0628b4c0": [
        _frame("GROSS_MARGIN", "COMPARATIVE", 63.0),
        _frame("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 65.1),
    ],
    # Ally Financial.
    "127c4b9d13c6f540bc55": [
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 13_300_000_000.0),
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 8_300_000_000.0),
        _frame("ACTIVITY_VOLUME", "COMPOSITION", 63.0),
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 4_200_000_000.0),
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 739_000_000.0),
    ],
    "f77da9810e2d0374aee8": [
        _frame("REVENUE", "CHANGE_TO", 1_300_000_000.0, change=22_000_000.0),
    ],
    "748fcb1bcfae17b6ecce": [
        _frame("ACTIVITY_VOLUME", "CHANGE_TO", 13_000_000_000.0, change=21.0),
    ],
    # Alarm.com.
    "21f165c6c8494698cfdb": [
        _frame(
            "REVENUE_GUIDANCE",
            "RANGE_GUIDANCE",
            754_200_000.0,
            lower_value=754_000_000.0,
            upper_value=754_400_000.0,
        ),
        _frame("REVENUE_GUIDANCE", "CHANGE_BY", 10_200_000.0),
    ],
    "af1d32dc8fa1df26f7bc": [
        _frame("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 304.0),
    ],
}


TABLE_IDS = {
    "3ec7785420f2ad53c86d", "a2094de06ed570142baa", "3f284618f67fbf988e65",  # ALCO
    "671c0a4c1bcbc1ee3dee", "25aeecc4c3008e89ee42", "c6ddb02eb2e30c21feee", "ed884559d7a4ec4d3ce2",  # ALGM
    "2287038d0e67606ef1e0",  # ALGN
    "7818543604167055e744",  # ALGT
    "d356b97d20a6df31f4fc", "06725895f6cbcebbc996", "7b57ea1830ad301d4a91",  # ALHC
    "92dded22b08d30a7400e",  # ALIT
    "977d91e2aee6fa067587", "c246ffd176b3bb8e9eca",  # ALKS
    "cfab69babdc65fbdb54c", "44ca6f6d1d9c39f6871b", "21f8239277d9a0c3b7b2",  # ALKT
    "d28e4c263ecdb9c3909a",  # ALLY
    "c7b5e3ca7f3cc22830cd", "15128966456ff3d7c53c",  # ALRM
}


NOTES = {
    "ce0e9db0e1024921c265": "prose KPI highlights, not a positional table",
    "977d91e2aee6fa067587": "cash sentence is fused to a dense expectations grid; route the full block to TABLE_DSL",
    "44ca6f6d1d9c39f6871b": "two-period cash-flow rows are positional table evidence",
    "af1d32dc8fa1df26f7bc": "demand-response event count is an industry activity anchor even though current aliases miss it",
    "127c4b9d13c6f540bc55": "total originations and explicitly owned used/new/lease components are separate activity facts",
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
                "exhaustive manual twenty-ninth annotation before prediction",
            ),
        })
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.8.6 twenty-ninth holdout must cover 100 unique blocks")
    overlap = set(EXPECTED) & TABLE_IDS
    if overlap:
        raise ValueError(f"Text facts cannot also be table-only blocks: {sorted(overlap)}")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown twenty-ninth candidate ids: {sorted(unknown)}")
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
