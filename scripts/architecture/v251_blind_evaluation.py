from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.reporting import write_csv_artifacts
from equity_platform.text_ie.v251 import extract_text_kpis_v251
import scripts.architecture.v25_blind_evaluation as base
from scripts.architecture import v251_blind_candidates as blind


ANNOTATIONS = PROJECT_ROOT / "data-lake/gold/parser/text_ie/v251_unseen_sentence_annotations.jsonl"
V251_SOURCES = {
    "runtime": PROJECT_ROOT / "equity_platform/text_ie/v251/runtime.py",
    "init": PROJECT_ROOT / "equity_platform/text_ie/v251/__init__.py",
}


def verify_snapshot(config) -> None:
    blind._configure()
    base_config = config
    blind.base.verify_v25_snapshot(base_config)
    expected = dict(config["v251_snapshot_sha256"])
    mismatch = {name: sha256_file(path) for name, path in V251_SOURCES.items() if sha256_file(path) != expected[name]}
    if mismatch:
        raise ValueError(f"V2.5.1 changed after blind declaration: {mismatch}")
    if sha256_file(PROJECT_ROOT / "scripts/architecture/v251_blind_candidates.py") != config["selection_snapshot"]["generator_sha256"]:
        raise ValueError("V2.5.1 selection generator changed")


def _extract(document):
    result = extract_text_kpis_v251(document)
    return SimpleNamespace(
        extraction=result.extraction,
        candidates=result.candidates,
        bindings=(),
        table_routes=result.table_routes,
    )


def evaluate_unseen_sentences():
    base.CANDIDATES = blind.CANDIDATES
    base.OUTPUT = blind.OUTPUT
    base.ANNOTATIONS = ANNOTATIONS
    base.load_blind_config = blind.load_blind_config
    base.verify_candidate_artifact = blind.verify_candidate_artifact
    base.verify_v25_snapshot = verify_snapshot
    base._documents = blind._documents
    base.extract_text_kpis_v25 = _extract
    detail, summary, ladder, taxonomy = base.evaluate_unseen_sentences()
    summary.loc[:, "version"] = "PLATFORM_V2_5_1_SECOND_ISSUER_DOCUMENT_UNSEEN"
    return detail, summary, ladder, taxonomy


def main() -> int:
    detail, summary, ladder, taxonomy = evaluate_unseen_sentences()
    write_csv_artifacts(blind.OUTPUT, {
        "blind_sentence_evaluation": detail,
        "blind_sentence_summary": summary,
        "coverage_ladder": ladder,
        "error_taxonomy": taxonomy,
    })
    (blind.OUTPUT / "blind_sentence_metadata.json").write_text(
        json.dumps({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "annotations": ANNOTATIONS.relative_to(PROJECT_ROOT).as_posix(),
            "candidate_sha256": sha256_file(blind.CANDIDATES),
            "rule_changes_after_selection": False,
            "llm_backend_used": False,
            "validation_set_reused": False,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(ladder.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
