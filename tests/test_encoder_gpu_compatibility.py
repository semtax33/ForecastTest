from __future__ import annotations

import spacy

from equity_platform.text_ie.llm.encoder_compatibility import (
    COMPATIBILITY_STATUS,
    sec_bert_shape_preprocess,
)


class _Tokenizer:
    additional_special_tokens = ["[X]", "[X.X]", "[XX,XXX.X]", "[XXXX]", "[NUM]"]


def test_sec_bert_shape_preprocessing_uses_spacy_tokens_and_known_shapes() -> None:
    nlp = spacy.blank("en")

    result = sec_bert_shape_preprocess(
        "Sales decreased 2% or $5.4 million in 2025; backlog was 40,200.5.",
        tokenizer=_Tokenizer(),
        nlp=nlp,
    )

    assert result == (
        "Sales decreased [X] % or $ [X.X] million in [XXXX] ; "
        "backlog was [XX,XXX.X] ."
    )


def test_sec_bert_shape_preprocessing_falls_back_to_num_for_unknown_shape() -> None:
    nlp = spacy.blank("en")

    result = sec_bert_shape_preprocess(
        "Revenue was 12345678901234567890 units.",
        tokenizer=_Tokenizer(),
        nlp=nlp,
    )

    assert "[NUM]" in result
    assert "12345678901234567890" not in result


def test_gpu_check_is_explicitly_not_a_model_performance_benchmark() -> None:
    assert COMPATIBILITY_STATUS == "GPU_COMPATIBILITY_ONLY_NOT_PERFORMANCE"
