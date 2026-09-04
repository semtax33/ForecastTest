from __future__ import annotations

from hashlib import sha256

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie import SemanticFrame
from equity_platform.text_ie.v24 import (
    LLMRoleProposal,
    extract_text_kpis_v24,
)


def _document(text: str):
    html = f"<html><body><p>{text}</p></body></html>".encode()
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                content=html,
                source_uri="dev://v24",
                source_description="V24_DEV",
                expected_sha256=sha256(html).hexdigest(),
            ),
        ),
        metadata=DocumentMetadata(
            entity="DEV",
            source_kind="DEV",
            document_kind="EARNINGS_RELEASE",
            available_at="2026-09-04",
            report_period="2026Q2",
        ),
    )


def _frames(text: str) -> set[tuple[str, str, float | None]]:
    result = extract_text_kpis_v24(_document(text)).extraction
    return {(frame.concept, frame.frame.value, frame.value) for frame in result.frames}


def test_v24_recovers_level_and_change_from_one_clause() -> None:
    frames = _frames(
        "Operating margin of 10.4% was a 40-basis-point expansion from the prior year."
    )
    assert ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 10.4) in frames
    assert ("OPERATING_MARGIN_CHANGE", "CHANGE_BY", 40.0) in frames


def test_v24_binds_two_local_guidance_ranges_without_cross_assignment() -> None:
    frames = _frames(
        "The company now expects 2026 Adjusted EBITDA of $8.3 billion to $8.5 billion "
        "and growth capex between $7.3 billion and $7.9 billion."
    )
    assert ("ADJUSTED_EBITDA_GUIDANCE", "RANGE_GUIDANCE", 8_400_000_000.0) in frames
    assert ("CAPEX_GUIDANCE", "RANGE_GUIDANCE", 7_600_000_000.0) in frames


def test_v24_recovers_lower_bound_orders_and_value_before_capex() -> None:
    order_frames = _frames("Data center orders reached more than $5 billion year-to-date.")
    assert ("ORDERS", "ABSOLUTE_VALUE", 5_000_000_000.0) in order_frames
    capex_frames = _frames(
        "The company invested $13.0 billion in cash capital expenditures year-to-date."
    )
    assert ("CAPEX", "ABSOLUTE_VALUE", 13_000_000_000.0) in capex_frames


def test_v24_emits_cash_level_and_separate_change() -> None:
    frames = _frames(
        "We ended the quarter with a cash balance of $13.1 billion, up $4.3 billion in the year."
    )
    assert ("CASH", "ABSOLUTE_VALUE", 13_100_000_000.0) in frames
    assert ("CASH_CHANGE", "CHANGE_BY", 4_300_000_000.0) in frames


def test_v24_uses_local_causal_roles_when_block_has_extra_concepts() -> None:
    result = extract_text_kpis_v24(
        _document(
            "Alongside disciplined pricing, revenue growth was driven by increased volumes."
        )
    ).extraction
    frames = {(frame.concept, frame.frame.value) for frame in result.frames}
    assert ("REVENUE", "CAUSE_EFFECT") in frames
    assert ("ACTIVITY_VOLUME", "CAUSE_EFFECT") in frames
    assert len(result.relations) == 1
    assert result.relations[0].cause == "ACTIVITY_VOLUME"
    assert result.relations[0].effect == "REVENUE"


def test_v24_routes_flattened_cash_capex_table_before_text_ie() -> None:
    text = (
        "CASH CAPITAL EXPENDITURES 2Q26 1Q26 Dollars in millions YTD 2026 YTD 2025 "
        "Additions to property plant and equipment 12997 12181 6527 6470 "
        "Additional investments and advances 711 472 324 387 Other investing activities "
        "734 339 430 219 Total Cash Capital Expenditures 12974 12539 6787 6187"
    )
    result = extract_text_kpis_v24(_document(text))
    assert len(result.table_routes) == 1
    assert not result.extraction.frames
    assert any(
        item.rule_id == "v24.document.table_reconstruction"
        for item in result.extraction.abstentions
    )


class _GroundedBackend:
    def propose(self, block, candidates):
        candidate = next(item for item in candidates if item.metric.concept == "REVENUE")
        return (
            LLMRoleProposal(
                candidate_id=candidate.candidate_id,
                concept="REVENUE",
                frame=SemanticFrame.ABSOLUTE_VALUE,
                metric_literal=candidate.metric.alias,
                value_literal="$900 million",
                relation_literal="with",
            ),
        )


def test_v24_llm_rescue_is_proposal_only_and_deterministically_reverified() -> None:
    document = _document("Net sales finished with $900 million.")
    result = extract_text_kpis_v24(document, llm_backend=_GroundedBackend())
    rescued = [
        frame
        for frame in result.extraction.frames
        if frame.rule_id == "v24.llm_abstention_rescue"
    ]
    assert len(rescued) == 1
    assert rescued[0].verified_by == "LLM_PROPOSAL_PLUS_DETERMINISTIC_V24_VERIFIER"
    assert rescued[0].authority.name == "RESEARCH_DIAGNOSTIC"


class _HallucinatingBackend:
    def propose(self, block, candidates):
        candidate = next(item for item in candidates if item.metric.concept == "REVENUE")
        return (
            LLMRoleProposal(
                candidate_id=candidate.candidate_id,
                concept="REVENUE",
                frame=SemanticFrame.ABSOLUTE_VALUE,
                metric_literal=candidate.metric.alias,
                value_literal="$901 million",
                relation_literal="with",
            ),
        )


def test_v24_llm_rescue_cannot_invent_a_numeric_literal() -> None:
    result = extract_text_kpis_v24(
        _document("Net sales finished with $900 million."),
        llm_backend=_HallucinatingBackend(),
    )
    assert not any(
        frame.rule_id == "v24.llm_abstention_rescue"
        for frame in result.extraction.frames
    )
