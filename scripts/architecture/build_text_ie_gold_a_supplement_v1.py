from __future__ import annotations

import csv
from pathlib import Path

from equity_platform.documents.sec_filing import (
    discover_sec_filing_sources,
    sec_filing_canonical_documents,
)
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import (
    AnnotationSourceSlice,
    build_filing_review_queue,
    load_annotation_review_queue,
    write_annotation_review_queue,
)
from scripts.architecture.build_text_ie_gold_a_batch_v1 import (
    build_batch_artifacts,
)


ACTIVE_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/annotation_review_queue_active.jsonl"
)
SUPPLEMENT_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/annotation_review_queue_gold_a_supplement_v1.jsonl"
)
BASE_BATCH = PROJECT_ROOT / "output/text_ie_annotation_factory_v1/gold_a_batch_v1"
OUTPUT = PROJECT_ROOT / "output/text_ie_annotation_factory_v1/gold_a_supplement_v1"
SEC_FILING_ROOT = PROJECT_ROOT.parent / "Arcana/data-lake/bronze/sec/fillings"
CONTEXTS_PER_SLICE = 25
SEC_CANDIDATE_CONTEXTS_PER_SLICE = 75
BENCHMARK_SLICES = {
    AnnotationSourceSlice.SEC_10K,
    AnnotationSourceSlice.SEC_10Q,
    AnnotationSourceSlice.IR_PREPARED_REMARKS,
    AnnotationSourceSlice.IR_QA,
}


def _base_context_ids() -> frozenset[str]:
    path = BASE_BATCH / "annotator_a_context_audit.csv"
    if not path.exists():
        raise FileNotFoundError(f"base annotation batch is missing: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        ids = frozenset(
            str(row.get("context_id", "")).strip() for row in csv.DictReader(handle)
        )
    if "" in ids or len(ids) != 200:
        raise ValueError("base annotation batch must contain exactly 200 context ids")
    return ids


def _expanded_sec_items(active_items, maximum_contexts_per_slice: int):
    active_sec_hashes = {
        item.source_sha256
        for item in active_items
        if item.source_slice in {
            AnnotationSourceSlice.SEC_10K,
            AnnotationSourceSlice.SEC_10Q,
        }
    }
    sources = tuple(
        source
        for source in discover_sec_filing_sources(root=SEC_FILING_ROOT)
        if source.sha256 in active_sec_hashes
    )
    if {source.sha256 for source in sources} != active_sec_hashes:
        raise ValueError("not every active SEC source was recovered from Arcana")
    documents = sec_filing_canonical_documents(sources)
    return build_filing_review_queue(
        documents=documents,
        maximum_contexts_per_slice=maximum_contexts_per_slice,
    ).items


def build_supplement(
    *,
    output: Path,
    supplement_queue: Path,
    contexts_per_slice: int,
    sec_candidate_contexts_per_slice: int,
) -> dict[str, object]:
    active_items = load_annotation_review_queue(ACTIVE_QUEUE)
    expanded_sec_items = _expanded_sec_items(
        active_items, sec_candidate_contexts_per_slice
    )
    transcript_items = tuple(
        item
        for item in active_items
        if item.source_slice in {
            AnnotationSourceSlice.IR_PREPARED_REMARKS,
            AnnotationSourceSlice.IR_QA,
        }
        and item.proposal is not None
    )
    combined = {
        item.queue_item_id: item
        for item in (*expanded_sec_items, *transcript_items)
        if item.source_slice in BENCHMARK_SLICES and item.proposal is not None
    }
    supplement_queue.parent.mkdir(parents=True, exist_ok=True)
    write_annotation_review_queue(supplement_queue, tuple(combined.values()))
    excluded = _base_context_ids()
    manifest = build_batch_artifacts(
        queue_path=supplement_queue,
        output=output,
        contexts_per_slice=contexts_per_slice,
        excluded_context_ids=excluded,
    )
    selected_context_ids = set()
    with (output / "annotator_a_context_audit.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        selected_context_ids.update(
            str(row["context_id"]) for row in csv.DictReader(handle)
        )
    if selected_context_ids & excluded:
        raise RuntimeError("supplement reused a base-batch context")
    return manifest


def main() -> int:
    manifest = build_supplement(
        output=OUTPUT,
        supplement_queue=SUPPLEMENT_QUEUE,
        contexts_per_slice=CONTEXTS_PER_SLICE,
        sec_candidate_contexts_per_slice=SEC_CANDIDATE_CONTEXTS_PER_SLICE,
    )
    print(
        f"STATUS={manifest['status']} CONTEXTS={manifest['total_contexts']} "
        f"PAIRS_PER_ANNOTATOR={manifest['total_pairs_per_annotator']}"
    )
    print(f"CONTEXT_COUNTS={manifest['context_counts']}")
    print("COMBINED_GOLD_A_CONTEXT_TARGET=300")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
