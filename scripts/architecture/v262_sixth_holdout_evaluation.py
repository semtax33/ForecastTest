from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v262 import extract_text_kpis_v262
import scripts.architecture.v261_fifth_holdout_evaluation as scoring
from scripts.architecture.v262_sixth_holdout_annotations import ANNOTATIONS
from scripts.architecture.v262_sixth_holdout_candidates import (
    CANDIDATES,
    CONFIG,
    OUTPUT,
    documents,
    load_config,
    verify_snapshot,
)


@contextmanager
def _sixth_holdout_inputs():
    replacements = {
        "ANNOTATIONS": ANNOTATIONS,
        "CANDIDATES": CANDIDATES,
        "CONFIG": CONFIG,
        "OUTPUT": OUTPUT,
        "documents": documents,
        "load_config": load_config,
        "verify_snapshot": verify_snapshot,
        "extract_text_kpis_v261": extract_text_kpis_v262,
    }
    prior = {name: getattr(scoring, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(scoring, name, value)
        yield
    finally:
        for name, value in prior.items():
            setattr(scoring, name, value)


def evaluate_sixth_holdout():
    with _sixth_holdout_inputs():
        detail, summary, ladder, rejections = scoring.evaluate_fifth_holdout()
    summary.loc[:, "version"] = "PLATFORM_V2_6_2_SIXTH_DISJOINT_HOLDOUT"
    gates = [
        "precision_gate",
        "recall_gate",
        "candidate_gate",
        "table_gate",
        "duplicate_gate",
        "cross_clause_gate",
        "silent_gate",
    ]
    summary.loc[:, "status"] = (
        "V262_RESEARCH_BENCHMARK_PASS"
        if all(bool(summary.iloc[0][gate]) for gate in gates)
        else "HOLD_RESEARCH_UNFROZEN"
    )
    return detail, summary, ladder, rejections


def main() -> int:
    detail, summary, ladder, rejections = evaluate_sixth_holdout()
    write_csv_artifacts(
        OUTPUT,
        {
            "sixth_holdout_evaluation": detail,
            "sixth_holdout_summary": summary,
            "sixth_holdout_ladder": ladder,
            "sixth_holdout_rejection_taxonomy": rejections,
        },
    )
    (OUTPUT / "sixth_holdout_metadata.json").write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "holdout_config": CONFIG.relative_to(PROJECT_ROOT).as_posix(),
                "candidate_sha256": sha256_file(CANDIDATES),
                "annotation_sha256": sha256_file(ANNOTATIONS),
                "semantic_rule_changes_after_selection": False,
                "forecast_dcf_layers_modified": False,
                "llm_backend_used": False,
                "source_documents_predeclared": 10,
                "candidate_issuers": int(detail["ticker"].nunique()),
                "candidate_sampling_skew_disclosed": True,
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
