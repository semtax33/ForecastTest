from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..llm.encoder_registry import EncoderSourceSlice


class SpanModelFamily(StrEnum):
    TOKEN_CLASSIFICATION = "TOKEN_CLASSIFICATION"
    SCHEMA_EXTRACTION = "SCHEMA_EXTRACTION"


@dataclass(frozen=True)
class SpanModelCandidate:
    model_id: str
    family: SpanModelFamily
    source_slices: tuple[EncoderSourceSlice, ...]
    research_hypothesis: str
    runtime_champion: bool = False


@dataclass(frozen=True)
class SpanBenchmarkCell:
    model_id: str
    source_slice: EncoderSourceSlice
    status: str = "NOT_RUN"


_SEC_SLICES = (EncoderSourceSlice.SEC_10K, EncoderSourceSlice.SEC_10Q)
_IR_SLICES = (
    EncoderSourceSlice.IR_PREPARED_REMARKS,
    EncoderSourceSlice.IR_QA,
)


# Candidates are deliberately not production routes.  A source-slice winner
# requires issuer/document-disjoint human labels and the existing precision
# gates before ``runtime_champion`` may change.
DEFAULT_SPAN_MODEL_CANDIDATES = (
    SpanModelCandidate(
        model_id="AAU-NLP/BERT-SL1000",
        family=SpanModelFamily.TOKEN_CLASSIFICATION,
        source_slices=_SEC_SLICES,
        research_hypothesis="raw KPI span recall in SEC 10-K/10-Q narrative",
    ),
    SpanModelCandidate(
        model_id="AAU-NLP/Cal-BERT-SL1000",
        family=SpanModelFamily.TOKEN_CLASSIFICATION,
        source_slices=_SEC_SLICES,
        research_hypothesis="calculation-taxonomy abstraction for SEC KPI spans",
    ),
    SpanModelCandidate(
        model_id="fastino/gliner2-base-v1",
        family=SpanModelFamily.SCHEMA_EXTRACTION,
        source_slices=_IR_SLICES,
        research_hypothesis="schema-guided novel KPI span recall in IR language",
    ),
)


def span_models_for_source(
    source_slice: EncoderSourceSlice,
) -> tuple[SpanModelCandidate, ...]:
    return tuple(
        candidate
        for candidate in DEFAULT_SPAN_MODEL_CANDIDATES
        if source_slice in candidate.source_slices
    )


def build_span_benchmark_matrix() -> tuple[SpanBenchmarkCell, ...]:
    return tuple(
        SpanBenchmarkCell(candidate.model_id, source_slice)
        for candidate in DEFAULT_SPAN_MODEL_CANDIDATES
        for source_slice in candidate.source_slices
    )


__all__ = [
    "DEFAULT_SPAN_MODEL_CANDIDATES",
    "SpanBenchmarkCell",
    "SpanModelCandidate",
    "SpanModelFamily",
    "build_span_benchmark_matrix",
    "span_models_for_source",
]
