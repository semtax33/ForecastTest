from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping

from equity_platform.documents import CanonicalDocument

from ..document import document_text_blocks
from ..ontology import find_concepts
from ..quantities import extract_quantities
from .annotation import (
    AdjudicationStatus,
    AnnotationQualityTier,
    AnnotationReviewItem,
    AnnotationSourceSlice,
    PairProposal,
    TextSpan,
)


@dataclass(frozen=True)
class DocumentReviewQueue:
    items: tuple[AnnotationReviewItem, ...]
    eligible_contexts: int
    selected_contexts: int
    eligible_contexts_by_slice: dict[str, int]
    selected_contexts_by_slice: dict[str, int]
    excluded_oversized_contexts: int = 0
    excluded_dense_contexts: int = 0


@dataclass(frozen=True)
class _CandidateContext:
    document: CanonicalDocument
    source_slice: AnnotationSourceSlice
    sentence_index: int
    char_start: int
    char_end: int
    text: str
    concepts: tuple
    quantities: tuple


def _balanced_sample(
    candidates: tuple[_CandidateContext, ...],
    maximum: int,
) -> tuple[_CandidateContext, ...]:
    by_entity: dict[str, deque[_CandidateContext]] = defaultdict(deque)
    for candidate in sorted(
        candidates,
        key=lambda row: (
            row.document.metadata.entity,
            row.document.metadata.report_period or "",
            row.document.source.sha256,
            row.sentence_index,
        ),
    ):
        by_entity[candidate.document.metadata.entity].append(candidate)
    selected: list[_CandidateContext] = []
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


def _candidate_id(context: _CandidateContext) -> str:
    material = "|".join((
        context.document.source.sha256,
        context.source_slice.value,
        str(context.sentence_index),
        str(context.char_start),
        str(context.char_end),
        context.text,
    ))
    return sha256(material.encode()).hexdigest()[:24]


def build_document_review_queue(
    *,
    documents: tuple[CanonicalDocument, ...],
    document_slices: Mapping[str, AnnotationSourceSlice],
    slice_order: tuple[AnnotationSourceSlice, ...],
    maximum_contexts_per_slice: int,
    maximum_context_characters: int,
    excluded_source_hashes: frozenset[str],
    generator: str,
    lineage_marker: str,
    maximum_pair_proposals_per_context: int | None = None,
) -> DocumentReviewQueue:
    """Build source-balanced metric×quantity graphs without assigning labels."""

    if maximum_contexts_per_slice < 1:
        raise ValueError("maximum_contexts_per_slice must be positive")
    if maximum_context_characters < 128:
        raise ValueError("maximum_context_characters must be at least 128")
    candidates_by_slice: dict[AnnotationSourceSlice, list[_CandidateContext]] = defaultdict(list)
    excluded_oversized_contexts = 0
    excluded_dense_contexts = 0
    for document in documents:
        if document.source.sha256 in excluded_source_hashes:
            continue
        source_slice = document_slices.get(document.metadata.document_kind)
        if source_slice is None:
            continue
        blocks = document_text_blocks(document)
        seen_windows: set[tuple[int, int]] = set()
        for index, block in enumerate(blocks):
            if block.char_end - block.char_start > maximum_context_characters:
                # A target sentence is atomic evidence.  Silently clipping it
                # would invalidate mention offsets and the surrounding meaning.
                excluded_oversized_contexts += 1
                continue
            target_concepts = find_concepts(block.text)
            target_quantities = extract_quantities(block.text)
            if not target_concepts or not target_quantities:
                continue
            char_start = block.char_start
            char_end = block.char_end
            if (
                index > 0
                and char_end - blocks[index - 1].char_start <= maximum_context_characters
            ):
                char_start = blocks[index - 1].char_start
            if (
                index + 1 < len(blocks)
                and blocks[index + 1].char_end - char_start <= maximum_context_characters
            ):
                char_end = blocks[index + 1].char_end
            window_key = (char_start, char_end)
            if window_key in seen_windows:
                continue
            seen_windows.add(window_key)
            text = document.text[char_start:char_end]
            concepts = find_concepts(text)
            quantities = extract_quantities(text)
            if (
                maximum_pair_proposals_per_context is not None
                and len(concepts) * len(quantities)
                > maximum_pair_proposals_per_context
            ):
                # Dense statement tables belong on TABLE_DSL.  Expanding their
                # Cartesian product into narrative labels is both misleading
                # and an unbounded human-review burden.
                excluded_dense_contexts += 1
                continue
            candidates_by_slice[source_slice].append(_CandidateContext(
                document=document,
                source_slice=source_slice,
                sentence_index=block.sentence_index,
                char_start=char_start,
                char_end=char_end,
                text=text,
                concepts=concepts,
                quantities=quantities,
            ))
    selected = tuple(
        context
        for source_slice in slice_order
        for context in _balanced_sample(
            tuple(candidates_by_slice[source_slice]), maximum_contexts_per_slice
        )
    )
    items: list[AnnotationReviewItem] = []
    for context in selected:
        candidate_id = _candidate_id(context)
        for concept in context.concepts:
            for quantity in context.quantities:
                suffix = "|".join((
                    candidate_id,
                    str(concept.char_start),
                    str(concept.char_end),
                    str(quantity.char_start),
                    str(quantity.char_end),
                ))
                items.append(AnnotationReviewItem(
                    schema_version="1.0.0",
                    queue_item_id=sha256(suffix.encode()).hexdigest()[:24],
                    candidate_id=candidate_id,
                    entity=context.document.metadata.entity,
                    source_path=context.document.source.local_path,
                    source_sha256=context.document.source.sha256,
                    source_slice=context.source_slice,
                    document_char_start=context.char_start,
                    document_char_end=context.char_end,
                    text=context.text,
                    proposal=PairProposal(
                        metric_span=TextSpan(
                            concept.char_start,
                            concept.char_end,
                            context.text[concept.char_start:concept.char_end],
                        ),
                        quantity_span=TextSpan(
                            quantity.char_start,
                            quantity.char_end,
                            context.text[quantity.char_start:quantity.char_end],
                        ),
                        concept_label=concept.concept,
                        binding_hint="UNREVIEWED",
                        role_hint=None,
                        generator=generator,
                        quantity_kind=quantity.kind.value,
                    ),
                    legacy_route="TEXT_IE",
                    legacy_expected_frames=(),
                    legacy_annotation_files=(lineage_marker,),
                    adjudication_status=AdjudicationStatus.PENDING,
                    quality_tier=AnnotationQualityTier.WEAK,
                    split="UNASSIGNED",
                ))
    return DocumentReviewQueue(
        items=tuple(items),
        eligible_contexts=sum(len(rows) for rows in candidates_by_slice.values()),
        selected_contexts=len(selected),
        eligible_contexts_by_slice={
            source_slice.value: len(candidates_by_slice[source_slice])
            for source_slice in slice_order
        },
        selected_contexts_by_slice={
            source_slice.value: sum(
                context.source_slice is source_slice for context in selected
            )
            for source_slice in slice_order
        },
        excluded_oversized_contexts=excluded_oversized_contexts,
        excluded_dense_contexts=excluded_dense_contexts,
    )


__all__ = ["DocumentReviewQueue", "build_document_review_queue"]
