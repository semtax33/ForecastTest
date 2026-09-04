from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v265 import RULE_PATH, extract_text_kpis_v265
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v264_seventh_holdout_annotations import ANNOTATIONS
from scripts.architecture.v264_seventh_holdout_candidates import (
    CANDIDATES,
    CONFIG,
    documents,
    load_config,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_6_5_spacy_semantic_recovery"


@contextmanager
def _development_inputs():
    replacements = {
        "ANNOTATIONS": ANNOTATIONS,
        "CANDIDATES": CANDIDATES,
        "CONFIG": CONFIG,
        "OUTPUT": OUTPUT,
        "documents": documents,
        "load_config": load_config,
        "verify_snapshot": lambda config: None,
        "extract_text_kpis_v261": extract_text_kpis_v265,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def evaluate_disclosed_seventh_set():
    with _development_inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
    summary.loc[:, "version"] = "PLATFORM_V2_6_5_SEVENTH_DISCLOSED_DEVELOPMENT"
    summary.loc[:, "status"] = "DEVELOPMENT_DIAGNOSTIC_NOT_BLIND"
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_disclosed_seventh_set()
    write_csv_artifacts(
        OUTPUT,
        {
            "seventh_disclosed_evaluation": detail,
            "seventh_disclosed_summary": summary,
            "seventh_disclosed_ladder": ladder,
            "seventh_disclosed_rejection_taxonomy": rejections,
        },
    )
    metadata = {
        "version": "PLATFORM_V2_6_5_SEVENTH_DISCLOSED_DEVELOPMENT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_candidate_sha256": sha256_file(CANDIDATES),
        "source_annotation_sha256": sha256_file(ANNOTATIONS),
        "rule_program": RULE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "rule_program_sha256": sha256_file(RULE_PATH),
        "status": "DEVELOPMENT_DIAGNOSTIC_NOT_BLIND",
        "hmrb_runtime_dependency": False,
        "llm_backend_used": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "seventh_disclosed_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
