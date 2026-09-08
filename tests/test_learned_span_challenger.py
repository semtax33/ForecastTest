from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.learned import (
    LearnedSpanProposal,
    LearnedSpanUnavailableError,
    challenge_v292_span_candidates,
)
from equity_platform.text_ie.llm import EncoderSourceSlice
from equity_platform.text_ie.v24 import CandidateOrigin
from equity_platform.text_ie.v292 import extract_text_kpis_v292


def _doc(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<p>{text}</p>".encode(),
                "test://learned-span",
                "LEARNED-SPAN",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata(
            "TEST",
            "SEC",
            "10-Q",
            "2026-09-08",
            "2026Q2",
        ),
    )


class _Backend:
    name = "TEST_SPAN_CHALLENGER"
    device = "cuda"

    def __init__(self, proposals=()) -> None:
        self.proposals = tuple(proposals)

    def propose(self, block, source_slice):
        return tuple(
            proposal(block) if callable(proposal) else proposal
            for proposal in self.proposals
        )


class _UnavailableBackend:
    name = "OFFLINE_SPAN_CHALLENGER"
    device = "cuda:pending"

    def propose(self, block, source_slice):
        raise LearnedSpanUnavailableError("checkpoint is not available locally")


def _proposal(block, literal: str, *, canonical_concept=None, source_sha256=None):
    start = block.text.index(literal)
    return LearnedSpanProposal(
        source_sha256=source_sha256 or block.source.sha256,
        block_char_start=block.char_start,
        block_char_end=block.char_end,
        char_start=start,
        char_end=start + len(literal),
        raw_text=literal,
        raw_label="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        confidence=0.97,
        model_id="AAU-NLP/BERT-SL1000",
        model_revision="main",
        canonical_concept=canonical_concept,
    )


def test_learned_span_proposal_is_an_immutable_candidate_without_authority() -> None:
    proposal = LearnedSpanProposal(
        source_sha256="a" * 64,
        block_char_start=0,
        block_char_end=20,
        char_start=0,
        char_end=7,
        raw_text="Revenue",
        raw_label="revenue",
        confidence=0.99,
        model_id="test/model",
        model_revision="abc123",
    )

    assert not hasattr(proposal, "authority")
    assert not hasattr(proposal, "fact")
    with pytest.raises(FrozenInstanceError):
        proposal.confidence = 1.0


def test_learned_span_adds_only_candidate_graph_nodes_and_preserves_v292_output() -> None:
    document = _doc("HBM3E revenue mix reached 18% during the quarter.")
    baseline = extract_text_kpis_v292(document)
    backend = _Backend((lambda block: _proposal(block, "HBM3E revenue mix"),))

    result = challenge_v292_span_candidates(
        document,
        backend=backend,
        source_slice=EncoderSourceSlice.SEC_10Q,
    )

    learned = tuple(
        candidate
        for candidate in result.candidates
        if CandidateOrigin.LEARNED_SPAN in candidate.origins
    )
    assert len(learned) == 1
    assert learned[0].metric.alias == "HBM3E revenue mix"
    assert learned[0].metric.concept == "UNRESOLVED_KPI"
    assert [quantity.value for quantity in learned[0].quantities] == [18.0]
    assert result.extraction == baseline.extraction
    assert result.research_facts == ()
    assert result.status == "CANDIDATE_GRAPH_AUGMENTED"


def test_exact_overlap_merges_provenance_instead_of_duplicating_candidate() -> None:
    document = _doc("Revenue was $10 million during the quarter.")
    baseline = extract_text_kpis_v292(document)
    revenue_candidates = tuple(
        candidate
        for candidate in baseline.candidates
        if candidate.metric.alias.casefold() == "revenue"
    )
    assert len(revenue_candidates) == 1
    backend = _Backend((
        lambda block: _proposal(block, "Revenue", canonical_concept="REVENUE"),
    ))

    result = challenge_v292_span_candidates(
        document,
        backend=backend,
        source_slice=EncoderSourceSlice.SEC_10Q,
    )

    matching = tuple(
        candidate
        for candidate in result.candidates
        if candidate.block.char_start == revenue_candidates[0].block.char_start
        and candidate.metric.char_start == revenue_candidates[0].metric.char_start
        and candidate.metric.char_end == revenue_candidates[0].metric.char_end
    )
    assert len(matching) == 1
    assert CandidateOrigin.LEARNED_SPAN in matching[0].origins
    assert result.added_candidate_count == 0
    assert result.merged_candidate_count == 1


def test_source_hash_or_literal_mismatch_is_rejected_fail_closed() -> None:
    document = _doc("Revenue was $10 million during the quarter.")
    backend = _Backend((
        lambda block: _proposal(block, "Revenue", source_sha256="b" * 64),
        lambda block: LearnedSpanProposal(
            source_sha256=block.source.sha256,
            block_char_start=block.char_start,
            block_char_end=block.char_end,
            char_start=0,
            char_end=7,
            raw_text="NotThis",
            raw_label="revenue",
            confidence=0.99,
            model_id="test/model",
            model_revision="main",
        ),
    ))

    result = challenge_v292_span_candidates(
        document,
        backend=backend,
        source_slice=EncoderSourceSlice.SEC_10Q,
    )

    assert result.added_candidate_count == 0
    assert {item.reason for item in result.rejections} == {
        "SOURCE_HASH_MISMATCH",
        "SOURCE_LITERAL_MISMATCH",
    }
    assert result.status == "PROPOSALS_REJECTED"
    assert result.research_facts == ()


def test_unavailable_learned_backend_leaves_v292_byte_semantics_unchanged() -> None:
    document = _doc("Revenue was $10 million during the quarter.")
    baseline = extract_text_kpis_v292(document)

    result = challenge_v292_span_candidates(
        document,
        backend=_UnavailableBackend(),
        source_slice=EncoderSourceSlice.SEC_10Q,
    )

    assert result.status == "CHALLENGER_UNAVAILABLE"
    assert result.diagnostic == "checkpoint is not available locally"
    assert result.candidates == baseline.candidates
    assert result.extraction == baseline.extraction
    assert result.research_facts == ()


def test_repeated_local_span_is_attached_to_the_exact_source_block() -> None:
    document = _doc("Revenue rose 10%. Revenue fell 5%.")

    class _SecondBlockBackend:
        name = "SECOND_BLOCK"
        device = "cuda"

        def propose(self, block, source_slice):
            if "fell" not in block.text:
                return ()
            return (_proposal(block, "Revenue", canonical_concept="REVENUE"),)

    result = challenge_v292_span_candidates(
        document,
        backend=_SecondBlockBackend(),
        source_slice=EncoderSourceSlice.SEC_10Q,
    )

    learned = tuple(
        candidate
        for candidate in result.candidates
        if CandidateOrigin.LEARNED_SPAN in candidate.origins
    )
    assert len(learned) == 1
    assert "fell" in learned[0].block.text
