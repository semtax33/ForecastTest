from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from equity_platform.artifacts import sha256_file
from equity_platform.documents.earnings_call import (
    TranscriptSection,
    load_alpha_vantage_transcript_corpus,
    transcript_canonical_documents,
)
from equity_platform.documents.sec_filing import (
    discover_sec_filing_sources,
    sec_filing_canonical_documents,
)
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import (
    AnnotationQualityTier,
    AnnotationSourceSlice,
    assess_annotation_corpus,
    build_historical_review_queue,
    build_filing_review_queue,
    build_transcript_review_queue,
    write_annotation_review_queue,
)


GOLD_ROOT = PROJECT_ROOT / "data-lake/gold/parser/text_ie"
OUTPUT_ROOT = PROJECT_ROOT / "output/text_ie_annotation_factory_v1"
SILVER_ROOT = PROJECT_ROOT / "data-lake/silver/parser/text_ie"
HISTORICAL_QUEUE = SILVER_ROOT / "annotation_review_queue_v1.jsonl"
HISTORICAL_METADATA = SILVER_ROOT / "annotation_review_queue_v1_metadata.json"
QUEUE = SILVER_ROOT / "annotation_review_queue_active.jsonl"
METADATA = SILVER_ROOT / "annotation_review_queue_active_metadata.json"
READINESS = OUTPUT_ROOT / "source_slice_readiness.csv"
REPORT = OUTPUT_ROOT / "report.md"
CONTEXT_PRIORITY = OUTPUT_ROOT / "annotation_context_priority.csv"
SOURCE_GAPS = OUTPUT_ROOT / "source_slice_gap.csv"
IR_TRIAGE = OUTPUT_ROOT / "ir_source_triage.csv"
TRANSCRIPT_CATALOG = OUTPUT_ROOT / "earnings_call_transcript_catalog.csv"
SEC_CATALOG = OUTPUT_ROOT / "sec_filing_annotation_catalog.csv"
SCHEMA = PROJECT_ROOT / "configs/annotation/text_ie_adjudication_v1.schema.json"
GUIDELINE = PROJECT_ROOT / "docs/text_ie/annotation-guideline-v1.md"
UNIVERSE = (
    PROJECT_ROOT
    / "data-lake/gold/platform_v2_5/precision_recovery/universe_layer_certification.csv"
)
TRANSCRIPT_ROOT = Path(os.environ.get(
    "ARCANA_EARNINGS_CALL_TRANSCRIPT_ROOT",
    str(
        PROJECT_ROOT.parent
        / "Arcana/data-lake/bronze/earnings-call-transcripts/alpha-vantage"
    ),
))
TRANSCRIPTS_PER_ENTITY = 2
TRANSCRIPT_CONTEXTS_PER_SLICE = 200
SEC_CONTEXTS_PER_SLICE = 50
SEC_FILING_ROOT = Path(os.environ.get(
    "ARCANA_SEC_FILING_ROOT",
    str(PROJECT_ROOT.parent / "Arcana/data-lake/bronze/sec/fillings"),
))


def discover_candidate_csvs() -> tuple[Path, ...]:
    return tuple(sorted(
        path
        for path in (PROJECT_ROOT / "output").rglob("*.csv")
        if path.name.endswith("holdout_candidates.csv")
        or path.name == "blind_sentence_candidates.csv"
    ))


def discover_annotation_files() -> tuple[Path, ...]:
    return tuple(sorted(GOLD_ROOT.glob("v*_annotations.jsonl")))


def _candidate_sources(candidate_csvs: tuple[Path, ...]) -> dict[Path, str]:
    sources: dict[Path, str] = {}
    for candidate_csv in candidate_csvs:
        with candidate_csv.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                path = Path(row["source_path"])
                expected = row["source_sha256"]
                prior = sources.setdefault(path, expected)
                if prior != expected:
                    raise ValueError(f"conflicting source hashes for {path}")
    return sources


