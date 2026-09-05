from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v276 import extract_text_kpis_v276, route_document_blocks_v276


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body>{text}</body></html>".encode(),
                "test://v276-semantic-laws",
                "V276_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    return extract_text_kpis_v276(_document(f"<p>{text}</p>")).extraction.frames


def _signatures(text: str):
    return {
        (
            frame.concept,
            frame.frame.value,
            frame.value,
            frame.change,
            frame.lower_value,
            frame.upper_value,
            frame.polarity.positive,
        )
        for frame in _frames(text)
    }


def test_v276_candidate_aliases_cover_cross_industry_economics() -> None:
    result = extract_text_kpis_v276(
        _document(
            "<p>RevPAR increased 5 percent.</p>"
            "<p>Underwriting income was $686 million.</p>"
            "<p>Fee income increased 20 percent.</p>"
            "<p>Noninterest income increased 13.7 percent.</p>"
            "<p>We participated in 1,350 investment banking transactions.</p>"
        )
    )
    assert {
        "REVENUE",
        "OPERATING_INCOME",
        "ACTIVITY_VOLUME",
    }.issubset({candidate.metric.concept for candidate in result.candidates})


def test_v276_revpar_multi_region_changes() -> None:
    frames = _signatures(
        "U.S. and Canada RevPAR rose 5 percent. International RevPAR declined "
        "0.5 percent in the quarter."
    )
    assert ("REVENUE", "CHANGE_BY", 5.0, None, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 0.5, None, None, None, False) in frames

    regions = _signatures(
        "APEC RevPAR increased over 5 percent, while Greater China RevPAR "
        "increased over 3 percent."
    )
    assert ("REVENUE", "CHANGE_BY", 5.0, None, None, None, True) in regions
    assert ("REVENUE", "CHANGE_BY", 3.0, None, None, None, True) in regions


def test_v276_underwriting_income_level() -> None:
    frames = _signatures(
        "General Insurance underwriting income was $686 million, with a combined "
        "ratio of 89.0%."
    )
    assert (
        "OPERATING_INCOME",
        "ABSOLUTE_VALUE",
        686_000_000.0,
        None,
        None,
        None,
        True,
    ) in frames


def test_v276_fee_income_money_percent_and_component_changes() -> None:
    frames = _signatures(
        "Fee income increased $385 million, or 20%, driven by an increase in "
        "capital markets and advisory revenue of $256 million."
    )
    assert ("REVENUE", "CHANGE_BY", 385_000_000.0, None, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 20.0, None, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 256_000_000.0, None, None, None, True) in frames
    assert not any(
        concept == "REVENUE" and frame == "ABSOLUTE_VALUE" and value == 256_000_000.0
        for concept, frame, value, *_ in frames
    )


def test_v276_record_revenue_and_subcomponent_growth() -> None:
    frames = _signatures(
        "Record net revenue of $7,712 million, including year-over-year increases "
        "of 7.5% in net interest income and 13.2% in fee revenue."
    )
    assert ("REVENUE", "ABSOLUTE_VALUE", 7_712_000_000.0, None, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 7.5, None, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 13.2, None, None, None, True) in frames

    noninterest = _signatures("Noninterest income increased 13.7 percent.")
    assert ("REVENUE", "CHANGE_BY", 13.7, None, None, None, True) in noninterest


def test_v276_capex_level_owns_value_despite_sales_phrase() -> None:
    frames = _signatures(
        "Capital expenditures, net of proceeds from sales of plant and equipment, "
        "for fiscal year 2026 were $524 million."
    )
    assert ("CAPEX", "ABSOLUTE_VALUE", 524_000_000.0, None, None, None, True) in frames
    assert not any(
        concept == "REVENUE" and value == 524_000_000.0
        for concept, _, value, *_ in frames
    )


def test_v276_activity_transaction_count() -> None:
    frames = _signatures(
        "The business has participated in more than 1,350 investment banking "
        "transactions since 2015."
    )
    assert (
        "ACTIVITY_VOLUME",
        "ABSOLUTE_VALUE",
        1_350.0,
        None,
        None,
        None,
        True,
    ) in frames


def test_v276_production_does_not_take_a_later_deposit_change() -> None:
    frames = _signatures(
        "Average loans increased 6%, driven by strong new production and increased "
        "utilization. Average deposits decreased 2%, reflecting seasonal declines."
    )
    assert not any(
        concept == "PRODUCTION" and value == 2.0
        for concept, _, value, *_ in frames
    )


def test_v276_sparse_narratives_are_not_flattened_tables() -> None:
    document = _document(
        "<p>U.S. and Canada RevPAR rose 5 percent. International RevPAR declined "
        "0.5 percent in the quarter.</p>"
        "<p>Contacts: Media: Example Person (513) 762-1080; Investors: Example "
        "Person (513) 762-4969.</p>"
        "<p>The business has participated in more than 1,350 investment banking "
        "transactions since 2015.</p>"
        "<p>Fiscal year 2026 includes legal costs. In arriving at adjusted EBITDA, "
        "the company does not adjust interest income of $8 million and $8 million "
        "or stock compensation of $24 million and $19 million.</p>"
    )
    assert all(
        route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in route_document_blocks_v276(document)
    )
