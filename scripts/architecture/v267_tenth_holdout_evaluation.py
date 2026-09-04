from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v267 import RULE_PATH, extract_text_kpis_v267
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v267_tenth_holdout_annotations import ANNOTATIONS
from scripts.architecture.v267_tenth_holdout_candidates import (
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
        "extract_text_kpis_v261": extract_text_kpis_v267,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def evaluate_tenth_holdout():
    with _frozen_inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
    passed = all(
        bool(summary.iloc[0][column])
        for column in (
            "precision_gate",
            "recall_gate",
            "candidate_gate",
            "table_gate",
            "duplicate_gate",
            "cross_clause_gate",
            "silent_gate",
        )
    )
    summary.loc[:, "version"] = "PLATFORM_V2_6_7_TENTH_DISJOINT_HOLDOUT"
    summary.loc[:, "status"] = (
        "V267_RESEARCH_BENCHMARK_PASS" if passed else "HOLD_RESEARCH_UNFROZEN"
    )
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_tenth_holdout()
    write_csv_artifacts(
        OUTPUT,
        {
            "tenth_holdout_evaluation": detail,
            "tenth_holdout_summary": summary,
            "tenth_holdout_ladder": ladder,
            "tenth_holdout_rejection_taxonomy": rejections,
        },
    )
    metadata = {
        "version": "PLATFORM_V2_6_7_TENTH_DISJOINT_HOLDOUT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "holdout_config": CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "candidate_sha256": sha256_file(CANDIDATES),
        "annotation_sha256": sha256_file(ANNOTATIONS),
        "rule_program": RULE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "rule_program_sha256": sha256_file(RULE_PATH),
        "semantic_rule_changes_after_selection": False,
        "semantic_rule_changes_after_annotation": False,
        "hmrb_runtime_dependency": False,
        "llm_backend_used": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "tenth_holdout_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