def verify_candidate_sources(candidate_csvs: tuple[Path, ...]) -> dict[str, object]:
    sources = _candidate_sources(candidate_csvs)
    missing = tuple(str(path) for path in sources if not path.exists())
    mismatched = tuple(
        str(path)
        for path, expected in sources.items()
        if path.exists() and sha256_file(path) != expected
    )
    return {
        "unique_source_files": len(sources),
        "existing_source_files": len(sources) - len(missing),
        "missing_source_files": missing,
        "hash_mismatched_source_files": mismatched,
        "all_sources_verified": not missing and not mismatched,
    }


def _write_readiness(assessment) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    fields = (
        "source_slice",
        "research_contexts",
        "gold_a_contexts",
        "positive_bindings",
        "negative_bindings",
        "role_examples",
        "double_annotated_pairs",
        "binding_agreement",
        "binding_kappa",
        "exact_pair_agreement",
        "ready_for_source_benchmark",
        "reasons",
    )
    with READINESS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for source_slice, row in assessment.by_source_slice.items():
            writer.writerow({
                "source_slice": source_slice.value,
                "research_contexts": row.research_contexts,
                "gold_a_contexts": row.gold_a_contexts,
                "positive_bindings": row.positive_bindings,
                "negative_bindings": row.negative_bindings,
                "role_examples": row.role_examples,
                "double_annotated_pairs": row.double_annotated_pairs,
                "binding_agreement": row.binding_agreement,
                "binding_kappa": row.binding_kappa,
                "exact_pair_agreement": row.exact_pair_agreement,
                "ready_for_source_benchmark": row.ready_for_source_benchmark,
                "reasons": "|".join(row.reasons),
            })


def _write_annotation_operations(items, assessment) -> None:
    by_context: dict[str, list] = {}
    for item in items:
        by_context.setdefault(item.candidate_id, []).append(item)
    priority_rows = []
    for candidate_id, items in by_context.items():
        proposals = tuple(item.proposal for item in items if item.proposal is not None)
        related = sum(item.binding_hint == "BELONGS_TO" for item in proposals)
        negative = sum(item.binding_hint == "NOT_RELATED" for item in proposals)
        recovery = sum(
            item.proposal is None and item.adjudication_status == "PENDING"
            for item in items
        )
        source_slice = items[0].source_slice
        if source_slice in {
            AnnotationSourceSlice.SEC_10K,
            AnnotationSourceSlice.SEC_10Q,
            AnnotationSourceSlice.IR_PREPARED_REMARKS,
            AnnotationSourceSlice.IR_QA,
        }:
            priority, reason = 0, "SCARCE_BENCHMARK_SOURCE_SLICE"
        elif related and negative:
            priority, reason = 1, "LOCAL_HARD_NEGATIVE_CROSS_PRODUCT"
        elif related:
            priority, reason = 2, "LEGACY_POSITIVE_RECOVERY"
        elif recovery and items[0].legacy_expected_frames:
            priority, reason = 3, "UNMATCHED_LEGACY_FRAME"
        else:
            priority, reason = 4, "NEGATIVE_OR_CONTEXT_REVIEW"
        priority_rows.append({
            "candidate_id": candidate_id,
            "entity": items[0].entity,
            "source_slice": source_slice.value,
            "priority": priority,
            "priority_reason": reason,
            "queue_items": len(items),
            "related_hints": related,
            "negative_hints": negative,
            "context_recovery_items": recovery,
            "pair_proposals": len(proposals),
            "source_sha256": items[0].source_sha256,
            "source_path": items[0].source_path,
        })
    priority_rows.sort(key=lambda row: (
        row["priority"], row["source_slice"], row["candidate_id"]
    ))
    with CONTEXT_PRIORITY.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(priority_rows[0]))
        writer.writeheader()
        writer.writerows(priority_rows)

    available = Counter(
        row["source_slice"]
        for row in priority_rows
        if row["pair_proposals"] > 0
    )
    benchmark_slices = (
        AnnotationSourceSlice.SEC_10K,
        AnnotationSourceSlice.SEC_10Q,
        AnnotationSourceSlice.IR_PREPARED_REMARKS,
        AnnotationSourceSlice.IR_QA,
    )
    with SOURCE_GAPS.open("w", encoding="utf-8", newline="") as handle:
        fields = (
            "source_slice", "available_weak_pair_contexts", "research_contexts",
            "gold_a_contexts", "minimum_context_target", "acquisition_gap",
            "ready_for_source_benchmark",
        )
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for source_slice in benchmark_slices:
            row = assessment.by_source_slice[source_slice]
            writer.writerow({
                "source_slice": source_slice.value,
                "available_weak_pair_contexts": available[source_slice.value],
                "research_contexts": row.research_contexts,
                "gold_a_contexts": row.gold_a_contexts,
                "minimum_context_target": 50,
                "acquisition_gap": max(0, 50 - available[source_slice.value]),
                "ready_for_source_benchmark": row.ready_for_source_benchmark,
            })

    ir_sources: dict[str, dict[str, object]] = {}
    for row in priority_rows:
        if row["source_slice"] != AnnotationSourceSlice.IR_UNSPECIFIED.value:
            continue
        source = ir_sources.setdefault(str(row["source_sha256"]), {
            "source_sha256": row["source_sha256"],
            "source_path": row["source_path"],
            "context_count": 0,
            "adjudicated_source_slice": "",
            "reviewer_id": "",
        })
        source["context_count"] = int(source["context_count"]) + 1
    with IR_TRIAGE.open("w", encoding="utf-8", newline="") as handle:
        fields = (
            "source_sha256", "source_path", "context_count",
            "adjudicated_source_slice", "reviewer_id",
        )
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(ir_sources.values(), key=lambda row: str(row["source_path"])))


