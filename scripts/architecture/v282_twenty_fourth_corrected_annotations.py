from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v281_twenty_fourth_holdout_annotations import ANNOTATIONS as FROZEN_ANNOTATIONS


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v282_twenty_fourth_corrected_annotations.jsonl"
TARGET = "31a537f6f0f17fd19bfd"


def main() -> int:
    rows = [json.loads(line) for line in FROZEN_ANNOTATIONS.read_text(encoding="utf-8").splitlines() if line]
    changed = 0
    for row in rows:
        if row["candidate_id"] != TARGET:
            continue
        row["expected_frames"].append(
            {
                "concept": "PRIOR_YEAR_REVENUE",
                "frame": "COMPARATIVE",
                "value": 718_500_000.0,
                "tier": "CRITICAL",
            }
        )
        row["annotation_note"] = "adjudicated: explicit prior-year revenue level retained alongside current CHANGE_TO"
        changed += 1
    if changed != 1:
        raise ValueError(f"Expected exactly one corrected row, found {changed}")
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    print(f"ROWS={len(rows)} EXPECTED_FRAMES={sum(len(row['expected_frames']) for row in rows)} CORRECTED={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
