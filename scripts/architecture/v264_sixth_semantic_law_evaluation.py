from __future__ import annotations

from contextlib import contextmanager
import json

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v264 import RULE_PATH, extract_text_kpis_v264
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v262_sixth_holdout_candidates import (
    CANDIDATES,
    CONFIG,
    documents,
    load_config as load_frozen_config,
    verify_snapshot,
)
from scripts.architecture.v263_sixth_error_recovery_evaluation import (
    CORRECTED_ANNOTATIONS,
    write_adjudicated_annotations,
)


OUTPUT = PROJECT_ROOT / "output/platform_v2_6_4_spacy_semantic_laws"


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
        "extract_text_kpis_v261": extract_text_kpis_v264,
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
    summary.loc[:, "version"] = "PLATFORM_V2_6_4_SPACY_SEMANTIC_LAWS"
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
        },
    )
    metadata = {
        "version": "PLATFORM_V2_6_4_SPACY_SEMANTIC_LAWS",
        "status": "DEVELOPMENT_DIAGNOSTIC_NOT_BLIND",
        "core_dependency": "spaCy",
        "hmrb_dependency": False,
        "hmrb_inspiration": [
            "Law/Var",
            "nested token predicates",
            "labeled roles",
            "bounded optional/repetition",
            "registered pure operations",
        ],
        "rule_program": RULE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "rule_program_sha256": sha256_file(RULE_PATH),
        "annotation_sha256": sha256_file(CORRECTED_ANNOTATIONS),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
