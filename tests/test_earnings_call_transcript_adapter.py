from __future__ import annotations

from hashlib import sha256
import json

import pytest

from equity_platform.documents.earnings_call import (
    TranscriptBoundaryMethod,
    TranscriptSection,
    adapt_alpha_vantage_transcript,
    load_alpha_vantage_transcript_corpus,
    transcript_canonical_documents,
)
from equity_platform.text_ie.document import document_text_blocks


def _write_transcript(
    tmp_path,
    *,
    turns: list[dict[str, str]] | None,
    status: str = "ok",
    ticker: str = "EOG",
    year: int = 2025,
    quarter: int = 2,
):
    path = (
        tmp_path
        / f"ticker={ticker}"
        / f"fiscal_year={year}"
        / f"quarter=Q{quarter}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "provider": "ALPHA_VANTAGE",
        "dataset": "EARNINGS_CALL_TRANSCRIPT",
        "status": status,
        "complete": True,
        "retrieved_at": "2026-08-30T13:12:14.934694+00:00",
        "data": (
            {
                "symbol": ticker,
                "quarter": f"{year}Q{quarter}",
                "transcript": turns,
            }
            if status == "ok"
            else []
        ),
        "symbol": ticker,
        "fiscal_year": year,
        "quarter": quarter,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _turn(speaker: str, title: str, content: str) -> dict[str, str]:
    return {
        "speaker": speaker,
        "title": title,
        "content": content,
        "sentiment": "0.0",
    }


def test_adapter_validates_partition_hash_and_uses_retrieval_as_conservative_availability(
    tmp_path,
) -> None:
    path = _write_transcript(
        tmp_path,
        turns=[_turn("CEO", "Chief Executive Officer", "Revenue was $10 million.")],
    )
    expected = sha256(path.read_bytes()).hexdigest()

    transcript = adapt_alpha_vantage_transcript(path, expected_sha256=expected)

    assert transcript.entity == "EOG"
    assert transcript.period == "2025Q2"
    assert transcript.source.sha256 == expected
    assert transcript.source.available_at == "2026-08-30T13:12:14.934694+00:00"
    assert transcript.call_occurred_at is None
    assert transcript.available_at_basis == "ARCHIVE_RETRIEVED_AT"

    with pytest.raises(ValueError, match="hash mismatch"):
        adapt_alpha_vantage_transcript(path, expected_sha256="0" * 64)


def test_adapter_splits_prepared_and_qa_from_explicit_transcript_structure(tmp_path) -> None:
    path = _write_transcript(
        tmp_path,
        turns=[
            _turn("Operator", "Operator", "Welcome to the quarterly call."),
            _turn("Jane Doe", "CEO", "Revenue was $10 million. Margin was 20%."),
            _turn(
                "Operator",
                "Operator",
                "We will now begin the question-and-answer session. The first question is from Alex.",
            ),
            _turn("Alex Roe", "Analyst (UBS)", "Could revenue reach $12 million?"),
            _turn("Jane Doe", "CEO", "We expect about $11 million."),
            _turn(
                "Operator",
                "Operator",
                "This concludes the question-and-answer session.",
            ),
            _turn("Jane Doe", "CEO", "Thank you for joining us."),
        ],
    )

    transcript = adapt_alpha_vantage_transcript(path)

    assert transcript.boundary_method is TranscriptBoundaryMethod.OPERATOR_QA_CUE
    assert [turn.section for turn in transcript.turns] == [
        TranscriptSection.PREPARED_REMARKS,
        TranscriptSection.PREPARED_REMARKS,
        TranscriptSection.QA,
        TranscriptSection.QA,
        TranscriptSection.QA,
        TranscriptSection.QA,
        TranscriptSection.UNSPECIFIED,
    ]
    documents = transcript_canonical_documents(transcript)
    assert [document.metadata.document_kind for document in documents] == [
        "EARNINGS_CALL_PREPARED_REMARKS",
        "EARNINGS_CALL_QA",
        "EARNINGS_CALL_UNSPECIFIED",
    ]
    prepared_blocks = document_text_blocks(documents[0])
    assert prepared_blocks[1].section == "IR_PREPARED_REMARKS"
    assert prepared_blocks[1].nearest_heading == "Jane Doe — CEO"
    assert prepared_blocks[1].previous_sentence == "Welcome to the quarterly call."
    assert prepared_blocks[1].next_sentence == "Margin was 20%."


def test_analyst_title_variant_is_a_structured_fallback_not_an_alias_list(tmp_path) -> None:
    path = _write_transcript(
        tmp_path,
        turns=[
            _turn("CEO", "Chief Executive Officer", "Prepared remarks."),
            _turn("Alex Roe", "Senior Equity Analyst, JPMorgan", "My question is about revenue."),
            _turn("CEO", "Chief Executive Officer", "Revenue was $10 million."),
        ],
    )

    transcript = adapt_alpha_vantage_transcript(path)

    assert transcript.boundary_method is TranscriptBoundaryMethod.ANALYST_ROLE
    assert transcript.turns[0].section is TranscriptSection.PREPARED_REMARKS
    assert transcript.turns[1].section is TranscriptSection.QA


def test_ambiguous_call_is_not_silently_labeled_as_prepared_remarks(tmp_path) -> None:
    path = _write_transcript(
        tmp_path,
        turns=[
            _turn("Unknown", "", "Revenue was $10 million."),
            _turn("Unknown", "", "Thank you."),
        ],
    )

    transcript = adapt_alpha_vantage_transcript(path)

    assert transcript.boundary_method is TranscriptBoundaryMethod.NOT_IDENTIFIED
    assert all(turn.section is TranscriptSection.UNSPECIFIED for turn in transcript.turns)


def test_no_data_is_observable_but_does_not_create_documents(tmp_path) -> None:
    path = _write_transcript(tmp_path, turns=None, status="no_data")

    transcript = adapt_alpha_vantage_transcript(path)

    assert transcript.status == "NO_DATA"
    assert transcript.turns == ()
    assert transcript_canonical_documents(transcript) == ()


def test_provider_ok_with_blank_turn_is_quarantined_as_partial_content(tmp_path) -> None:
    path = _write_transcript(
        tmp_path,
        turns=[
            _turn("CEO", "Chief Executive Officer", "Revenue was $10 million."),
            _turn("Analyst", "Analyst", ""),
        ],
    )

    transcript = adapt_alpha_vantage_transcript(path)

    assert transcript.status == "PARTIAL_CONTENT"
    assert transcript.empty_turn_count == 1
    assert transcript_canonical_documents(transcript) == ()


def test_payload_identity_cannot_disagree_with_storage_partition(tmp_path) -> None:
    path = _write_transcript(tmp_path, turns=[_turn("CEO", "CEO", "Hello.")])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["symbol"] = "FANG"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="partition identity"):
        adapt_alpha_vantage_transcript(path)


