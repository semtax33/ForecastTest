from __future__ import annotations


COMPATIBILITY_STATUS = "GPU_COMPATIBILITY_ONLY_NOT_PERFORMANCE"
SEC_BERT_SHAPE_MODEL_ID = "nlpaueb/sec-bert-shape"


def sec_bert_shape_preprocess(text: str, *, tokenizer, nlp) -> str:
    """Apply the SEC-BERT-SHAPE model card's numeric-token contract.

    spaCy owns token boundaries.  This function only maps numeric tokens to
    model-vocabulary shape tokens and deliberately does not extract facts.
    """

    special_tokens = set(tokenizer.additional_special_tokens)
    processed: list[str] = []
    for token in nlp.make_doc(text):
        literal = token.text
        if token.like_num and any(character.isdigit() for character in literal):
            shape = "[" + "".join(
                "X" if character.isdigit() else character
                for character in literal
            ) + "]"
            processed.append(shape if shape in special_tokens else "[NUM]")
        else:
            processed.append(literal)
    return " ".join(processed)


def preprocess_encoder_text(
    text: str,
    *,
    model_id: str,
    tokenizer,
    nlp,
) -> str:
    if model_id == SEC_BERT_SHAPE_MODEL_ID:
        return sec_bert_shape_preprocess(text, tokenizer=tokenizer, nlp=nlp)
    return text


__all__ = [
    "COMPATIBILITY_STATUS",
    "SEC_BERT_SHAPE_MODEL_ID",
    "preprocess_encoder_text",
    "sec_bert_shape_preprocess",
]
