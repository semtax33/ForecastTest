from equity_platform.text_ie.learned import (
    DEFAULT_SPAN_MODEL_CANDIDATES,
    SpanModelFamily,
    build_span_benchmark_matrix,
    span_models_for_source,
)
from equity_platform.text_ie.llm import EncoderSourceSlice


def test_span_registry_routes_sec_and_ir_to_different_model_families() -> None:
    sec = span_models_for_source(EncoderSourceSlice.SEC_10K)
    ir = span_models_for_source(EncoderSourceSlice.IR_PREPARED_REMARKS)

    assert {item.model_id for item in sec} == {
        "AAU-NLP/BERT-SL1000",
        "AAU-NLP/Cal-BERT-SL1000",
    }
    assert {item.family for item in sec} == {SpanModelFamily.TOKEN_CLASSIFICATION}
    assert {item.model_id for item in ir} == {"fastino/gliner2-base-v1"}
    assert {item.family for item in ir} == {SpanModelFamily.SCHEMA_EXTRACTION}


def test_span_registry_has_no_production_champion_before_independent_benchmark() -> None:
    assert not any(item.runtime_champion for item in DEFAULT_SPAN_MODEL_CANDIDATES)
    matrix = build_span_benchmark_matrix()
    assert len(matrix) == 6
    assert {item.status for item in matrix} == {"NOT_RUN"}
