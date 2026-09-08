from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import (
    apply_context_recovery_review,
    build_blind_annotation_batch_for_contexts,
    load_annotation_review_queue,
    select_recovery_contexts_for_source_gaps,
    split_annotation_batch_into_chunks,
    write_annotation_review_queue,
)
from scripts.architecture.build_text_ie_gold_a_batch_v1 import (
    write_batch_artifacts_from_batch,
)


RECOVERY_ROOT = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2/context_recovery_v1"
)
TEMPLATE = RECOVERY_ROOT / "context_recovery_review.csv"
SOURCE_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/annotation_review_queue_gold_a_supplement_v2.jsonl"
)
SOURCE_SUBMISSION = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2/human_submission_v2"
)
STAGED_REVIEW = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/context_recovery_gold_a_supplement_v2_v1.csv"
)
RECOVERED_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/annotation_review_queue_gold_a_supplement_v2_recovery_v1.jsonl"
)
BATCH_OUTPUT = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2_recovery_v1"
)
CHUNKS_OUTPUT = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2_recovery_v1_chunks"
)
GOLD_A_QUEUE = (
    PROJECT_ROOT / "data-lake/gold/parser/text_ie/gold_a_combined_v1.jsonl"
)
GOLD_A_REPORT = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_combined_v1_ingestion_report.json"
)
MINIMUM_QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/annotation_review_queue_gold_a_supplement_v2_recovery_minimum_v1.jsonl"
)
MINIMUM_BATCH_OUTPUT = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2_recovery_minimum_v1"
)
MINIMUM_CHUNKS_OUTPUT = (
    PROJECT_ROOT
    / "output/text_ie_annotation_factory_v1/gold_a_supplement_v2_recovery_minimum_v1_chunks"
)


