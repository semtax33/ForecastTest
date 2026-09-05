from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.evaluation import count_semantic_duplicate_frames
from equity_platform.text_ie.v281 import RULE_PATH, extract_text_kpis_v281
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v281_twenty_fourth_holdout_annotations import ANNOTATIONS
from scripts.architecture.v281_twenty_fourth_holdout_candidates import (
    CANDIDATES,
    CONFIG,
    OUTPUT,
    documents,
    load_config,
    verify_snapshot,
)


@contextmanager
def _frozen_inputs():
    replacements = {
        "ANNOTATIONS": ANNOTATIONS,
        "CANDIDATES": CANDIDATES,
        "CONFIG": CONFIG,
        "OUTPUT": OUTPUT,
        "documents": documents,
        "load_config": load_config,
        "verify_snapshot": verify_snapshot,
        "extract_text_kpis_v261": extract_text_kpis_v281,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def evaluate_twenty_fourth_holdout():
    with _frozen_inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
    duplicate_count = count_semantic_duplicate_frames(
        json.loads(payload) for payload in detail["actual_frames_json"]
    )
    duplicate_limit = int(dict(load_config()["gates"])["duplicate_auto_emission"])
    summary.loc[:, "duplicate_auto_emission"] = duplicate_count
    summary.loc[:, "duplicate_gate"] = duplicate_count <= duplicate_limit
    gate_columns = (
        "precision_gate",
        "recall_gate",
        "candidate_gate",
        "table_gate",
        "duplicate_gate",
        "cross_clause_gate",
        "silent_gate",
    )
    passed = all(bool(summary.iloc[0][column]) for column in gate_columns)
    summary.loc[:, "version"] = "PLATFORM_V2_8_1_TWENTY_FOURTH_DISJOINT_HOLDOUT"
    summary.loc[:, "status"] = (
        "V281_INDEPENDENT_RESEARCH_BENCHMARK_PASS"
        if passed
        else "HOLD_RESEARCH_UNFROZEN"
    )
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_twenty_fourth_holdout()
    write_csv_artifacts(
        OUTPUT,
        {
            "twenty_fourth_holdout_evaluation": detail,
            "twenty_fourth_holdout_summary": summary,
            "twenty_fourth_holdout_ladder": ladder,
            "twenty_fourth_holdout_rejection_taxonomy": rejections,
        },
    )
    metadata = {
        "version": "PLATFORM_V2_8_1_TWENTY_FOURTH_DISJOINT_HOLDOUT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "holdout_config": CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "candidate_sha256": sha256_file(CANDIDATES),
        "annotation_sha256": sha256_file(ANNOTATIONS),
        "rule_program": RULE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "rule_program_sha256": sha256_file(RULE_PATH),
        "issuer_document_disjoint": True,
        "annotations_frozen_before_prediction": True,
        "semantic_rule_changes_after_selection": False,
        "semantic_rule_changes_after_annotation": False,
        "parent_numeric_inheritance": False,
        "hmrb_runtime_dependency": False,
        "llm_backend_used": False,
        "uses_hierarchical_context": True,
    }
    (OUTPUT / "twenty_fourth_holdout_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
