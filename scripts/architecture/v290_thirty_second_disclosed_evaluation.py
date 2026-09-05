from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.evaluation import count_semantic_duplicate_frames
from equity_platform.text_ie.v290 import RULE_PATH, extract_text_kpis_v290
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v289_thirty_second_holdout_annotations import ANNOTATIONS
from scripts.architecture.v289_thirty_second_holdout_candidates import (
    CANDIDATES,
    CONFIG,
    documents,
    load_config,
    verify_snapshot,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_9_0_semantic_role_graph"


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
        "extract_text_kpis_v261": extract_text_kpis_v290,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def evaluate_thirty_second_disclosed():
    with _frozen_inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
    duplicate_count = count_semantic_duplicate_frames(
        json.loads(payload) for payload in detail["actual_frames_json"]
    )
    duplicate_limit = int(dict(load_config()["gates"])["duplicate_auto_emission"])
    summary.loc[:, "duplicate_auto_emission"] = duplicate_count
    summary.loc[:, "duplicate_gate"] = duplicate_count <= duplicate_limit
    gates = (
        "precision_gate", "recall_gate", "candidate_gate", "table_gate",
        "duplicate_gate", "cross_clause_gate", "silent_gate",
    )
    passed = all(bool(summary.iloc[0][column]) for column in gates)
    summary.loc[:, "version"] = "PLATFORM_V2_9_0_THIRTY_SECOND_DISCLOSED_REMEDIATION"
    summary.loc[:, "status"] = "V290_DISCLOSED_REMEDIATION_PASS" if passed else "HOLD_RESEARCH_UNFROZEN"
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_thirty_second_disclosed()
    write_csv_artifacts(OUTPUT, {
        "thirty_second_disclosed_evaluation": detail,
        "thirty_second_disclosed_summary": summary,
        "thirty_second_disclosed_ladder": ladder,
        "thirty_second_disclosed_rejection_taxonomy": rejections,
    })
    metadata = {
        "version": "PLATFORM_V2_9_0_THIRTY_SECOND_DISCLOSED_REMEDIATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "holdout_config": CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "candidate_sha256": sha256_file(CANDIDATES),
        "annotation_sha256": sha256_file(ANNOTATIONS),
        "rule_program": RULE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "rule_program_sha256": sha256_file(RULE_PATH),
        "issuer_document_disjoint": True,
        "annotations_frozen_before_v289_prediction": True,
        "disclosed_v289_failure_set": True,
        "semantic_rule_changes_after_v289_failure": True,
        "parent_numeric_inheritance": False,
        "hmrb_runtime_dependency": False,
        "llm_backend_used": False,
        "uses_hierarchical_context": True,
        "hierarchical_context_numeric_inheritance": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "thirty_second_disclosed_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
