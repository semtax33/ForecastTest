from __future__ import annotations

import json

import pandas as pd

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v276_nineteenth_holdout_annotations import (
    EXPECTED as V276_EXPECTED,
    NOTES as V276_NOTES,
    TABLE_IDS,
    _frame,
)
from scripts.architecture.v276_nineteenth_holdout_candidates import CANDIDATES


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v277_nineteenth_corrected_annotations.jsonl"
)

# Post-prediction errata are isolated from the immutable V2.7.6 independent
# holdout. This artifact is development-only and must never be called blind.
EXPECTED = {
    **V276_EXPECTED,
    "c04ee7d7e8f677207dc7": [
        _frame("REVENUE", "CHANGE_TO", 2_050_000_000.0, change=16.0),
        _frame("REVENUE", "CHANGE_TO", 2_050_000_000.0, change=14.0),
    ],
    "53eaf9e166960c0be53b": [
        _frame("REVENUE_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 5.0),
    ],
}
NOTES = {
    **V276_NOTES,
    "c04ee7d7e8f677207dc7": (
        "ERRATUM: reported and constant-currency changes share the reported level"
    ),
    "53eaf9e166960c0be53b": (
        "ERRATUM: growth-rate guidance uses REVENUE_CHANGE_GUIDANCE"
    ),
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
                    "nineteenth corrected disclosed development annotation",
                ),
            }
        )
    if len(rows) != 100 or len({row["candidate_id"] for row in rows}) != 100:
        raise ValueError("V2.7.7 corrected annotations must cover 100 frozen blocks")
    if set(EXPECTED) & TABLE_IDS:
        raise ValueError("Text facts cannot also be table-only blocks")
    unknown = (set(EXPECTED) | TABLE_IDS) - set(candidates["candidate_id"])
    if unknown:
        raise ValueError(f"Unknown candidate ids: {sorted(unknown)}")
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