def _registered_entities() -> tuple[str, ...]:
    with UNIVERSE.open(encoding="utf-8-sig", newline="") as handle:
        return tuple(sorted({str(row["ticker"]).strip() for row in csv.DictReader(handle)}))


def _write_transcript_catalog(corpus) -> None:
    selected_hashes = {row.source.sha256 for row in corpus.selected_transcripts}
    rows = []
    for transcript in corpus.transcripts:
        rows.append({
            "entity": transcript.entity,
            "period": transcript.period,
            "status": transcript.status.value,
            "complete": transcript.complete,
            "selected_for_annotation": transcript.source.sha256 in selected_hashes,
            "boundary_method": transcript.boundary_method.value,
            "turns": len(transcript.turns),
            "empty_turns": transcript.empty_turn_count,
            "prepared_turns": sum(
                turn.section is TranscriptSection.PREPARED_REMARKS
                for turn in transcript.turns
            ),
            "qa_turns": sum(
                turn.section is TranscriptSection.QA for turn in transcript.turns
            ),
            "unspecified_turns": sum(
                turn.section is TranscriptSection.UNSPECIFIED
                for turn in transcript.turns
            ),
            "available_at": transcript.source.available_at,
            "available_at_basis": transcript.available_at_basis,
            "call_occurred_at": transcript.call_occurred_at or "",
            "source_path": transcript.source.local_path,
            "source_sha256": transcript.source.sha256,
        })
    fields = (
        "entity", "period", "status", "complete", "selected_for_annotation",
        "boundary_method", "turns", "empty_turns", "prepared_turns", "qa_turns",
        "unspecified_turns", "available_at", "available_at_basis",
        "call_occurred_at", "source_path", "source_sha256",
    )
    with TRANSCRIPT_CATALOG.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _select_unseen_sec_sources(sources, excluded_hashes: frozenset[str]):
    """Take unseen sources in entity-balanced rounds, newest first."""

    by_key: dict[tuple[str, str], list] = {}
    for source in sources:
        if source.sha256 in excluded_hashes:
            continue
        by_key.setdefault((source.form, source.entity), []).append(source)
    for rows in by_key.values():
        rows.sort(key=lambda row: (row.filing_date, row.path.name), reverse=True)
    selected = []
    for round_index in range(2):
        for key in sorted(by_key):
            rows = by_key[key]
            if round_index < len(rows):
                selected.append(rows[round_index])
    return tuple(selected)


def _write_sec_catalog(sources, selected_hashes, excluded_hashes) -> None:
    fields = (
        "entity", "form", "filing_date", "report_period", "selected_for_annotation",
        "excluded_as_historical_source", "available_at_basis", "source_path",
        "source_sha256", "metadata_path",
    )
    with SEC_CATALOG.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for source in sources:
            writer.writerow({
                "entity": source.entity,
                "form": source.form,
                "filing_date": source.filing_date,
                "report_period": source.report_period,
                "selected_for_annotation": source.sha256 in selected_hashes,
                "excluded_as_historical_source": source.sha256 in excluded_hashes,
                "available_at_basis": "SEC_FILING_DATE",
                "source_path": source.path.as_posix(),
                "source_sha256": source.sha256,
                "metadata_path": source.metadata_path.as_posix(),
            })


