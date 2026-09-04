from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v261 import BlockRoute, extract_text_kpis_v261, route_document_blocks_v261


def _document(text: str):
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "memory://v261", "V261", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "IR", "EARNINGS_RELEASE", "2026-09-04", "2026Q3"),
    )


def _signatures(text: str):
    return {
        (frame.concept, frame.frame.value, round(float(frame.value or 0), 3), frame.change)
        for frame in extract_text_kpis_v261(_document(text)).extraction.frames
    }


def test_negated_debt_does_not_own_exception_payment() -> None:
    signatures = _signatures(
        "We do not have any long-term debt or lease obligations, other than to pay "
        "an affiliate $25,000 per month for administrative support."
    )
    assert not any(item[0] == "DEBT" for item in signatures)


def test_securities_sales_and_offering_price_are_not_operating_kpis() -> None:
    signatures = _signatures(
        "The Company entered into an ATM sales agreement to sell common shares, "
        "par value $0.001 per share, at a public offering price of $9.75 per share."
    )
    assert not any(item[0] in {"REVENUE", "PRICE_REALIZATION"} for item in signatures)


def test_parallel_metric_clause_keeps_revenue_deltas_before_while() -> None:
    signatures = _signatures(
        "Adjusted revenue increased $17.4 million, or 5.8%, while expenses "
        "increased $4.8 million, or 3.1%."
    )
    assert ("REVENUE", "CHANGE_BY", 17_400_000.0, None) in signatures
    assert ("REVENUE", "CHANGE_BY", 5.8, None) in signatures
    assert not any(item[0] == "REVENUE" and item[2] == 3.1 for item in signatures)


def test_bullet_comparisons_remain_text_and_preserve_two_comparators() -> None:
    text = (
        "Financial Summary · GAAP revenue was $191.9 million, compared with "
        "$103.0 million in 2025 and $151.1 million in Q1. · GAAP gross margin "
        "was 27.7%, compared with 30.3% in 2025 and 29.1% in Q1."
    )
    document = _document(text)
    assert any(route.route is BlockRoute.LIST_BULLET for route in route_document_blocks_v261(document))
    signatures = _signatures(text)
    assert len({item for item in signatures if item[1] == "COMPARATIVE"}) == 6


def test_prefix_value_bullet_recovers_level_and_relative_change() -> None:
    signatures = _signatures(
        "Financial Highlights: ● $8.2 million in Revenue, a 5.1% increase from "
        "the previous quarter ● $50.3 million cash, a 31% increase ● $0.0 million "
        "debt, Company currently holds zero debt."
    )
    assert ("REVENUE", "CHANGE_TO", 8_200_000.0, 5.1) in signatures
    assert ("CASH", "CHANGE_TO", 50_300_000.0, 31.0) in signatures
    assert ("DEBT", "ABSOLUTE_VALUE", 0.0, None) in signatures


def test_capex_aircraft_list_is_prose_and_value_before_metric_is_bound() -> None:
    text = (
        "Investing activities included $1.3 billion of capital expenditures, "
        "primarily for 11 aircraft, three engines and five spare parts."
    )
    document = _document(text)
    assert all(route.route is not BlockRoute.FLATTENED_TABLE for route in route_document_blocks_v261(document))
    assert ("CAPEX", "ABSOLUTE_VALUE", 1_300_000_000.0, None) in _signatures(text)


def test_absolute_money_change_and_unit_production_are_supported() -> None:
    assert ("REVENUE", "CHANGE_BY", 4_500_000.0, None) in _signatures(
        "Mortgage revenue decreased $4.5 million."
    )
    assert ("PRODUCTION", "ABSOLUTE_VALUE", 33_000.0, None) in _signatures(
        "Average annual production of 33,000 tons of lithium was assumed."
    )
