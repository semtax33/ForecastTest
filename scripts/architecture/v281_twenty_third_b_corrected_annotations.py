from __future__ import annotations

import json

from equity_platform.paths import PROJECT_ROOT
from scripts.architecture.v280_twenty_third_b_holdout_annotations import (
    ANNOTATIONS as FROZEN_ANNOTATIONS,
)


ANNOTATIONS = (
    PROJECT_ROOT
    / "data-lake/gold/parser/text_ie/v281_twenty_third_b_corrected_annotations.jsonl"
)
CORRECTED_ID = "7b40ae1be283df4dfd27"


def main() -> int:
    rows = [
        json.loads(line)
        for line in FROZEN_ANNOTATIONS.read_text(encoding="utf-8").splitlines()
        if line
    ]
    corrected = 0
    for row in rows:
        if row["candidate_id"] != CORRECTED_ID:
            continue
        for frame in row["expected_frames"]:
            if frame["concept"] not in {"PRODUCTION_GUIDANCE", "ACTIVITY_VOLUME_GUIDANCE"}:
                continue
            for key in ("value", "lower_value", "upper_value"):
                frame[key] = float(frame[key]) * 1_000_000.0
            corrected += 1
        row["annotation_note"] = (
            "V281 adjudication: million metric tons normalized to base metric tons; "
            "the frozen V280 annotation remains immutable"
        )
    if len(rows) != 100 or corrected != 2:
        raise ValueError(f"Expected 100 rows and 2 unit corrections, got {len(rows)}, {corrected}")
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(f"ROWS={len(rows)} UNIT_CORRECTIONS={corrected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

