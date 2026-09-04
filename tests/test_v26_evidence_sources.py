from __future__ import annotations

from equity_platform.text_ie.v26.evidence import (
    EvidenceChannel,
    industry_context,
    load_holdout_evidence_sources,
)


def test_holdout_has_hashed_10k_10q_and_ir_for_every_issuer() -> None:
    sources = load_holdout_evidence_sources()
    by_ticker = {}
    for source in sources:
        by_ticker.setdefault(source.ticker, set()).add(source.channel)
    assert len(by_ticker) == 10
    assert all(channels == {
        EvidenceChannel.SEC_10K,
        EvidenceChannel.SEC_10Q,
        EvidenceChannel.COMPANY_IR,
    } for channels in by_ticker.values())


def test_industry_statistics_are_context_only() -> None:
    for ticker in ("A", "AA", "AAL", "AAOI", "AAON", "AARD", "ABAT", "ABCB", "ABCL", "AACO"):
        context = industry_context(ticker)
        assert len(context) > 0
        assert context["authority_role"].eq("CONTEXT_ONLY_NOT_COMPANY_FACT").all()
        assert context["evidence_channel"].eq("INDUSTRY_STATISTIC").all()
