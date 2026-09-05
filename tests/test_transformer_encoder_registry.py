from __future__ import annotations

from equity_platform.text_ie.llm import (
    DEFAULT_ENCODER_CANDIDATES,
    EncoderSourceSlice,
    build_encoder_benchmark_matrix,
)


def test_encoder_registry_keeps_all_feedback_candidates_without_a_champion() -> None:
    assert {candidate.model_id for candidate in DEFAULT_ENCODER_CANDIDATES} == {
        "yiyanghkust/finbert-pretrain",
        "SALT-NLP/FLANG-SpanBERT",
        "nlpaueb/sec-bert-shape",
    }
    assert all(not candidate.runtime_champion for candidate in DEFAULT_ENCODER_CANDIDATES)


def test_encoder_benchmark_matrix_separates_ir_and_filing_contexts() -> None:
    matrix = build_encoder_benchmark_matrix()

    assert len(matrix) == 12
    assert {cell.source_slice for cell in matrix} == set(EncoderSourceSlice)
    assert len({(cell.model_id, cell.source_slice) for cell in matrix}) == 12
    assert all(cell.status == "NOT_RUN" for cell in matrix)
