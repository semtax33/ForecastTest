from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v270 import RULE_PATH, extract_text_kpis_v270
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v269_twelfth_holdout_annotations import ANNOTATIONS
from scripts.architecture.v269_twelfth_holdout_candidates import CANDIDATES, CONFIG, documents, load_config


OUTPUT = PROJECT_ROOT / "output/platform_v2_7_0_spacy_semantic_ownership"


def _development_snapshot(_: dict[str, object]) -> None:
    """V269 inputs stay frozen; V270 is intentionally under development."""


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
        "extract_text_kpis_v261": extract_text_kpis_v270,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def evaluate_twelfth_disclosed():
    with _inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
    gates = ("precision_gate", "recall_gate", "candidate_gate", "table_gate", "duplicate_gate", "cross_clause_gate", "silent_gate")
    passed = all(bool(summary.iloc[0][column]) for column in gates)
    summary.loc[:, "version"] = "PLATFORM_V2_7_0_TWELFTH_DISCLOSED_DEVELOPMENT"
    summary.loc[:, "status"] = "V270_DISCLOSED_DEVELOPMENT_PASS" if passed else "HOLD_RESEARCH_UNFROZEN"
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_twelfth_disclosed()
    write_csv_artifacts(
        OUTPUT,
        {
            "twelfth_disclosed_evaluation": detail,
            "twelfth_disclosed_summary": summary,
            "twelfth_disclosed_ladder": ladder,
            "twelfth_disclosed_rejection_taxonomy": rejections,
        },
    )
    metadata = {
        "version": "PLATFORM_V2_7_0_TWELFTH_DISCLOSED_DEVELOPMENT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_sha256": sha256_file(CANDIDATES),
        "annotation_sha256": sha256_file(ANNOTATIONS),
        "rule_program": RULE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "rule_program_sha256": sha256_file(RULE_PATH),
        "holdout_disclosed_before_v270_changes": True,
        "hmrb_runtime_dependency": False,
        "llm_backend_used": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "twelfth_disclosed_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