def _stage_new_or_identical(source: Path, target: Path) -> None:
    value = source.read_bytes()
    if target.exists() and target.read_bytes() != value:
        raise ValueError(f"refusing to replace a different recovery review: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(value)


def _annotator_ids(root: Path) -> frozenset[str]:
    output = set()
    for name in ("annotator_a_pairs.csv", "annotator_b_pairs.csv"):
        with (root / name).open(encoding="utf-8-sig", newline="") as handle:
            rows = tuple(csv.DictReader(handle))
        identifiers = {str(row.get("annotator_id", "")).strip() for row in rows}
        if "" in identifiers or len(identifiers) != 1:
            raise ValueError(f"{name} must contain one non-empty annotator id")
        output.update(identifiers)
    if len(output) != 2:
        raise ValueError("recovery source requires two independent annotators")
    return frozenset(output)


def _write_deterministic_zip(path: Path, members: tuple[tuple[str, Path], ...]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for member_name, source in sorted(members):
            info = ZipInfo(member_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, source.read_bytes())
    value = temporary.read_bytes()
    if path.exists() and path.read_bytes() != value:
        temporary.unlink()
        raise ValueError(f"refusing to replace a different package: {path.name}")
    if path.exists():
        temporary.unlink()
    else:
        temporary.replace(path)


def _write_annotator_packages(package, *, chunks_output: Path) -> None:
    for channel in ("a", "b"):
        logical_names = (
            f"annotator_{channel}_pairs.csv",
            f"annotator_{channel}_context_audit.csv",
        )
        members = tuple(
            (
                Path(chunk.files[logical_name]).name,
                chunks_output / chunk.files[logical_name],
            )
            for chunk in package.chunks
            for logical_name in logical_names
        )
        _write_deterministic_zip(
            chunks_output / f"annotator_{channel}.zip",
            members,
        )


def _source_gaps() -> dict[str, int]:
    report = json.loads(GOLD_A_REPORT.read_text(encoding="utf-8"))
    gaps = report.get("context_gaps_to_50")
    if not isinstance(gaps, dict):
        raise ValueError("combined Gold A report has no context_gaps_to_50")
    normalized = {str(source): int(value) for source, value in gaps.items()}
    if any(value < 0 for value in normalized.values()):
        raise ValueError("Gold A context gaps cannot be negative")
    return normalized


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply reviewed candidate recovery and create a fresh blind round."
    )
    parser.add_argument("--labeled", type=Path, required=True)
    parser.add_argument("--maximum-pairs-per-chunk", type=int, default=350)
    args = parser.parse_args(argv)

    _stage_new_or_identical(args.labeled, STAGED_REVIEW)
    source_items = load_annotation_review_queue(SOURCE_QUEUE)
    application = apply_context_recovery_review(
        template_path=TEMPLATE,
        labeled_path=STAGED_REVIEW,
        source_items=source_items,
        forbidden_reviewer_ids=_annotator_ids(SOURCE_SUBMISSION),
    )
    write_annotation_review_queue(RECOVERED_QUEUE, application.items)
    batch = build_blind_annotation_batch_for_contexts(
        application.items,
        context_ids=application.context_ids,
    )
    manifest = write_batch_artifacts_from_batch(
        batch=batch,
        output=BATCH_OUTPUT,
        source_queue=RECOVERED_QUEUE,
        contexts_per_slice=None,
        lineage={
            "recovery_template": TEMPLATE.relative_to(PROJECT_ROOT).as_posix(),
            "recovery_template_sha256": sha256_file(TEMPLATE),
            "reviewed_recovery": STAGED_REVIEW.relative_to(PROJECT_ROOT).as_posix(),
            "reviewed_recovery_sha256": sha256_file(STAGED_REVIEW),
            "action_counts": application.action_counts,
            "original_pair_count": application.original_pair_count,
            "recovered_pair_count": application.recovered_pair_count,
            "added_pair_count": application.added_pair_count,
        },
    )
    package = split_annotation_batch_into_chunks(
        batch_root=BATCH_OUTPUT,
        chunks_root=CHUNKS_OUTPUT,
        maximum_pairs_per_chunk=args.maximum_pairs_per_chunk,
    )
    _write_annotator_packages(package, chunks_output=CHUNKS_OUTPUT)
    context_counts = Counter(row["source_slice"] for row in batch.context_rows)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "AWAITING_NEW_BLIND_A_B_AND_ADJUDICATION",
        "production_enabled": False,
        "gold_a_promoted": 0,
        "reviewed_contexts": application.context_count,
        "archived_contexts": application.archived_context_count,
        "action_counts": application.action_counts,
        "original_pairs": application.original_pair_count,
        "recovered_pairs": application.recovered_pair_count,
        "added_pairs": application.added_pair_count,
        "context_counts": dict(sorted(context_counts.items())),
        "chunks": package.chunk_count,
        "oversized_contexts": len(package.oversized_context_ids),
        "oversized_context_ids": list(package.oversized_context_ids),
        "pairs_per_annotator": package.pair_count,
        "annotator_packages": {
            name: sha256_file(CHUNKS_OUTPUT / name)
            for name in ("annotator_a.zip", "annotator_b.zip")
        },
        "batch_manifest_status": manifest["status"],
    }
    (BATCH_OUTPUT / "recovery_application_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (CHUNKS_OUTPUT / "README.md").write_text(
        "# Gold A candidate-recovery blind round\n\n"
        "The recovery reviewer identified candidate spans only; no semantic label "
        "was promoted. Give `annotator_a.zip` and `annotator_b.zip` to two "
        "independent annotators. After both pair files and context audits are "
        "complete, hydrate the chunk adjudication templates and use a separate "
        "adjudicator. Contexts listed as oversized in `manifest.json` intentionally "
        "occupy one chunk by themselves so their candidate graph is never split.\n",
        encoding="utf-8",
    )

    existing_gold_context_ids = frozenset(
        item.candidate_id for item in load_annotation_review_queue(GOLD_A_QUEUE)
    )
    eligible_items = tuple(
        item
        for item in application.items
        if item.candidate_id not in existing_gold_context_ids
    )
    gaps = _source_gaps()
    selection = select_recovery_contexts_for_source_gaps(
        eligible_items,
        source_gaps=gaps,
    )
    minimum_items = tuple(
        item for item in eligible_items if item.candidate_id in selection.context_ids
    )
    write_annotation_review_queue(MINIMUM_QUEUE, minimum_items)
    minimum_batch = build_blind_annotation_batch_for_contexts(
        minimum_items,
        context_ids=selection.context_ids,
    )
    minimum_manifest = write_batch_artifacts_from_batch(
        batch=minimum_batch,
        output=MINIMUM_BATCH_OUTPUT,
        source_queue=MINIMUM_QUEUE,
        contexts_per_slice=None,
        lineage={
            "parent_recovery_queue": RECOVERED_QUEUE.relative_to(PROJECT_ROOT).as_posix(),
            "parent_recovery_queue_sha256": sha256_file(RECOVERED_QUEUE),
            "existing_gold_a_queue": GOLD_A_QUEUE.relative_to(PROJECT_ROOT).as_posix(),
            "existing_gold_a_queue_sha256": sha256_file(GOLD_A_QUEUE),
            "existing_gold_a_contexts_excluded": len(existing_gold_context_ids),
            "selection_policy": (
                "exact source gap, maximize issuer diversity before reuse, then "
                "minimize candidate pair annotation burden; no semantic outcomes"
            ),
            "source_gaps": gaps,
        },
    )
    minimum_package = split_annotation_batch_into_chunks(
        batch_root=MINIMUM_BATCH_OUTPUT,
        chunks_root=MINIMUM_CHUNKS_OUTPUT,
        maximum_pairs_per_chunk=args.maximum_pairs_per_chunk,
    )
    _write_annotator_packages(
        minimum_package,
        chunks_output=MINIMUM_CHUNKS_OUTPUT,
    )
    minimum_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "AWAITING_NEW_BLIND_A_B_AND_ADJUDICATION",
        "recommended_working_package": True,
        "production_enabled": False,
        "gold_a_promoted": 0,
        "selection_policy": (
            "source-gap exact, issuer-diverse, minimum candidate-pair burden; "
            "semantic labels and model predictions were not used"
        ),
        "source_gaps": gaps,
        "selected_context_counts": selection.context_counts,
        "selected_pair_counts": selection.pair_counts,
        "selected_contexts": len(selection.context_ids),
        "selected_entities": selection.entity_count,
        "pairs_per_annotator": minimum_package.pair_count,
        "chunks": minimum_package.chunk_count,
        "oversized_contexts": len(minimum_package.oversized_context_ids),
        "oversized_context_ids": list(minimum_package.oversized_context_ids),
        "existing_gold_a_contexts_excluded": len(existing_gold_context_ids),
        "annotator_packages": {
            name: sha256_file(MINIMUM_CHUNKS_OUTPUT / name)
            for name in ("annotator_a.zip", "annotator_b.zip")
        },
        "batch_manifest_status": minimum_manifest["status"],
    }
    (MINIMUM_BATCH_OUTPUT / "recovery_minimum_report.json").write_text(
        json.dumps(minimum_report, indent=2) + "\n", encoding="utf-8"
    )
    (MINIMUM_CHUNKS_OUTPUT / "README.md").write_text(
        "# Gold A candidate-recovery minimum closure round\n\n"
        "This is the recommended working package. It contains only the contexts "
        "needed to close the current 50-context source-slice gate, excludes every "
        "existing Gold A context, and was selected without semantic labels or model "
        "predictions. Give `annotator_a.zip` and `annotator_b.zip` to two independent "
        "annotators. A separate adjudicator must resolve the hydrated outputs before "
        "any record can become Gold A.\n",
        encoding="utf-8",
    )
    print(
        f"STATUS={report['status']} CONTEXTS={application.context_count} "
        f"PAIRS={package.pair_count} CHUNKS={package.chunk_count} GOLD_A=0"
    )
    print(
        f"RECOMMENDED_MINIMUM CONTEXTS={len(selection.context_ids)} "
        f"PAIRS={minimum_package.pair_count} CHUNKS={minimum_package.chunk_count} "
        f"ENTITIES={selection.entity_count} GOLD_A=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
