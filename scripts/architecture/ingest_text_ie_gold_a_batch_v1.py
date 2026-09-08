from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import (
    AnnotationQualityTier,
    assign_gold_a_splits,
    assess_annotation_corpus,
    assess_semantic_training_readiness,
    build_semantic_training_dataset_from_review_queue,
    ingest_gold_a_batch,
    partition_pair_gold_b_for_training,
    write_annotation_review_queue,
)


TEMPLATE_ROOT = PROJECT_ROOT / "output/text_ie_annotation_factory_v1/gold_a_batch_v1"
BATCH_ROOT = TEMPLATE_ROOT / "human_submission_v1"
REVIEW_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/annotation_review_queue_active.jsonl"
)
GOLD_QUEUE = PROJECT_ROOT / "data-lake/gold/parser/text_ie/gold_a_batch_v1.jsonl"
PAIR_GOLD_B_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/pair_gold_b_incomplete_graph_v1.jsonl"
)
REPORT = TEMPLATE_ROOT / "ingestion_report.json"
INPUT_FILES = (
    "annotator_a_pairs.csv",
    "annotator_b_pairs.csv",
    "annotator_a_context_audit.csv",
    "annotator_b_context_audit.csv",
    "adjudication_template.csv",
)


def _completion_counts(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"exists": False, "rows": 0, "human_fields_filled": 0}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    human_fields = tuple(
        field
        for field in (tuple(rows[0]) if rows else ())
        if field.startswith(("reviewed_", "final_", "annotator_"))
        or field in {"annotator_id", "adjudicator_id", "agreement_status", "candidate_graph_complete"}
    )
    return {
        "exists": True,
        "rows": len(rows),
        "human_fields": list(human_fields),
        "human_fields_filled": sum(
            bool(str(row.get(field, "")).strip())
            for row in rows
            for field in human_fields
        ),
        "sha256": sha256_file(path),
    }


def main() -> int:
    inputs = {
        name: _completion_counts(BATCH_ROOT / name) for name in INPUT_FILES
    }
    common = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "batch_root": BATCH_ROOT.relative_to(PROJECT_ROOT).as_posix(),
        "active_queue": REVIEW_QUEUE.relative_to(PROJECT_ROOT).as_posix(),
        "active_queue_sha256": sha256_file(REVIEW_QUEUE),
        "input_files": inputs,
    }
    try:
        ingestion = ingest_gold_a_batch(
            batch_root=BATCH_ROOT,
            review_queue_path=REVIEW_QUEUE,
            required_contexts_per_slice=0,
        )
    except ValueError as exc:
        report = {
            **common,
            "status": "BLOCKED_INVALID_OR_INCOMPLETE_HUMAN_SUBMISSION",
            "gold_a_written": False,
            "production_enabled": False,
            "error": str(exc),
        }
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"STATUS={report['status']}")
        print(f"ERROR={report['error']}")
        return 1
    split = assign_gold_a_splits(ingestion.items)
    write_annotation_review_queue(GOLD_QUEUE, split.items)
    pair_gold_b = partition_pair_gold_b_for_training(
        ingestion.quarantined_items,
        gold_a_items=split.items,
    )
    pair_gold_b_train = pair_gold_b.train_items
    write_annotation_review_queue(PAIR_GOLD_B_QUEUE, pair_gold_b_train)
    dataset = build_semantic_training_dataset_from_review_queue(
        (*split.items, *pair_gold_b_train),
        minimum_quality=AnnotationQualityTier.GOLD_B,
    )
    training = assess_semantic_training_readiness(dataset)
    corpus = assess_annotation_corpus(split.items)
    report = {
        **common,
        "status": (
            "GOLD_A_INGESTED_RESEARCH_TRAINING_READY"
            if training.ready
            else "PARTIAL_GOLD_A_INGESTED_RECOVERY_AND_TRAINING_BLOCKED"
        ),
        "gold_a_written": True,
        "production_enabled": False,
        "gold_queue": GOLD_QUEUE.relative_to(PROJECT_ROOT).as_posix(),
        "gold_queue_sha256": sha256_file(GOLD_QUEUE),
        "pair_gold_b_queue": PAIR_GOLD_B_QUEUE.relative_to(PROJECT_ROOT).as_posix(),
        "pair_gold_b_queue_sha256": sha256_file(PAIR_GOLD_B_QUEUE),
        "gold_a_pairs": len(ingestion.items),
        "pair_gold_b_quarantined_pairs": len(ingestion.quarantined_items),
        "pair_gold_b_train_pairs": len(pair_gold_b_train),
        "pair_gold_b_holdout_issuer_exclusions": (
            len(pair_gold_b.holdout_issuer_exclusions)
        ),
        "context_counts": ingestion.context_counts,
        "excluded_context_counts": ingestion.excluded_context_counts,
        "pair_counts": ingestion.pair_counts,
        "exact_pair_agreement": ingestion.exact_pair_agreement,
        "split_entity_counts": split.entity_counts,
        "split_context_counts_by_source": split.context_counts_by_split_source,
        "all_source_slices_ready": corpus.all_benchmark_slices_ready,
        "training_ready": training.ready,
        "training_reasons": list(training.reasons),
        "training_metrics": {
            "text_contexts": training.text_context_count,
            "concept_examples": training.concept_example_count,
            "relation_pairs": training.relation_pair_count,
            "role_examples": training.role_example_count,
            "positive_bindings": training.positive_binding_count,
            "negative_bindings": training.negative_binding_count,
            "independently_human_adjudicated": (
                training.independently_human_adjudicated
            ),
        },
        "dataset": {
            "concepts": len(dataset.concepts),
            "relations": len(dataset.relations),
            "roles": len(dataset.roles),
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"STATUS={report['status']} GOLD_A_PAIRS={report['gold_a_pairs']} "
        f"TRAINING_READY={report['training_ready']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
