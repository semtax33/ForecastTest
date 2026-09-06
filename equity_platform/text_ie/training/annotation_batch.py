from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256

from .annotation import AnnotationReviewItem, AnnotationSourceSlice


_BATCH_SOURCE_SLICES = (
    AnnotationSourceSlice.SEC_10K,
    AnnotationSourceSlice.SEC_10Q,
    AnnotationSourceSlice.IR_PREPARED_REMARKS,
    AnnotationSourceSlice.IR_QA,
)


@dataclass(frozen=True)
class BlindAnnotationBatch:
    context_rows: tuple[dict[str, object], ...]
    pair_rows: tuple[dict[str, object], ...]
    annotator_a_rows: tuple[dict[str, object], ...]
    annotator_b_rows: tuple[dict[str, object], ...]


def _balanced_contexts(
    contexts: dict[str, tuple[AnnotationReviewItem, ...]],
    maximum: int,
) -> tuple[tuple[AnnotationReviewItem, ...], ...]:
    by_entity: dict[str, deque[tuple[AnnotationReviewItem, ...]]] = defaultdict(deque)
    for items in sorted(
        contexts.values(), key=lambda rows: (rows[0].entity, rows[0].candidate_id)
    ):
        by_entity[items[0].entity].append(items)
    selected = []
    entities = tuple(sorted(by_entity))
    while len(selected) < maximum:
        progressed = False
        for entity in entities:
            if by_entity[entity] and len(selected) < maximum:
                selected.append(by_entity[entity].popleft())
                progressed = True
        if not progressed:
            break
    return tuple(selected)


def _blind_pair_row(item: AnnotationReviewItem) -> dict[str, object]:
    proposal = item.proposal
    if proposal is None:
        raise ValueError("blind pair rows require a metric×quantity proposal")
    return {
        "pair_id": item.queue_item_id,
        "context_id": item.candidate_id,
        "source_slice": item.source_slice.value,
        "entity": item.entity,
        "source_sha256": item.source_sha256,
        "source_path": item.source_path,
        "document_char_start": item.document_char_start,
        "document_char_end": item.document_char_end,
        "text": item.text,
        "metric_candidate_start": proposal.metric_span.char_start,
        "metric_candidate_end": proposal.metric_span.char_end,
        "metric_candidate_literal": proposal.metric_span.literal,
        "quantity_candidate_start": proposal.quantity_span.char_start,
        "quantity_candidate_end": proposal.quantity_span.char_end,
        "quantity_candidate_literal": proposal.quantity_span.literal,
        "quantity_candidate_kind": proposal.quantity_kind,
        "reviewed_metric_start": "",
        "reviewed_metric_end": "",
        "reviewed_metric_literal": "",
        "reviewed_quantity_start": "",
        "reviewed_quantity_end": "",
        "reviewed_quantity_literal": "",
        "reviewed_concept_label": "",
        "reviewed_binding_label": "",
        "reviewed_role_label": "",
        "reviewed_scope": "",
        "reviewed_period": "",
        "reviewed_quantity_kind": "",
        "annotator_id": "",
        "notes": "",
    }


def _assignment_rows(
    rows: tuple[dict[str, object], ...], channel: str
) -> tuple[dict[str, object], ...]:
    return tuple(
        {"annotation_channel": channel, **row}
        for row in sorted(
            rows,
            key=lambda row: sha256(
                f"TEXT_IE_GOLD_A_V1|{channel}|{row['pair_id']}".encode()
            ).hexdigest(),
        )
    )


def build_blind_annotation_batch(
    items: tuple[AnnotationReviewItem, ...],
    *,
    contexts_per_slice: int = 50,
) -> BlindAnnotationBatch:
    """Create two label-blind assignments from complete candidate graphs."""

    if contexts_per_slice < 1:
        raise ValueError("contexts_per_slice must be positive")
    grouped: dict[AnnotationSourceSlice, dict[str, list[AnnotationReviewItem]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for item in items:
        if item.source_slice in _BATCH_SOURCE_SLICES and item.proposal is not None:
            grouped[item.source_slice][item.candidate_id].append(item)
    selected_contexts = []
    for source_slice in _BATCH_SOURCE_SLICES:
        contexts = {
            candidate_id: tuple(sorted(rows, key=lambda row: row.queue_item_id))
            for candidate_id, rows in grouped[source_slice].items()
        }
        if len(contexts) < contexts_per_slice:
            raise ValueError(
                f"{source_slice.value} has {len(contexts)} pair contexts; "
                f"requires {contexts_per_slice}"
            )
        selected_contexts.extend(_balanced_contexts(contexts, contexts_per_slice))
    context_rows = tuple({
        "context_id": rows[0].candidate_id,
        "source_slice": rows[0].source_slice.value,
        "entity": rows[0].entity,
        "source_sha256": rows[0].source_sha256,
        "source_path": rows[0].source_path,
        "document_char_start": rows[0].document_char_start,
        "document_char_end": rows[0].document_char_end,
        "text": rows[0].text,
        "candidate_pair_count": len(rows),
        "candidate_graph_complete": "",
        "missing_metric_mentions": "",
        "missing_quantity_mentions": "",
        "missing_pairs": "",
        "annotator_id": "",
        "notes": "",
    } for rows in selected_contexts)
    pair_rows = tuple(
        _blind_pair_row(item)
        for rows in selected_contexts
        for item in rows
    )
    return BlindAnnotationBatch(
        context_rows=context_rows,
        pair_rows=pair_rows,
        annotator_a_rows=_assignment_rows(pair_rows, "A"),
        annotator_b_rows=_assignment_rows(pair_rows, "B"),
    )


__all__ = ["BlindAnnotationBatch", "build_blind_annotation_batch"]