def main() -> int:
    candidate_csvs = discover_candidate_csvs()
    annotation_files = discover_annotation_files()
    historical_queue = build_historical_review_queue(
        candidate_csvs=candidate_csvs,
        annotation_files=annotation_files,
    )
    historical_source_hashes = frozenset(
        item.source_sha256 for item in historical_queue.items
    )
    historical_by_context: dict[str, list] = {}
    for item in historical_queue.items:
        historical_by_context.setdefault(item.candidate_id, []).append(item)
    historical_pair_context_counts = Counter(
        items[0].source_slice
        for items in historical_by_context.values()
        if any(item.proposal is not None for item in items)
    )
    sec_sources = discover_sec_filing_sources(root=SEC_FILING_ROOT)
    selected_sec_sources = _select_unseen_sec_sources(
        sec_sources, historical_source_hashes
    )
    sec_documents = sec_filing_canonical_documents(selected_sec_sources)
    filing_queues = []
    for source_slice, document_kind in (
        (AnnotationSourceSlice.SEC_10K, "10-K"),
        (AnnotationSourceSlice.SEC_10Q, "10-Q"),
    ):
        gap = max(
            0,
            SEC_CONTEXTS_PER_SLICE - historical_pair_context_counts[source_slice],
        )
        if gap:
            filing_queues.append(build_filing_review_queue(
                documents=tuple(
                    document
                    for document in sec_documents
                    if document.metadata.document_kind == document_kind
                ),
                maximum_contexts_per_slice=gap,
            ))
    corpus = load_alpha_vantage_transcript_corpus(
        root=TRANSCRIPT_ROOT,
        entities=_registered_entities(),
        maximum_ok_per_entity=TRANSCRIPTS_PER_ENTITY,
    )
    if corpus.duplicate_source_hashes:
        raise RuntimeError("duplicate transcript payload hashes detected")
    transcript_documents = tuple(
        document
        for transcript in corpus.selected_transcripts
        for document in transcript_canonical_documents(transcript)
    )
    transcript_queue = build_transcript_review_queue(
        documents=transcript_documents,
        maximum_contexts_per_slice=TRANSCRIPT_CONTEXTS_PER_SLICE,
    )
    write_annotation_review_queue(HISTORICAL_QUEUE, historical_queue.items)
    filing_items = tuple(
        item for queue in filing_queues for item in queue.items
    )
    combined_items = (
        *historical_queue.items,
        *filing_items,
        *transcript_queue.items,
    )
    write_annotation_review_queue(QUEUE, combined_items)
    assessment = assess_annotation_corpus(combined_items)
    _write_readiness(assessment)
    _write_annotation_operations(combined_items, assessment)
    _write_transcript_catalog(corpus)
    _write_sec_catalog(
        sec_sources,
        {source.sha256 for source in selected_sec_sources},
        historical_source_hashes,
    )
    source_verification = verify_candidate_sources(candidate_csvs)
    if historical_queue.missing_candidate_ids or not source_verification["all_sources_verified"]:
        raise RuntimeError("historical queue source lineage did not verify")
    proposals = tuple(item for item in combined_items if item.proposal is not None)
    slice_items = Counter(item.source_slice.value for item in combined_items)
    slice_contexts = {
        source_slice.value: len({
            item.candidate_id
            for item in combined_items
            if item.source_slice is source_slice
        })
        for source_slice in AnnotationSourceSlice
    }
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "REVIEW_QUEUE_READY_MODEL_TRAINING_BLOCKED",
        "schema_version": "1.0.0",
        "queue_path": QUEUE.relative_to(PROJECT_ROOT).as_posix(),
        "model_training_allowed": False,
        "certification_allowed": False,
        "candidate_csv_count": len(candidate_csvs),
        "annotation_file_count": len(annotation_files),
        "annotation_rows": historical_queue.annotation_row_count,
        "unique_historical_candidate_contexts": historical_queue.unique_candidate_count,
        "unique_candidate_contexts": len({item.candidate_id for item in combined_items}),
        "superseded_annotation_rows": historical_queue.superseded_annotation_rows,
        "review_queue_items": len(combined_items),
        "pair_proposals": len(proposals),
        "context_recovery_items": sum(
            item.proposal is None and item.adjudication_status == "PENDING"
            for item in combined_items
        ),
        "archived_table_contexts": historical_queue.archived_table_contexts,
        "positive_binding_hints": sum(
            item.proposal.binding_hint == "BELONGS_TO" for item in proposals
        ),
        "negative_binding_hints": sum(
            item.proposal.binding_hint == "NOT_RELATED" for item in proposals
        ),
        "selected_legacy_frames": historical_queue.selected_expected_frames,
        "matched_legacy_frames": historical_queue.matched_expected_frames,
        "unmatched_legacy_frames": historical_queue.unmatched_expected_frames,
        "earnings_call_transcripts": {
            "root": str(TRANSCRIPT_ROOT),
            "registered_entities": len(_registered_entities()),
            "files": len(corpus.transcripts),
            "ok": corpus.ok_count,
            "no_data": corpus.no_data_count,
            "partial_content": corpus.partial_content_count,
            "empty_content": corpus.empty_content_count,
            "missing_entities": list(corpus.missing_entities),
            "duplicate_source_hashes": list(corpus.duplicate_source_hashes),
            "boundary_method_counts": corpus.boundary_method_counts,
            "selected_transcripts": len(corpus.selected_transcripts),
            "eligible_contexts": transcript_queue.eligible_contexts,
            "selected_contexts": transcript_queue.selected_contexts,
            "eligible_contexts_by_slice": transcript_queue.eligible_contexts_by_slice,
            "selected_contexts_by_slice": transcript_queue.selected_contexts_by_slice,
            "candidate_graph_items": len(transcript_queue.items),
            "available_at_policy": "ARCHIVE_RETRIEVED_AT_NOT_CALL_DATE",
            "training_authority": "WEAK_REVIEW_ONLY",
        },
        "sec_filing_candidate_graph": {
            "root": str(SEC_FILING_ROOT),
            "discovered_sources": len(sec_sources),
            "selected_unseen_sources": len(selected_sec_sources),
            "selected_10k_sources": sum(
                source.form == "10-K" for source in selected_sec_sources
            ),
            "selected_10q_sources": sum(
                source.form == "10-Q" for source in selected_sec_sources
            ),
            "eligible_contexts_by_slice": {
                source_slice: sum(
                    queue.eligible_contexts_by_slice.get(source_slice, 0)
                    for queue in filing_queues
                )
                for source_slice in ("SEC_10K", "SEC_10Q")
            },
            "selected_contexts_by_slice": {
                source_slice: sum(
                    queue.selected_contexts_by_slice.get(source_slice, 0)
                    for queue in filing_queues
                )
                for source_slice in ("SEC_10K", "SEC_10Q")
            },
            "candidate_graph_items": len(filing_items),
            "excluded_oversized_contexts": sum(
                queue.excluded_oversized_contexts for queue in filing_queues
            ),
            "excluded_dense_contexts": sum(
                queue.excluded_dense_contexts for queue in filing_queues
            ),
            "available_at_policy": "SEC_FILING_DATE",
            "historical_source_overlap": 0,
            "training_authority": "WEAK_REVIEW_ONLY",
        },
        "source_slice_item_counts": dict(sorted(slice_items.items())),
        "source_slice_context_counts": slice_contexts,
        "quality_tier_counts": {
            tier.value: assessment.quality_tier_counts[tier]
            for tier in AnnotationQualityTier
        },
        "all_benchmark_slices_ready": assessment.all_benchmark_slices_ready,
        "source_verification": source_verification,
        "schema_sha256": sha256_file(SCHEMA),
        "guideline_sha256": sha256_file(GUIDELINE),
        "candidate_artifact_sha256": {
            path.relative_to(PROJECT_ROOT).as_posix(): sha256_file(path)
            for path in candidate_csvs
        },
        "annotation_artifact_sha256": {
            path.relative_to(PROJECT_ROOT).as_posix(): sha256_file(path)
            for path in annotation_files
        },
        "queue_sha256": sha256_file(QUEUE),
        "historical_queue_sha256": sha256_file(HISTORICAL_QUEUE),
        "readiness_sha256": sha256_file(READINESS),
        "context_priority_sha256": sha256_file(CONTEXT_PRIORITY),
        "source_gap_sha256": sha256_file(SOURCE_GAPS),
        "ir_triage_sha256": sha256_file(IR_TRIAGE),
        "transcript_catalog_sha256": sha256_file(TRANSCRIPT_CATALOG),
        "sec_catalog_sha256": sha256_file(SEC_CATALOG),
    }
    HISTORICAL_METADATA.write_text(json.dumps({
        "generated_at_utc": metadata["generated_at_utc"],
        "status": "FROZEN_HISTORICAL_WEAK_REPLAY",
        "schema_version": "1.0.0",
        "queue_path": HISTORICAL_QUEUE.relative_to(PROJECT_ROOT).as_posix(),
        "model_training_allowed": False,
        "certification_allowed": False,
        "annotation_rows": historical_queue.annotation_row_count,
        "unique_candidate_contexts": historical_queue.unique_candidate_count,
        "review_queue_items": len(historical_queue.items),
        "queue_sha256": sha256_file(HISTORICAL_QUEUE),
    }, indent=2) + "\n", encoding="utf-8")
    METADATA.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(
        "# Text IE Annotation Factory V1\n\n"
        f"- Status: `{metadata['status']}`\n"
        f"- Unique historical contexts: {historical_queue.unique_candidate_count}\n"
        f"- Earnings-call contexts selected: {transcript_queue.selected_contexts}\n"
        f"- New SEC filing contexts selected: {sum(queue.selected_contexts for queue in filing_queues)}\n"
        f"- Review queue items: {len(combined_items)}\n"
        f"- Pair proposals: {len(proposals)}\n"
        f"- Context recovery items: {metadata['context_recovery_items']}\n"
        f"- Archived TABLE_DSL contexts: {historical_queue.archived_table_contexts}\n"
        f"- Unmatched legacy frames requiring recovery: {historical_queue.unmatched_expected_frames}\n"
        f"- Alpha Vantage transcripts: {corpus.ok_count} OK / {corpus.no_data_count} no_data / "
        f"{corpus.partial_content_count} partial / {corpus.empty_content_count} empty\n"
        f"- Missing registered transcript entities: {', '.join(corpus.missing_entities) or 'none'}\n"
        "- Transcript PIT policy: retrieved-at is archive availability, never call date.\n"
        f"- Verified raw source files: {source_verification['existing_source_files']}\n"
        "- Model training: blocked until source-slice human adjudication gates pass.\n",
        encoding="utf-8",
    )
    print(
        f"CONTEXTS={metadata['unique_candidate_contexts']} QUEUE_ITEMS={len(combined_items)} "
        f"PAIR_PROPOSALS={len(proposals)}"
    )
    print(
        f"RELATED_HINTS={metadata['positive_binding_hints']} "
        f"NEGATIVE_HINTS={metadata['negative_binding_hints']} "
        f"RECOVERY_ITEMS={metadata['context_recovery_items']}"
    )
    print(
        f"SOURCES_VERIFIED={source_verification['existing_source_files']} "
        f"MISSING_CANDIDATES={len(historical_queue.missing_candidate_ids)} "
        f"SOURCE_BENCHMARK_READY={assessment.all_benchmark_slices_ready}"
    )
    print(
        f"TRANSCRIPTS_OK={corpus.ok_count} TRANSCRIPTS_NO_DATA={corpus.no_data_count} "
        f"TRANSCRIPTS_PARTIAL={corpus.partial_content_count} "
        f"TRANSCRIPTS_EMPTY={corpus.empty_content_count} "
        f"TRANSCRIPT_CONTEXTS={transcript_queue.selected_contexts} "
        f"MISSING_ENTITIES={','.join(corpus.missing_entities)}"
    )
    print("STATUS=REVIEW_QUEUE_READY_MODEL_TRAINING_BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
