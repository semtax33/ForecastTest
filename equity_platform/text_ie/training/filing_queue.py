from __future__ import annotations

from equity_platform.documents import CanonicalDocument

from .annotation import AnnotationSourceSlice
from .document_queue import DocumentReviewQueue, build_document_review_queue


_DOCUMENT_SLICES = {
    "10-K": AnnotationSourceSlice.SEC_10K,
    "10-Q": AnnotationSourceSlice.SEC_10Q,
}

FilingReviewQueue = DocumentReviewQueue


def build_filing_review_queue(
    *,
    documents: tuple[CanonicalDocument, ...],
    maximum_contexts_per_slice: int = 50,
    maximum_context_characters: int = 1_600,
    excluded_source_hashes: frozenset[str] = frozenset(),
    maximum_pair_proposals_per_context: int = 64,
) -> FilingReviewQueue:
    return build_document_review_queue(
        documents=documents,
        document_slices=_DOCUMENT_SLICES,
        slice_order=(
            AnnotationSourceSlice.SEC_10K,
            AnnotationSourceSlice.SEC_10Q,
        ),
        maximum_contexts_per_slice=maximum_contexts_per_slice,
        maximum_context_characters=maximum_context_characters,
        excluded_source_hashes=excluded_source_hashes,
        generator="SEC_FILING_CANDIDATE_GRAPH_V1",
        lineage_marker="ARCANA_SEC_FILING_CANDIDATE_GRAPH_V1",
        maximum_pair_proposals_per_context=maximum_pair_proposals_per_context,
    )


__all__ = ["FilingReviewQueue", "build_filing_review_queue"]
