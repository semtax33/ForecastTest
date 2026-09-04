from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v271 import RULE_PATH, extract_text_kpis_v271
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v270_thirteenth_holdout_annotations import ANNOTATIONS
from scripts.architecture.v270_thirteenth_holdout_candidates import CANDIDATES, CONFIG, documents, load_config


OUTPUT = PROJECT_ROOT / "output/platform_v2_7_1_spacy_semantic_ownership"


def _development_snapshot(_: dict[str, object]) -> None:
    """V270 holdout inputs stay frozen; V271 is intentionally under development."""


@contextmanager
def _inputs():
    replacements = {
        "ANNOTATIONS": ANNOTATIONS,
        "CANDIDATES": CANDIDATES,
        "CONFIG": CONFIG,
        "OUTPUT": OUTPUT,
        "documents": documents,
        "load_config": load_config,
        "verify_snapshot": _development_snapshot,
        "extract_text_kpis_v261": extract_text_kpis_v271,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def evaluate_thirteenth_disclosed():
    with _inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
    gates = (
        "precision_gate", "recall_gate", "candidate_gate", "table_gate",
        "duplicate_gate", "cross_clause_gate", "silent_gate",
    )
    passed = all(bool(summary.iloc[0][column]) for column in gates)
    summary.loc[:, "version"] = "PLATFORM_V2_7_1_THIRTEENTH_DISCLOSED_DEVELOPMENT"
    summary.loc[:, "status"] = (
        "V271_DISCLOSED_DEVELOPMENT_PASS" if passed else "HOLD_RESEARCH_UNFROZEN"
    )
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_thirteenth_disclosed()
    write_csv_artifacts(
        OUTPUT,
        {
            "thirteenth_disclosed_evaluation": detail,
            "thirteenth_disclosed_summary": summary,
            "thirteenth_disclosed_ladder": ladder,
            "thirteenth_disclosed_rejection_taxonomy": rejections,
        },
    )
    metadata = {
        "version": "PLATFORM_V2_7_1_THIRTEENTH_DISCLOSED_DEVELOPMENT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_sha256": sha256_file(CANDIDATES),
        "annotation_sha256": sha256_file(ANNOTATIONS),
        "rule_program": RULE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "rule_program_sha256": sha256_file(RULE_PATH),
        "holdout_disclosed_before_v271_changes": True,
        "hmrb_runtime_dependency": False,
        "llm_backend_used": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "thirteenth_disclosed_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
