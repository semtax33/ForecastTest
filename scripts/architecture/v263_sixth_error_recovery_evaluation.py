from __future__ import annotations

from contextlib import contextmanager
import json

import pandas as pd

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v263 import extract_text_kpis_v263
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v262_sixth_holdout_annotations import ANNOTATIONS as FROZEN_ANNOTATIONS
from scripts.architecture.v262_sixth_holdout_candidates import (
    CANDIDATES,
    CONFIG,
    documents,
    load_config as load_frozen_config,
    verify_snapshot,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_6_3_relation_ownership_guards"
CORRECTED_ANNOTATIONS = OUTPUT / "sixth_disclosed_adjudicated_annotations.jsonl"
WRONG_BLOCK = "1a1f511a392b7e927c64"
ORDERS_BLOCK = "2a720b9a69edefb7f939"


def write_adjudicated_annotations() -> None:
    rows = [
        json.loads(line)
        for line in FROZEN_ANNOTATIONS.read_text(encoding="utf-8").splitlines()
        if line
    ]
    misplaced = next(row for row in rows if row["candidate_id"] == WRONG_BLOCK)
    target = next(row for row in rows if row["candidate_id"] == ORDERS_BLOCK)
    target["expected_frames"] = misplaced["expected_frames"]
    target["gold_route"] = "TEXT_IE"
    target["annotation_note"] = "post-blind adjudication: orders frame moved from adjacent block id"
    misplaced["expected_frames"] = []
    misplaced["gold_route"] = "NO_FACT"
    misplaced["annotation_note"] = "post-blind adjudication: removed adjacent-block labeling error"
    for row in rows:
        unique = {}
        for frame in row["expected_frames"]:
            signature = (
                frame["concept"],
                frame["frame"],
                frame["value"],
                frame.get("change"),
                frame.get("polarity", "POSITIVE"),
            )
            unique.setdefault(signature, frame)
        if len(unique) != len(row["expected_frames"]):
            row["annotation_note"] = (
                "post-blind adjudication: semantically identical contribution collapsed "
                "to match the zero-duplicate evaluation contract"
            )
        row["expected_frames"] = list(unique.values())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    CORRECTED_ANNOTATIONS.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def load_adjudicated_config() -> dict[str, object]:
    config = load_frozen_config()
    config["annotation_artifact"] = {
        "path": CORRECTED_ANNOTATIONS.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": sha256_file(CORRECTED_ANNOTATIONS),
    }
    return config


@contextmanager
def _development_inputs():
    replacements = {
        "ANNOTATIONS": CORRECTED_ANNOTATIONS,
        "CANDIDATES": CANDIDATES,
        "CONFIG": CONFIG,
        "OUTPUT": OUTPUT,
        "documents": documents,
        "load_config": load_adjudicated_config,
        "verify_snapshot": verify_snapshot,
        "extract_text_kpis_v261": extract_text_kpis_v263,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def evaluate_disclosed_sixth_set():
    write_adjudicated_annotations()
    with _development_inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
    summary.loc[:, "version"] = "PLATFORM_V2_6_3_SIXTH_DISCLOSED_DEVELOPMENT"
    summary.loc[:, "status"] = "DEVELOPMENT_DIAGNOSTIC_NOT_BLIND"
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_disclosed_sixth_set()
    write_csv_artifacts(
        OUTPUT,
        {
            "sixth_disclosed_evaluation": detail,
            "sixth_disclosed_summary": summary,
            "sixth_disclosed_ladder": ladder,
            "sixth_disclosed_rejection_taxonomy": rejections,
            "sixth_label_adjudication": pd.DataFrame(
                [
                    {
                        "correction": "MOVE_MISALIGNED_FRAME",
                        "from_candidate_id": WRONG_BLOCK,
                        "to_candidate_id": ORDERS_BLOCK,
                    },
                    {
                        "correction": "COLLAPSE_IDENTICAL_CONTRIBUTIONS",
                        "from_candidate_id": "020c87dbd0fa9ec3fdcf|a1eb2d14bc782e8edde3",
                        "to_candidate_id": "ZERO_DUPLICATE_CONTRACT",
                    },
                ]
            ),
        },
    )
    print(f"ADJUDICATED_ANNOTATION_SHA256={sha256_file(CORRECTED_ANNOTATIONS)}")
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
