from __future__ import annotations

from equity_platform.documents import CanonicalDocument

from .annotation import AnnotationSourceSlice
from .document_queue import DocumentReviewQueue, build_document_review_queue


_DOCUMENT_SLICES = {
    "EARNINGS_CALL_PREPARED_REMARKS": AnnotationSourceSlice.IR_PREPARED_REMARKS,
    "EARNINGS_CALL_QA": AnnotationSourceSlice.IR_QA,
}


TranscriptReviewQueue = DocumentReviewQueue


def build_transcript_review_queue(
    *,
    documents: tuple[CanonicalDocument, ...],
    maximum_contexts_per_slice: int = 200,
    maximum_context_characters: int = 1_600,
) -> TranscriptReviewQueue:
    """Create review-only candidate graphs from prepared and Q&A sentences.

    No cross-product edge is treated as a weak positive or negative label.  A
    human must decide concept, binding and role before the context can become
    training data.
    """

    return build_document_review_queue(
        documents=documents,
        document_slices=_DOCUMENT_SLICES,
        slice_order=(
            AnnotationSourceSlice.IR_PREPARED_REMARKS,
            AnnotationSourceSlice.IR_QA,
        ),
        maximum_contexts_per_slice=maximum_contexts_per_slice,
        maximum_context_characters=maximum_context_characters,
        excluded_source_hashes=frozenset(),
        generator="TRANSCRIPT_CANDIDATE_GRAPH_V1",
        lineage_marker="ALPHA_VANTAGE_TRANSCRIPT_CANDIDATE_GRAPH_V1",
        maximum_pair_proposals_per_context=None,
    )


__all__ = ["TranscriptReviewQueue", "build_transcript_review_queue"]
