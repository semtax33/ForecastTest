from __future__ import annotations

from hashlib import sha256
import json

from equity_platform.documents.earnings_call import (
    adapt_alpha_vantage_transcript,
    transcript_canonical_documents,
)
from equity_platform.text_ie.training import (
    AnnotationSourceSlice,
    build_transcript_review_queue,
)


def _document(tmp_path, ticker: str, content: str):
    path = (
        tmp_path
        / f"ticker={ticker}"
        / "fiscal_year=2025"
        / "quarter=Q2.json"
    )
    path.parent.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "provider": "ALPHA_VANTAGE",
        "dataset": "EARNINGS_CALL_TRANSCRIPT",
        "status": "ok",
        "complete": True,
        "retrieved_at": "2026-08-30T13:12:14+00:00",
        "data": {
            "symbol": ticker,
            "quarter": "2025Q2",
            "transcript": [
                {
                    "speaker": "CEO",
                    "title": "Chief Executive Officer",
                    "content": "Prepared introduction.",
                    "sentiment": "0.0",
                },
                {
                    "speaker": "Operator",
                    "title": "Operator",
                    "content": "We will now begin the question-and-answer session.",
                    "sentiment": "0.0",
                },
                {
                    "speaker": "Analyst",
                    "title": "Analyst (Bank)",
                    "content": content,
                    "sentiment": "0.0",
                },
            ],
        },
        "symbol": ticker,
        "fiscal_year": 2025,
        "quarter": 2,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    transcript = adapt_alpha_vantage_transcript(path)
    return transcript_canonical_documents(transcript)


def test_transcript_queue_creates_only_unreviewed_source_sliced_candidate_graphs(
    tmp_path,
) -> None:
    documents = (
        *_document(tmp_path, "EOG", "Revenue was $10 million."),
        *_document(tmp_path, "FANG", "Adjusted EBITDA was $3 million."),
    )

    queue = build_transcript_review_queue(
        documents=documents,
        maximum_contexts_per_slice=10,
    )

    assert queue.eligible_contexts == 2
    assert queue.selected_contexts == 2
    assert {item.source_slice for item in queue.items} == {AnnotationSourceSlice.IR_QA}
    assert all(item.proposal.binding_hint == "UNREVIEWED" for item in queue.items)
    assert all(item.proposal.role_hint is None for item in queue.items)
    assert all(item.quality_tier == "WEAK" for item in queue.items)
    assert all(item.legacy_expected_frames == () for item in queue.items)
    assert len({item.queue_item_id for item in queue.items}) == len(queue.items)
    assert any(
        "question-and-answer session" in item.text
        and "Revenue was $10 million." in item.text
        for item in queue.items
    )
    assert all(
        item.text[item.proposal.metric_span.char_start:item.proposal.metric_span.char_end]
        == item.proposal.metric_span.literal
        for item in queue.items
    )


def test_transcript_queue_balances_entities_before_taking_more_from_one_issuer(
    tmp_path,
) -> None:
    eog = _document(
        tmp_path,
        "EOG",
        "Revenue was $10 million. Revenue was $11 million. Revenue was $12 million.",
    )
    fang = _document(tmp_path, "FANG", "Revenue was $9 million.")

    queue = build_transcript_review_queue(
        documents=(*eog, *fang),
        maximum_contexts_per_slice=2,
    )

    assert queue.selected_contexts == 2
    assert {item.entity for item in queue.items} == {"EOG", "FANG"}


def test_transcript_queue_excludes_unspecified_and_non_numeric_contexts(tmp_path) -> None:
    path = (
        tmp_path
        / "ticker=EOG"
        / "fiscal_year=2025"
        / "quarter=Q2.json"
    )
    path.parent.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "provider": "ALPHA_VANTAGE",
        "dataset": "EARNINGS_CALL_TRANSCRIPT",
        "status": "ok",
        "complete": True,
        "retrieved_at": "2026-08-30T13:12:14+00:00",
        "data": {
            "symbol": "EOG",
            "quarter": "2025Q2",
            "transcript": [
                {"speaker": "Unknown", "title": "", "content": "Revenue was $10 million.", "sentiment": "0.0"}
            ],
        },
        "symbol": "EOG",
        "fiscal_year": 2025,
        "quarter": 2,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    transcript = adapt_alpha_vantage_transcript(path)

    queue = build_transcript_review_queue(
        documents=transcript_canonical_documents(transcript),
        maximum_contexts_per_slice=10,
    )

    assert queue.eligible_contexts == 0
    assert queue.items == ()


def test_context_window_never_truncates_target_behind_a_long_previous_turn(tmp_path) -> None:
    documents = _document(tmp_path, "EOG", "Revenue was $10 million.")
    qa = next(
        document
        for document in documents
        if document.metadata.document_kind == "EARNINGS_CALL_QA"
    )
    long_operator = (
        "We will now begin the question-and-answer session. "
        + "context " * 500
        + "."
    )
    qa = type(qa)(
        metadata=qa.metadata,
        source=qa.source,
        text=qa.text.replace(
            "We will now begin the question-and-answer session.",
            long_operator,
        ),
        tables=qa.tables,
        inline_facts=qa.inline_facts,
        sentences=(),
    )

    queue = build_transcript_review_queue(
        documents=(qa,),
        maximum_contexts_per_slice=10,
        maximum_context_characters=500,
    )

    assert queue.selected_contexts == 1
    assert all("Revenue was $10 million." in item.text for item in queue.items)
    assert all(len(item.text) <= 500 for item in queue.items)
