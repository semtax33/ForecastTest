from __future__ import annotations

import re

from equity_platform.documents import CanonicalDocument, DocumentSentence

from .model import TextBlock


def _fallback_sentences(text: str) -> tuple[DocumentSentence, ...]:
    boundaries = [0]
    boundaries.extend(
        match.end()
        for match in re.finditer(r"(?<=[.!?])\s+(?=[A-Z$])", text)
    )
    boundaries.append(len(text))
    rows: list[DocumentSentence] = []
    for start, end in zip(boundaries, boundaries[1:]):
        literal = text[start:end].strip()
        if not literal:
            continue
        actual_start = text.find(literal, start, end)
        rows.append(
            DocumentSentence(
                sentence_index=len(rows),
                text=literal,
                char_start=actual_start,
                char_end=actual_start + len(literal),
            )
        )
    return tuple(rows)


def _split_bullets(sentence: DocumentSentence) -> tuple[DocumentSentence, ...]:
    """Split flattened release bullets while preserving exact source offsets."""

    boundaries = [0]
    boundaries.extend(match.end() for match in re.finditer(r"\s*[•]\s*", sentence.text))
    boundaries.append(len(sentence.text))
    rows: list[DocumentSentence] = []
    for start, end in zip(boundaries, boundaries[1:]):
        literal = sentence.text[start:end].strip()
        if not literal:
            continue
        local_start = sentence.text.find(literal, start, end)
        rows.append(
            DocumentSentence(
                sentence_index=sentence.sentence_index,
                text=literal,
                char_start=sentence.char_start + local_start,
                char_end=sentence.char_start + local_start + len(literal),
                section=sentence.section,
                heading=sentence.heading,
                inline_fact_indices=sentence.inline_fact_indices,
            )
        )
    return tuple(rows)


def document_text_blocks(document: CanonicalDocument) -> tuple[TextBlock, ...]:
    source_sentences = document.sentences or _fallback_sentences(document.text)
    sentences = tuple(
        clause
        for sentence in source_sentences
        for clause in _split_bullets(sentence)
    )
    return tuple(
        TextBlock(
            entity=document.metadata.entity,
            text=sentence.text,
            source=document.source,
            sentence_index=index,
            char_start=sentence.char_start,
            char_end=sentence.char_end,
            document_period=document.metadata.report_period,
            section=sentence.section,
            nearest_heading=sentence.heading,
            previous_sentence=(
                sentences[index - 1].text if index > 0 else None
            ),
            next_sentence=(
                sentences[index + 1].text if index + 1 < len(sentences) else None
            ),
            inline_fact_indices=sentence.inline_fact_indices,
        )
        for index, sentence in enumerate(sentences)
    )
