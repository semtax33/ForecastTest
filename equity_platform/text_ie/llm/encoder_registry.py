from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EncoderSourceSlice(StrEnum):
    SEC_10K = "SEC_10K"
    SEC_10Q = "SEC_10Q"
    IR_PREPARED_REMARKS = "IR_PREPARED_REMARKS"
    IR_QA = "IR_QA"


@dataclass(frozen=True)
class EncoderCandidate:
    model_id: str
    family: str
    research_hypothesis: str
    runtime_champion: bool = False


@dataclass(frozen=True)
class EncoderBenchmarkCell:
    model_id: str
    source_slice: EncoderSourceSlice
    status: str = "NOT_RUN"


# These are competing initialization checkpoints, not deployable classifier
# heads.  No source-to-model routing is authorized until independently
# adjudicated source-slice benchmarks are complete.
DEFAULT_ENCODER_CANDIDATES = (
    EncoderCandidate(
        model_id="yiyanghkust/finbert-pretrain",
        family="FINBERT_PRETRAIN",
        research_hypothesis="broad financial communication and earnings-call context",
    ),
    EncoderCandidate(
        model_id="SALT-NLP/FLANG-SpanBERT",
        family="FLANG_SPANBERT",
        research_hypothesis="span-aware metric and quantity binding",
    ),
    EncoderCandidate(
        model_id="nlpaueb/sec-bert-shape",
        family="SEC_BERT_SHAPE",
        research_hypothesis="filing language and numeric-shape context",
    ),
)


def build_encoder_benchmark_matrix() -> tuple[EncoderBenchmarkCell, ...]:
    return tuple(
        EncoderBenchmarkCell(candidate.model_id, source_slice)
        for candidate in DEFAULT_ENCODER_CANDIDATES
        for source_slice in EncoderSourceSlice
    )


__all__ = [
    "DEFAULT_ENCODER_CANDIDATES",
    "EncoderBenchmarkCell",
    "EncoderCandidate",
    "EncoderSourceSlice",
    "build_encoder_benchmark_matrix",
]
