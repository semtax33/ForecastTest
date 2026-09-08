from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from ..model import QuantityKind
from ..role_graph import SemanticRole
from .annotation import (
    AnnotationQualityTier,
    AnnotationReviewItem,
    AnnotationSourceSlice,
    FinalPairAnnotation,
    HumanPairAnnotation,
    TextSpan,
    adjudicate_review_item,
    load_annotation_review_queue,
    record_human_annotation,
)
from .corpus_readiness import BENCHMARK_SOURCE_SLICES


@dataclass(frozen=True)
class GoldABatchIngestion:
    items: tuple[AnnotationReviewItem, ...]
    quarantined_items: tuple[AnnotationReviewItem, ...]
    context_counts: dict[str, int]
    excluded_context_counts: dict[str, int]
    pair_counts: dict[str, int]
    exact_pair_agreement: float


@dataclass(frozen=True)
class _ContextAudit:
    annotator_ids: frozenset[str]
    complete_context_ids: frozenset[str]
    incomplete_context_ids: frozenset[str]


def _read_csv(path: Path) -> tuple[dict[str, str], ...]:
    if not path.exists():
        raise ValueError(f"missing human annotation file: {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = tuple(dict(row) for row in csv.DictReader(handle))
    if not rows:
        raise ValueError(f"empty human annotation file: {path.name}")
    return rows


def _index(rows: tuple[dict[str, str], ...], key: str, label: str):
    output = {}
    for row in rows:
        value = row.get(key, "").strip()
        if not value or value in output:
            raise ValueError(f"{label} requires unique non-empty {key}")
        output[value] = row
    return output


def _integer(row: dict[str, str], field: str) -> int:
    literal = row.get(field, "").strip()
    if not literal:
        raise ValueError(f"missing required annotation field: {field}")
    try:
        return int(literal)
    except ValueError as exc:
        raise ValueError(f"invalid integer annotation field: {field}={literal}") from exc


def _span(row: dict[str, str], prefix: str, text: str) -> TextSpan:
    start = _integer(row, f"{prefix}_start")
    end = _integer(row, f"{prefix}_end")
    literal = row.get(f"{prefix}_literal", "")
    if not literal or not 0 <= start < end <= len(text):
        raise ValueError(f"invalid reviewed span: {prefix}")
    if text[start:end] != literal:
        raise ValueError(f"reviewed span literal mismatch: {prefix}")
    return TextSpan(start, end, literal)


def _annotation(
    row: dict[str, str],
    *,
    prefix: str,
    text: str,
) -> FinalPairAnnotation:
    binding = row.get(f"{prefix}_binding_label", "").strip()
    role = row.get(f"{prefix}_role_label", "").strip() or None
    quantity_kind = row.get(f"{prefix}_quantity_kind", "").strip()
    if role is not None and role not in {value.value for value in SemanticRole}:
        raise ValueError(f"unsupported reviewed role: {role}")
    if quantity_kind not in {value.value for value in QuantityKind}:
        raise ValueError(f"unsupported reviewed quantity kind: {quantity_kind}")
    return FinalPairAnnotation(
        metric_span=_span(row, f"{prefix}_metric", text),
        quantity_span=_span(row, f"{prefix}_quantity", text),
        concept_label=row.get(f"{prefix}_concept_label", "").strip(),
        binding_label=binding,
        role_label=role,
        scope=row.get(f"{prefix}_scope", "").strip(),
        period=row.get(f"{prefix}_period", "").strip(),
        quantity_kind=quantity_kind,
    )


def _pair_annotation(row: dict[str, str]) -> FinalPairAnnotation:
    return _annotation(row, prefix="reviewed", text=row.get("text", ""))


def _assert_immutable_pair_fields(
    row: dict[str, str], item: AnnotationReviewItem
) -> None:
    expected = {
        "context_id": item.candidate_id,
        "source_slice": item.source_slice.value,
        "entity": item.entity,
        "source_sha256": item.source_sha256,
        "source_path": item.source_path,
        "text": item.text,
        "document_char_start": str(item.document_char_start),
        "document_char_end": str(item.document_char_end),
    }
    for field, value in expected.items():
        if row.get(field, "") != value:
            raise ValueError(f"immutable annotation field changed: {field}")


def _assert_immutable_adjudication_fields(
    row: dict[str, str], item: AnnotationReviewItem
) -> None:
    proposal = item.proposal
    if proposal is None:
        raise ValueError("adjudication requires an active pair proposal")
    expected = {
        "context_id": item.candidate_id,
        "source_slice": item.source_slice.value,
        "entity": item.entity,
        "source_sha256": item.source_sha256,
        "source_path": item.source_path,
        "text": item.text,
        "metric_candidate_start": str(proposal.metric_span.char_start),
        "metric_candidate_end": str(proposal.metric_span.char_end),
        "metric_candidate_literal": proposal.metric_span.literal,
        "quantity_candidate_start": str(proposal.quantity_span.char_start),
        "quantity_candidate_end": str(proposal.quantity_span.char_end),
        "quantity_candidate_literal": proposal.quantity_span.literal,
        "quantity_candidate_kind": proposal.quantity_kind,
    }
    for field, value in expected.items():
        if row.get(field, "") != value:
            raise ValueError(f"immutable adjudication field changed: {field}")


def _verify_context_audits(
    *,
    rows: tuple[dict[str, str], ...],
    channel: str,
    expected_context_ids: set[str],
    queue_by_context: dict[str, tuple[AnnotationReviewItem, ...]],
) -> _ContextAudit:
    indexed = _index(rows, "context_id", f"annotator {channel} context audit")
    if set(indexed) != expected_context_ids:
        raise ValueError(f"annotator {channel} context audit set mismatch")
    identities = set()
    complete_context_ids = set()
    incomplete_context_ids = set()
    for context_id, row in indexed.items():
        if row.get("annotation_channel", "").strip() != channel:
            raise ValueError(f"annotator {channel} context channel mismatch")
        completeness = row.get("candidate_graph_complete", "").strip().upper()
        if completeness not in {"YES", "TRUE", "NO", "FALSE"}:
            raise ValueError(
                f"annotator {channel} candidate graph decision must be TRUE/FALSE"
            )
        missing_details = any(row.get(field, "").strip() for field in (
            "missing_metric_mentions", "missing_quantity_mentions", "missing_pairs"
        ))
        if completeness in {"YES", "TRUE"} and missing_details:
            raise ValueError(
                f"annotator {channel} marked a graph complete with missing details"
            )
        if completeness in {"NO", "FALSE"} and not missing_details:
            raise ValueError(
                f"annotator {channel} incomplete graph requires recovery details"
            )
        target = (
            complete_context_ids
            if completeness in {"YES", "TRUE"}
            else incomplete_context_ids
        )
        target.add(context_id)
        expected_items = queue_by_context[context_id]
        expected = {
            "source_slice": expected_items[0].source_slice.value,
            "entity": expected_items[0].entity,
            "source_sha256": expected_items[0].source_sha256,
            "source_path": expected_items[0].source_path,
            "text": expected_items[0].text,
            "document_char_start": str(expected_items[0].document_char_start),
            "document_char_end": str(expected_items[0].document_char_end),
            "candidate_pair_count": str(len(expected_items)),
        }
        for field, value in expected.items():
            if row.get(field, "") != value:
                raise ValueError(f"immutable context audit field changed: {field}")
        annotator_id = row.get("annotator_id", "").strip()
        if not annotator_id:
            raise ValueError(f"annotator {channel} context identity is blank")
        identities.add(annotator_id)
    return _ContextAudit(
        annotator_ids=frozenset(identities),
        complete_context_ids=frozenset(complete_context_ids),
        incomplete_context_ids=frozenset(incomplete_context_ids),
    )


def ingest_gold_a_batch(
    *,
    batch_root: Path,
    review_queue_path: Path,
    required_contexts_per_slice: int = 50,
) -> GoldABatchIngestion:
    """Validate completed A/B/adjudication CSVs and emit only genuine GOLD_A."""

    queue = {
        item.queue_item_id: item
        for item in load_annotation_review_queue(review_queue_path)
        if item.proposal is not None
    }
    a_rows = _read_csv(batch_root / "annotator_a_pairs.csv")
    b_rows = _read_csv(batch_root / "annotator_b_pairs.csv")
    c_rows = _read_csv(batch_root / "adjudication_template.csv")
    a_pairs = _index(a_rows, "pair_id", "annotator A pairs")
    b_pairs = _index(b_rows, "pair_id", "annotator B pairs")
    adjudications = _index(c_rows, "pair_id", "adjudications")
    if not (set(a_pairs) == set(b_pairs) == set(adjudications)):
        raise ValueError("A/B/adjudication pair sets do not match")
    if not set(a_pairs) <= set(queue):
        raise ValueError("human batch contains pairs outside the active review queue")
    expected_context_ids = {queue[pair_id].candidate_id for pair_id in a_pairs}
    queue_by_context: dict[str, tuple[AnnotationReviewItem, ...]] = {
        context_id: tuple(
            item for item in queue.values() if item.candidate_id == context_id
        )
        for context_id in expected_context_ids
    }
    complete_pair_ids = {
        item.queue_item_id
        for rows in queue_by_context.values()
        for item in rows
    }
    if set(a_pairs) != complete_pair_ids:
        raise ValueError(
            "submitted contexts do not contain the complete active metric×quantity graph"
        )
    a_context_audit = _verify_context_audits(
        rows=_read_csv(batch_root / "annotator_a_context_audit.csv"),
        channel="A",
        expected_context_ids=expected_context_ids,
        queue_by_context=queue_by_context,
    )
    b_context_audit = _verify_context_audits(
        rows=_read_csv(batch_root / "annotator_b_context_audit.csv"),
        channel="B",
        expected_context_ids=expected_context_ids,
        queue_by_context=queue_by_context,
    )
    if a_context_audit.annotator_ids & b_context_audit.annotator_ids:
        raise ValueError("annotator A and B identities must be disjoint")
    accepted_context_ids = (
        a_context_audit.complete_context_ids
        & b_context_audit.complete_context_ids
    )
    excluded_context_ids = expected_context_ids - accepted_context_ids
    a_pair_ids = {row.get("annotator_id", "").strip() for row in a_rows}
    b_pair_ids = {row.get("annotator_id", "").strip() for row in b_rows}
    if "" in a_pair_ids or "" in b_pair_ids or a_pair_ids & b_pair_ids:
        raise ValueError("annotator A and B pair identities must be non-empty and disjoint")
    adjudicator_ids = {
        row.get("adjudicator_id", "").strip() for row in c_rows
    }
    if (
        "" in adjudicator_ids
        or adjudicator_ids & a_pair_ids
        or adjudicator_ids & b_pair_ids
    ):
        raise ValueError("adjudicator identities must be globally separate from A/B")
    output = []
    quarantined = []
    agreements = 0
    for pair_id in sorted(a_pairs):
        item = queue[pair_id]
        a_row = a_pairs[pair_id]
        b_row = b_pairs[pair_id]
        c_row = adjudications[pair_id]
        _assert_immutable_pair_fields(a_row, item)
        _assert_immutable_pair_fields(b_row, item)
        _assert_immutable_adjudication_fields(c_row, item)
        if a_row.get("annotation_channel", "").strip() != "A":
            raise ValueError("annotator A pair channel mismatch")
        if b_row.get("annotation_channel", "").strip() != "B":
            raise ValueError("annotator B pair channel mismatch")
        a_id = a_row.get("annotator_id", "").strip()
        b_id = b_row.get("annotator_id", "").strip()
        if not a_id or not b_id or a_id == b_id:
            raise ValueError("pair annotations require independent A/B identities")
        if (
            a_id not in a_context_audit.annotator_ids
            or b_id not in b_context_audit.annotator_ids
        ):
            raise ValueError("pair annotator identity is absent from its context audit")
        annotation_a = _pair_annotation(a_row)
        annotation_b = _pair_annotation(b_row)
        equal = annotation_a == annotation_b
        expected_agreement = "AGREED" if equal else "DISAGREEMENT"
        if c_row.get("agreement_status", "").strip() != expected_agreement:
            raise ValueError(f"incorrect agreement status for pair {pair_id}")
        prefix_rows = {"a": (a_id, annotation_a), "b": (b_id, annotation_b)}
        for channel, (annotator_id, annotation) in prefix_rows.items():
            if c_row.get(f"annotator_{channel}_id", "").strip() != annotator_id:
                raise ValueError(f"adjudication annotator {channel} identity mismatch")
            transcribed = _annotation(
                c_row,
                prefix=f"annotator_{channel}",
                text=c_row.get("text", ""),
            )
            if transcribed != annotation:
                raise ValueError(
                    f"adjudication transcription mismatch for annotator {channel}"
                )
        adjudicator_id = c_row.get("adjudicator_id", "").strip()
        if not adjudicator_id or adjudicator_id in {a_id, b_id}:
            raise ValueError("adjudicator must be separate from both annotators")
        if c_row.get("text", "") != item.text:
            raise ValueError("adjudication source text changed")
        final = _annotation(c_row, prefix="final", text=item.text)
        reviewed = record_human_annotation(
            item, HumanPairAnnotation(a_id, annotation_a)
        )
        reviewed = record_human_annotation(
            reviewed, HumanPairAnnotation(b_id, annotation_b)
        )
        adjudicated = adjudicate_review_item(
            reviewed,
            adjudicator_id=adjudicator_id,
            final_annotation=final,
        )
        if item.candidate_id not in accepted_context_ids:
            quarantined.append(replace(
                adjudicated,
                quality_tier=AnnotationQualityTier.GOLD_B,
            ))
            continue
        agreements += int(equal)
        output.append(adjudicated)
    if not output:
        raise ValueError("no jointly complete candidate graph remains for GOLD_A")
    context_counts = Counter(
        next(item.source_slice.value for item in output if item.candidate_id == context_id)
        for context_id in accepted_context_ids
    )
    for source_slice in BENCHMARK_SOURCE_SLICES:
        if context_counts[source_slice.value] < required_contexts_per_slice:
            raise ValueError(
                f"{source_slice.value} has {context_counts[source_slice.value]} "
                f"completed contexts; requires {required_contexts_per_slice}"
            )
    return GoldABatchIngestion(
        items=tuple(output),
        quarantined_items=tuple(quarantined),
        context_counts=dict(sorted(context_counts.items())),
        excluded_context_counts=dict(sorted(Counter(
            queue_by_context[context_id][0].source_slice.value
            for context_id in excluded_context_ids
        ).items())),
        pair_counts=dict(sorted(Counter(
            item.source_slice.value for item in output
        ).items())),
        exact_pair_agreement=agreements / len(output),
    )


__all__ = ["GoldABatchIngestion", "ingest_gold_a_batch"]
