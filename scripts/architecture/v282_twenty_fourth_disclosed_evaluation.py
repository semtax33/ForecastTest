from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.evaluation import count_semantic_duplicate_frames
from equity_platform.text_ie.v282 import RULE_PATH, extract_text_kpis_v282
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v282_twenty_fourth_corrected_annotations import ANNOTATIONS
from scripts.architecture.v281_twenty_fourth_holdout_candidates import (
    CANDIDATES,
    CONFIG,
    documents,
    load_config,
    verify_snapshot,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_8_2_upper_context"


@contextmanager
def _development_inputs():
    replacements = {
        "ANNOTATIONS": ANNOTATIONS,
        "CANDIDATES": CANDIDATES,
        "CONFIG": CONFIG,
        "OUTPUT": OUTPUT,
        "documents": documents,
        "load_config": load_config,
        "verify_snapshot": verify_snapshot,
        "extract_text_kpis_v261": extract_text_kpis_v282,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def evaluate_disclosed_twenty_fourth():
    with _development_inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
    duplicate_count = count_semantic_duplicate_frames(json.loads(payload) for payload in detail["actual_frames_json"])
    duplicate_limit = int(dict(load_config()["gates"])["duplicate_auto_emission"])
    summary.loc[:, "duplicate_auto_emission"] = duplicate_count
    summary.loc[:, "duplicate_gate"] = duplicate_count <= duplicate_limit
    gates = ("precision_gate", "recall_gate", "candidate_gate", "table_gate", "duplicate_gate", "cross_clause_gate", "silent_gate")
    passed = all(bool(summary.iloc[0][column]) for column in gates)
    summary.loc[:, "version"] = "PLATFORM_V2_8_2_DISCLOSED_TWENTY_FOURTH"
    summary.loc[:, "status"] = "V282_DISCLOSED_DEVELOPMENT_PASS" if passed else "HOLD_RESEARCH_UNFROZEN"
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_disclosed_twenty_fourth()
    write_csv_artifacts(
        OUTPUT,
        {
            "twenty_fourth_disclosed_evaluation": detail,
            "twenty_fourth_disclosed_summary": summary,
            "twenty_fourth_disclosed_ladder": ladder,
            "twenty_fourth_disclosed_rejection_taxonomy": rejections,
        },
    )
    metadata = {
        "version": "PLATFORM_V2_8_2_DISCLOSED_TWENTY_FOURTH",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "development_holdout_config": CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "candidate_sha256": sha256_file(CANDIDATES),
        "annotation_sha256": sha256_file(ANNOTATIONS),
        "unit_adjudication_applied": True,
        "rule_program": RULE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "rule_program_sha256": sha256_file(RULE_PATH),
        "independent_evidence": False,
        "disclosed_failure_used_for_development": True,
        "parent_v281_immutable": True,
        "hmrb_runtime_dependency": False,
        "llm_backend_used": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "twenty_fourth_disclosed_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
