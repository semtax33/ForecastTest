from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v278 import RULE_PATH, extract_text_kpis_v278
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v277_twentieth_holdout_annotations import ANNOTATIONS
from scripts.architecture.v277_twentieth_holdout_candidates import (
    CANDIDATES,
    CONFIG,
    documents,
    load_config,
    verify_snapshot,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_7_8_spacy_semantic_roles"


@contextmanager
def _disclosed_inputs():
    replacements = {
        "ANNOTATIONS": ANNOTATIONS,
        "CANDIDATES": CANDIDATES,
        "CONFIG": CONFIG,
        "OUTPUT": OUTPUT,
        "documents": documents,
        "load_config": load_config,
        "verify_snapshot": verify_snapshot,
        "extract_text_kpis_v261": extract_text_kpis_v278,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def evaluate_twentieth_disclosed():
    with _disclosed_inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
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
    summary.loc[:, "version"] = "PLATFORM_V2_7_8_TWENTIETH_DISCLOSED"
    summary.loc[:, "status"] = (
        "V278_DISCLOSED_DEVELOPMENT_PASS" if passed else "HOLD_RESEARCH_UNFROZEN"
    )
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_twentieth_disclosed()
    write_csv_artifacts(
        OUTPUT,
        {
            "twentieth_disclosed_evaluation": detail,
            "twentieth_disclosed_summary": summary,
            "twentieth_disclosed_ladder": ladder,
            "twentieth_disclosed_rejection_taxonomy": rejections,
        },
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "twentieth_disclosed_metadata.json").write_text(
        json.dumps(
            {
                "version": "PLATFORM_V2_7_8_TWENTIETH_DISCLOSED",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_holdout_config": CONFIG.relative_to(PROJECT_ROOT).as_posix(),
                "candidate_sha256": sha256_file(CANDIDATES),
                "annotation_sha256": sha256_file(ANNOTATIONS),
                "rule_program": RULE_PATH.relative_to(PROJECT_ROOT).as_posix(),
                "rule_program_sha256": sha256_file(RULE_PATH),
                "independent_holdout": False,
                "development_data_disclosed": True,
                "parent_numeric_inheritance": False,
                "hmrb_runtime_dependency": False,
                "llm_backend_used": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
