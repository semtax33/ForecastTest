from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from equity_platform.artifacts import sha256_file
from equity_platform.paths import PROJECT_ROOT
from equity_platform.text_ie.training import (
    BlindAnnotationBatch,
    build_blind_annotation_batch,
    load_annotation_review_queue,
)


QUEUE = (
    PROJECT_ROOT
    / "data-lake/silver/parser/text_ie/annotation_review_queue_active.jsonl"
)
OUTPUT = PROJECT_ROOT / "output/text_ie_annotation_factory_v1/gold_a_batch_v1"
ANNOTATOR_A_PAIRS = OUTPUT / "annotator_a_pairs.csv"
ANNOTATOR_B_PAIRS = OUTPUT / "annotator_b_pairs.csv"
ANNOTATOR_A_CONTEXTS = OUTPUT / "annotator_a_context_audit.csv"
ANNOTATOR_B_CONTEXTS = OUTPUT / "annotator_b_context_audit.csv"
ADJUDICATION = OUTPUT / "adjudication_template.csv"
MANIFEST = OUTPUT / "manifest.json"
INSTRUCTIONS = OUTPUT / "README.md"
CONTEXTS_PER_SLICE = 50


def _write_csv(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    if not rows:
        raise ValueError(f"cannot write an empty annotation artifact: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _context_assignment(rows, channel: str):
    return tuple(
        {"annotation_channel": channel, **row}
        for row in sorted(
            rows,
            key=lambda row: sha256(
                f"TEXT_IE_GOLD_A_CONTEXT_V1|{channel}|{row['context_id']}".encode()
            ).hexdigest(),
        )
    )


def _adjudication_rows(pair_rows):
    rows = []
    for pair in pair_rows:
        identity = {
            key: pair[key]
            for key in (
                "pair_id", "context_id", "source_slice", "entity",
                "source_sha256", "source_path", "text",
                "metric_candidate_start", "metric_candidate_end",
                "metric_candidate_literal", "quantity_candidate_start",
                "quantity_candidate_end", "quantity_candidate_literal",
                "quantity_candidate_kind",
            )
        }
        reviews = {
            f"annotator_{channel}_{field}": ""
            for channel in ("a", "b")
            for field in (
                "id", "metric_start", "metric_end", "metric_literal",
                "quantity_start", "quantity_end", "quantity_literal",
                "concept_label", "binding_label", "role_label", "scope",
                "period", "quantity_kind", "notes",
            )
        }
        final = {
            "agreement_status": "",
            "adjudicator_id": "",
            "final_metric_start": "",
            "final_metric_end": "",
            "final_metric_literal": "",
            "final_quantity_start": "",
            "final_quantity_end": "",
            "final_quantity_literal": "",
            "final_concept_label": "",
            "final_binding_label": "",
            "final_role_label": "",
            "final_scope": "",
            "final_period": "",
            "final_quantity_kind": "",
            "adjudication_notes": "",
        }
        rows.append({**identity, **reviews, **final})
    return tuple(rows)


def write_batch_artifacts_from_batch(
    *,
    batch: BlindAnnotationBatch,
    output: Path,
    source_queue: Path,
    contexts_per_slice: int | None,
    excluded_context_count: int = 0,
    lineage: dict[str, object] | None = None,
) -> dict[str, object]:
    """Persist one already-selected blind batch without rebuilding its graph."""

    output.mkdir(parents=True, exist_ok=True)
    annotator_a_pairs = output / "annotator_a_pairs.csv"
    annotator_b_pairs = output / "annotator_b_pairs.csv"
    annotator_a_contexts = output / "annotator_a_context_audit.csv"
    annotator_b_contexts = output / "annotator_b_context_audit.csv"
    adjudication_path = output / "adjudication_template.csv"
    instructions_path = output / "README.md"
    manifest_path = output / "manifest.json"
    a_contexts = _context_assignment(batch.context_rows, "A")
    b_contexts = _context_assignment(batch.context_rows, "B")
    adjudication = _adjudication_rows(batch.pair_rows)
    _write_csv(annotator_a_pairs, batch.annotator_a_rows)
    _write_csv(annotator_b_pairs, batch.annotator_b_rows)
    _write_csv(annotator_a_contexts, a_contexts)
    _write_csv(annotator_b_contexts, b_contexts)
    _write_csv(adjudication_path, adjudication)
    instructions_path.write_text(
        f"# Text IE GOLD_A {output.name}\n\n"
        "Status: `AWAITING_HUMAN_ANNOTATION`\n\n"
        "1. Give the A pair/context files only to annotator A and the B files only "
        "to annotator B. They must work independently.\n"
        "2. Candidate spans are navigation aids, not labels. Machine concept, "
        "binding, role, generator, and legacy answers are intentionally hidden.\n"
        "3. Each annotator must complete the context audit. If the candidate graph "
        "misses a mention or pair, mark it incomplete; do not guess around it.\n"
        "4. Merge both completed assignments into the adjudication template. A third "
        "person, whose ID differs from both annotators, resolves every pair.\n"
        "5. Only then may records be ingested as `GOLD_A`. Do not assign train, "
        "calibration, or certification splits before adjudication.\n\n"
        "Binding labels: `BELONGS_TO`, `NOT_RELATED`. Roles for positive pairs: "
        "`VALUE_CURRENT`, `VALUE_PRIOR`, `DELTA`, `COMPOSITION`, `GUIDANCE_VALUE`, "
        "`GUIDANCE_LOW`, `GUIDANCE_HIGH`.\n\n"
        "Canonical policy: `docs/text_ie/annotation-guideline-v1.md`.\n",
        encoding="utf-8",
    )
    context_counts = Counter(row["source_slice"] for row in batch.context_rows)
    pair_counts = Counter(row["source_slice"] for row in batch.pair_rows)
    artifacts = (
        annotator_a_pairs,
        annotator_b_pairs,
        annotator_a_contexts,
        annotator_b_contexts,
        adjudication_path,
        instructions_path,
    )
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "AWAITING_TWO_INDEPENDENT_ANNOTATORS_AND_SEPARATE_ADJUDICATOR",
        "quality_tier_created": "NONE",
        "gold_a_rows": 0,
        "source_queue": source_queue.relative_to(PROJECT_ROOT).as_posix(),
        "source_queue_sha256": sha256_file(source_queue),
        "contexts_per_slice": contexts_per_slice,
        "excluded_context_count": excluded_context_count,
        "context_counts": dict(sorted(context_counts.items())),
        "pair_counts": dict(sorted(pair_counts.items())),
        "total_contexts": len(batch.context_rows),
        "total_pairs_per_annotator": len(batch.pair_rows),
        "entities": len({row["entity"] for row in batch.context_rows}),
        "machine_semantic_labels_exposed": False,
        "candidate_spans_exposed_for_navigation": True,
        "candidate_quantity_kind_exposed_for_navigation": True,
        "assignment_orders_independent": (
            [row["pair_id"] for row in batch.annotator_a_rows]
            != [row["pair_id"] for row in batch.annotator_b_rows]
        ),
        "artifacts": {
            path.name: sha256_file(path) for path in artifacts
        },
        "lineage": dict(lineage or {}),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_batch_artifacts(
    *,
    queue_path: Path,
    output: Path,
    contexts_per_slice: int,
    excluded_context_ids: frozenset[str] = frozenset(),
) -> dict[str, object]:
    """Write one immutable, label-blind assignment package."""

    items = load_annotation_review_queue(queue_path)
    batch = build_blind_annotation_batch(
        items,
        contexts_per_slice=contexts_per_slice,
        excluded_context_ids=excluded_context_ids,
    )
    return write_batch_artifacts_from_batch(
        batch=batch,
        output=output,
        source_queue=queue_path,
        contexts_per_slice=contexts_per_slice,
        excluded_context_count=len(excluded_context_ids),
    )


def main() -> int:
    manifest = build_batch_artifacts(
        queue_path=QUEUE,
        output=OUTPUT,
        contexts_per_slice=CONTEXTS_PER_SLICE,
    )
    print(
        f"STATUS={manifest['status']} CONTEXTS={manifest['total_contexts']} "
        f"PAIRS_PER_ANNOTATOR={manifest['total_pairs_per_annotator']} "
        f"GOLD_A_ROWS={manifest['gold_a_rows']}"
    )
    print(f"CONTEXT_COUNTS={manifest['context_counts']}")
    print(f"PAIR_COUNTS={manifest['pair_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
