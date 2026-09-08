from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json

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


FACTORY_ROOT = PROJECT_ROOT / "output/text_ie_annotation_factory_v1"
BATCH_SPECS = (
    (
        "gold_a_batch_v1",
        FACTORY_ROOT / "gold_a_batch_v1/human_submission_v1",
        PROJECT_ROOT
        / "data-lake/silver/parser/text_ie/annotation_review_queue_active.jsonl",
        0,
    ),
    (
        "gold_a_supplement_v2",
        FACTORY_ROOT / "gold_a_supplement_v2/human_submission_v2",
        PROJECT_ROOT
        / "data-lake/silver/parser/text_ie/annotation_review_queue_gold_a_supplement_v2.jsonl",
        0,
    ),
)
GOLD_QUEUE = PROJECT_ROOT / "data-lake/gold/parser/text_ie/gold_a_combined_v1.jsonl"
PAIR_GOLD_B_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/pair_gold_b_combined_v1.jsonl"
)
REPORT = FACTORY_ROOT / "gold_a_combined_v1_ingestion_report.json"


def main() -> int:
    ingestions = []
    batch_reports = []
    for name, batch_root, review_queue, required_contexts in BATCH_SPECS:
        try:
            ingestion = ingest_gold_a_batch(
                batch_root=batch_root,
                review_queue_path=review_queue,
                required_contexts_per_slice=required_contexts,
            )
        except (FileNotFoundError, ValueError) as exc:
            batch_reports.append({
                "batch": name,
                "status": "INVALID_OR_INCOMPLETE_HUMAN_SUBMISSION",
                "error": str(exc),
            })
            report = {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "BLOCKED_UNTIL_BOTH_HUMAN_BATCHES_PASS",
                "gold_a_written": False,
                "production_enabled": False,
                "batches": batch_reports,
            }
            REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"STATUS={report['status']} BATCH={name} ERROR={exc}")
            return 1
        ingestions.append(ingestion)
        batch_reports.append({
            "batch": name,
            "status": "VALID_GOLD_A",
            "contexts": sum(ingestion.context_counts.values()),
            "context_counts": ingestion.context_counts,
            "excluded_context_counts": ingestion.excluded_context_counts,
            "pairs": len(ingestion.items),
            "pair_gold_b_pairs": len(ingestion.quarantined_items),
            "exact_pair_agreement": ingestion.exact_pair_agreement,
            "review_queue_sha256": sha256_file(review_queue),
        })
    items = tuple(item for ingestion in ingestions for item in ingestion.items)
    pair_ids = [item.queue_item_id for item in items]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("base and supplemental Gold A pair ids overlap")
    context_slices = {
        (item.candidate_id, item.source_slice.value) for item in items
    }
    context_counts = Counter(source_slice for _, source_slice in context_slices)
    required_slices = ("SEC_10K", "SEC_10Q", "IR_PREPARED_REMARKS", "IR_QA")
    context_gaps_to_75 = {
        source_slice: max(0, 75 - context_counts[source_slice])
        for source_slice in required_slices
    }
    context_gaps_to_50 = {
        source_slice: max(0, 50 - context_counts[source_slice])
        for source_slice in required_slices
    }
    split = assign_gold_a_splits(items)
    quarantined = tuple(
        item
        for ingestion in ingestions
        for item in ingestion.quarantined_items
    )
    pair_gold_b = partition_pair_gold_b_for_training(
        quarantined,
        gold_a_items=split.items,
    )
    pair_gold_b_train = pair_gold_b.train_items
    dataset = build_semantic_training_dataset_from_review_queue(
        (*split.items, *pair_gold_b_train),
        minimum_quality=AnnotationQualityTier.GOLD_B,
    )
    training = assess_semantic_training_readiness(dataset)
    corpus = assess_annotation_corpus(split.items)
    GOLD_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    write_annotation_review_queue(GOLD_QUEUE, split.items)
    write_annotation_review_queue(PAIR_GOLD_B_QUEUE, pair_gold_b_train)
    ready = training.ready and corpus.all_benchmark_slices_ready
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "GOLD_A_COMBINED_TRAINING_READY"
        if ready else "GOLD_A_COMBINED_TRAINING_GATE_BLOCKED",
        "gold_a_written": True,
        "production_enabled": False,
        "batches": batch_reports,
        "gold_queue": GOLD_QUEUE.relative_to(PROJECT_ROOT).as_posix(),
        "gold_queue_sha256": sha256_file(GOLD_QUEUE),
        "pair_gold_b_queue": PAIR_GOLD_B_QUEUE.relative_to(PROJECT_ROOT).as_posix(),
        "pair_gold_b_queue_sha256": sha256_file(PAIR_GOLD_B_QUEUE),
        "gold_a_pairs": len(items),
        "pair_gold_b_quarantined_pairs": len(quarantined),
        "pair_gold_b_train_pairs": len(pair_gold_b_train),
        "pair_gold_b_holdout_issuer_exclusions": (
            len(pair_gold_b.holdout_issuer_exclusions)
        ),
        "context_counts": dict(sorted(context_counts.items())),
        "context_gaps_to_50": context_gaps_to_50,
        "context_gaps_to_75": context_gaps_to_75,
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
        f"STATUS={report['status']} CONTEXTS={sum(context_counts.values())} "
        f"PAIRS={len(items)} TRAINING_READY={training.ready}"
    )
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
