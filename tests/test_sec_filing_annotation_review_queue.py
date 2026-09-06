from __future__ import annotations

from hashlib import sha256
import json

import pytest

from equity_platform.documents.sec_filing import (
    discover_sec_filing_sources,
    sec_filing_canonical_documents,
)
from equity_platform.text_ie.training import (
    AnnotationSourceSlice,
    build_filing_review_queue,
)


def _filing(tmp_path, *, ticker: str, form: str, text: str):
    path = tmp_path / form / ticker / f"2026-02-01_accession_{ticker.lower()}.htm"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = f"<html><body><h2>Results</h2><p>{text}</p></body></html>"
    path.write_text(payload, encoding="utf-8")
    digest = sha256(path.read_bytes()).hexdigest()
    metadata = {
        "accession_number": f"accession-{ticker}",
        "document_type": form,
        "filing_date": "2026-02-01",
        "form": form,
        "period_of_report": "2025-12-31",
        "provider": "edgartools",
        "retrieved_at": "2026-08-30T12:58:27+00:00",
        "sha256": digest,
        "source_url": f"https://www.sec.gov/{ticker}/{form}",
        "ticker": ticker,
    }
    path.with_name(path.name + ".metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    return path, digest


def test_sec_source_adapter_uses_filing_date_as_pit_availability(tmp_path) -> None:
    path, digest = _filing(
        tmp_path, ticker="CAT", form="10-K", text="Revenue was $10 million."
    )

    sources = discover_sec_filing_sources(root=tmp_path)
    documents = sec_filing_canonical_documents(sources)

    assert len(documents) == 1
    assert documents[0].metadata.available_at == "2026-02-01"
    assert documents[0].metadata.report_period == "2025-12-31"
    assert documents[0].source.sha256 == digest
    assert documents[0].source.local_path == path.as_posix()


def test_sec_source_adapter_fails_closed_on_identity_or_hash_mismatch(tmp_path) -> None:
    path, _ = _filing(
        tmp_path, ticker="CAT", form="10-K", text="Revenue was $10 million."
    )
    metadata_path = path.with_name(path.name + ".metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["ticker"] = "DE"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="ticker"):
        discover_sec_filing_sources(root=tmp_path)


def test_filing_queue_creates_unreviewed_10k_and_10q_candidate_graphs(tmp_path) -> None:
    _filing(tmp_path, ticker="CAT", form="10-K", text="Revenue was $10 million.")
    _filing(tmp_path, ticker="DE", form="10-Q", text="Operating margin was 12%.")
    documents = sec_filing_canonical_documents(
        discover_sec_filing_sources(root=tmp_path)
    )

    queue = build_filing_review_queue(
        documents=documents,
        maximum_contexts_per_slice=10,
    )

    assert queue.eligible_contexts == 2
    assert queue.selected_contexts == 2
    assert {item.source_slice for item in queue.items} == {
        AnnotationSourceSlice.SEC_10K,
        AnnotationSourceSlice.SEC_10Q,
    }
    assert all(item.proposal.binding_hint == "UNREVIEWED" for item in queue.items)
    assert all(item.proposal.role_hint is None for item in queue.items)
    assert all(item.quality_tier == "WEAK" for item in queue.items)
    assert all(item.adjudication_status == "PENDING" for item in queue.items)


def test_filing_queue_balances_entities_and_excludes_source_hashes(tmp_path) -> None:
    _, excluded = _filing(
        tmp_path,
        ticker="CAT",
        form="10-K",
        text="Revenue was $10 million. Revenue was $11 million.",
    )
    _filing(tmp_path, ticker="DE", form="10-K", text="Revenue was $9 million.")
    documents = sec_filing_canonical_documents(
        discover_sec_filing_sources(root=tmp_path)
    )

    queue = build_filing_review_queue(
        documents=documents,
        maximum_contexts_per_slice=1,
        excluded_source_hashes=frozenset({excluded}),
    )

    assert queue.selected_contexts == 1
    assert {item.entity for item in queue.items} == {"DE"}


def test_filing_queue_never_truncates_target_sentence(tmp_path) -> None:
    long_context = "context " * 300
    _filing(
        tmp_path,
        ticker="CAT",
        form="10-Q",
        text=f"{long_context}. Revenue was $10 million.",
    )
    documents = sec_filing_canonical_documents(
        discover_sec_filing_sources(root=tmp_path)
    )

    queue = build_filing_review_queue(
        documents=documents,
        maximum_contexts_per_slice=10,
        maximum_context_characters=256,
    )

    assert queue.selected_contexts == 1
    assert all("Revenue was $10 million." in item.text for item in queue.items)
    assert all(len(item.text) <= 256 for item in queue.items)


def test_filing_queue_excludes_an_oversized_target_instead_of_truncating_it(
    tmp_path,
) -> None:
    _filing(
        tmp_path,
        ticker="CAT",
        form="10-K",
        text="Revenue was $10 million and " + "context " * 100 + ".",
    )
    documents = sec_filing_canonical_documents(
        discover_sec_filing_sources(root=tmp_path)
    )

    queue = build_filing_review_queue(
        documents=documents,
        maximum_contexts_per_slice=10,
        maximum_context_characters=256,
    )

    assert queue.eligible_contexts == 0
    assert queue.items == ()


def test_filing_queue_excludes_dense_table_like_cross_products(tmp_path) -> None:
    dense = " ".join(
        f"Revenue was ${value} million."
        for value in range(1, 12)
    )
    _filing(tmp_path, ticker="CAT", form="10-Q", text=dense)
    documents = sec_filing_canonical_documents(
        discover_sec_filing_sources(root=tmp_path)
    )

    queue = build_filing_review_queue(
        documents=documents,
        maximum_contexts_per_slice=20,
        maximum_pair_proposals_per_context=8,
    )

    assert queue.excluded_dense_contexts > 0
    assert all(
        sum(
            item.candidate_id == candidate_id
            for item in queue.items
        ) <= 8
        for candidate_id in {item.candidate_id for item in queue.items}
    )