def test_corpus_loader_counts_missing_and_no_data_and_selects_latest_ok(tmp_path) -> None:
    _write_transcript(
        tmp_path,
        ticker="EOG",
        year=2024,
        quarter=4,
        turns=[_turn("Operator", "Operator", "The first question is from Alex."),
               _turn("Alex", "Analyst", "Revenue was $9 million.")],
    )
    _write_transcript(
        tmp_path,
        ticker="EOG",
        year=2025,
        quarter=1,
        turns=[_turn("Operator", "Operator", "The first question is from Alex."),
               _turn("Alex", "Analyst", "Revenue was $10 million.")],
    )
    _write_transcript(
        tmp_path,
        ticker="EOG",
        year=2025,
        quarter=2,
        turns=None,
        status="no_data",
    )
    _write_transcript(
        tmp_path,
        ticker="FANG",
        year=2025,
        quarter=2,
        turns=[_turn("Unknown", "", "Revenue was $8 million.")],
    )

    corpus = load_alpha_vantage_transcript_corpus(
        root=tmp_path,
        entities=("EOG", "FANG", "MISSING"),
        maximum_ok_per_entity=1,
    )

    assert len(corpus.transcripts) == 4
    assert corpus.ok_count == 3
    assert corpus.no_data_count == 1
    assert corpus.missing_entities == ("MISSING",)
    assert [(row.entity, row.period) for row in corpus.selected_transcripts] == [
        ("EOG", "2025Q1"),
        ("FANG", "2025Q2"),
    ]
    assert corpus.boundary_method_counts == {
        "ANALYST_ROLE": 0,
        "NOT_IDENTIFIED": 1,
        "OPERATOR_QA_CUE": 2,
    }
