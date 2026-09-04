from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v264 import V264_RULES, extract_text_kpis_v264


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body><p>{text}</p></body></html>".encode(),
                "test://v264-semantic-laws",
                "V264_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata(
            entity="TEST",
            source_kind="TEST",
            document_kind="TEXT_IE",
            available_at="2026-09-04",
            report_period="2025",
        ),
    )


def _frames(text: str):
    return extract_text_kpis_v264(_document(text)).extraction.frames


def test_v264_is_company_agnostic_typed_law_program() -> None:
    assert len(V264_RULES) == 22
    assert all(rule.pattern for rule in V264_RULES)
    assert all(rule.rule_id.startswith("v264.") for rule in V264_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V264_RULES)


def test_semantic_laws_normalize_naked_count_and_parenthesized_percent() -> None:
    orders = _frames("Commercial Airplanes booked 246 net orders including Korean Air.")
    assert any(frame.concept == "ORDERS" and frame.value == 246 for frame in orders)
    margin = _frames("Operating margin was (0.2) percent in the quarter.")
    assert any(
        frame.concept == "OPERATING_MARGIN" and frame.value == -0.2
        for frame in margin
    )


def test_compact_pair_and_respectively_use_labeled_roles() -> None:
    orders = _frames("Total orders of $16.5B, +17%.")
    matched_orders = tuple(
        frame
        for frame in orders
        if frame.concept == "ORDERS"
        and frame.value == 16_500_000_000
    )
    assert len(matched_orders) == 1
    assert any(
        frame.concept == "ORDERS"
        and frame.value == 16_500_000_000
        and frame.change == 17
        for frame in orders
    )
    capex = _frames(
        "We reiterate full-year guidance for cash provided by operations and "
        "capital expenditures of at least $19 billion and approximately "
        "$9 billion, respectively, for fiscal 2026."
    )
    assert any(
        frame.concept == "CAPEX_GUIDANCE" and frame.value == 9_000_000_000
        for frame in capex
    )


def test_multiple_laws_target_one_comparative_frame_schema() -> None:
    frames = _frames(
        "Operating margin was 34.9% versus 34.1% in the prior year, and "
        "comparable operating margin was 35.6% versus 34.7% in the prior year."
    )
    values = {
        (frame.concept, frame.value)
        for frame in frames
        if frame.frame.value == "COMPARATIVE"
    }
    assert values == {
        ("OPERATING_MARGIN", 34.9),
        ("PRIOR_YEAR_OPERATING_MARGIN", 34.1),
        ("OPERATING_MARGIN", 35.6),
        ("PRIOR_YEAR_OPERATING_MARGIN", 34.7),
    }


def test_dependency_ownership_rejects_sales_cost_as_revenue() -> None:
    frames = _frames(
        "Selling, general, administrative and other costs increased $68 million, "
        "to $344 million from $276 million, primarily due to higher sales and "
        "marketing costs."
    )
    assert not any(frame.concept == "REVENUE" for frame in frames)


def test_more_specific_change_frame_supersedes_absolute_level() -> None:
    frames = _frames("Total debt was reduced by a record $8.4 billion in the quarter.")
    debt = tuple(frame for frame in frames if frame.concept == "DEBT")
    assert len(debt) == 1
    assert debt[0].frame.value == "CHANGE_BY"
    assert debt[0].value == 8_400_000_000
    assert not debt[0].polarity.positive
