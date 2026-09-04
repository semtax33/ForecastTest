from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v269 import (
    V269_RULES,
    extract_text_kpis_v269,
    route_document_blocks_v269,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body><p>{text}</p></body></html>".encode(),
                "test://v269-semantic-laws",
                "V269_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    return extract_text_kpis_v269(_document(text)).extraction.frames


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


def test_v269_laws_are_typed_and_issuer_neutral() -> None:
    assert len(V269_RULES) >= 20
    assert all(rule.pattern for rule in V269_RULES)
    assert all(rule.rule_id.startswith("v269.") for rule in V269_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V269_RULES)


def test_v269_money_guidance_and_margin_guidance() -> None:
    revenue = _signatures(
        "Total revenues in the range of $38.2 billion to $39.4 billion."
    )
    assert (
        "REVENUE_GUIDANCE",
        "RANGE_GUIDANCE",
        38_800_000_000.0,
        None,
        38_200_000_000.0,
        39_400_000_000.0,
        True,
    ) in revenue
    margins = _signatures(
        "Updates full year GAAP operating margin guidance to 20.1%, and maintains "
        "non-GAAP operating margin guidance of 34.3%."
    )
    assert {
        value
        for concept, frame, value, *_ in margins
        if concept == "OPERATING_MARGIN_GUIDANCE" and frame == "ABSOLUTE_VALUE"
    } == {20.1, 34.3}
    ratio = _signatures(
        "Third quarter non-GAAP operating income guidance of approximately 67 "
        "percent of projected revenue."
    )
    assert any(
        concept == "OPERATING_MARGIN_GUIDANCE" and value == 67.0
        for concept, _, value, *_ in ratio
    )


def test_v269_component_changes_preserve_ownership() -> None:
    signatures = _signatures(
        "Sales increased 19% year-over-year, driven by 15% higher net selling "
        "price and 2% volume growth."
    )
    assert ("REVENUE", "CHANGE_BY", 19.0, None, None, None, True) in signatures
    assert (
        "PRICE_REALIZATION",
        "CHANGE_BY",
        15.0,
        None,
        None,
        None,
        True,
    ) in signatures
    assert (
        "ACTIVITY_VOLUME",
        "CHANGE_BY",
        2.0,
        None,
        None,
        None,
        True,
    ) in signatures
    assert not any(
        concept == "REVENUE" and frame == "CHANGE_BY" and value in {15.0, 2.0}
        for concept, frame, value, *_ in signatures
    )


def test_v269_cash_debt_capex_and_volume_levels() -> None:
    balances = _signatures(
        "Cash and cash equivalents totaled $14.0 billion and debt outstanding "
        "totaled $57.3 billion as of June 30, 2026."
    )
    assert ("CASH", "ABSOLUTE_VALUE", 14_000_000_000.0, None, None, None, True) in balances
    assert ("DEBT", "ABSOLUTE_VALUE", 57_300_000_000.0, None, None, None, True) in balances
    had = _signatures("The company had $2.3 billion in cash and $3.4 billion of debt.")
    assert ("CASH", "ABSOLUTE_VALUE", 2_300_000_000.0, None, None, None, True) in had
    assert ("DEBT", "ABSOLUTE_VALUE", 3_400_000_000.0, None, None, None, True) in had
    capex = _signatures(
        "The company generated $10,493 million in cash from operations and spent "
        "$231 million on capital expenditures, resulting in $10,262 million of free cash flow."
    )
    assert ("CAPEX", "ABSOLUTE_VALUE", 231_000_000.0, None, None, None, True) in capex
    assert not any(concept == "CAPEX" and value == 10_262_000_000.0 for concept, _, value, *_ in capex)
    volume = _signatures(
        "Second-quarter average daily volume was the third highest quarterly ADV "
        "reaching 29.8 million contracts."
    )
    assert any(concept == "ACTIVITY_VOLUME" and value == 29_800_000.0 for concept, _, value, *_ in volume)


def test_v269_word_percent_and_secondary_growth_roles() -> None:
    asia = _signatures(
        "Asia sales of $886 million increased nine percent from the prior year on "
        "six percent higher volumes, two percent favorable currency, and one percent "
        "higher energy cost pass-through."
    )
    assert ("REVENUE", "CHANGE_TO", 886_000_000.0, 9.0, None, None, True) in asia
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 6.0, None, None, None, True) in asia
    cc = _signatures(
        "Subscription and support revenue of $10.8 billion, up 12% Y/Y and 11% in CC."
    )
    assert ("REVENUE", "CHANGE_TO", 10_800_000_000.0, 12.0, None, None, True) in cc
    assert ("REVENUE", "CHANGE_BY", 11.0, None, None, None, True) in cc


def test_v269_guidance_ranges_and_cross_metric_firewall() -> None:
    guidance = _signatures(
        "2026 guidance calls for revenue growth of 5.9% to 7.9%, and organic "
        "constant currency growth of 6.0% to 8.0%."
    )
    ranges = {
        (low, high)
        for concept, frame, _, _, low, high, _ in guidance
        if concept == "REVENUE_CHANGE_GUIDANCE" and frame == "RANGE_GUIDANCE"
    }
    assert ranges == {(5.9, 7.9), (6.0, 8.0)}
    profit = _signatures(
        "Adjusted operating profit increased 15% to $1.998 billion, and adjusted "
        "diluted EPS increased 23% to $4.83."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_TO",
        1_998_000_000.0,
        15.0,
        None,
        None,
        True,
    ) in profit
    assert not any(
        concept == "OPERATING_INCOME" and change == 23.0
        for concept, _, _, change, *_ in profit
    )


def test_v269_router_handles_grids_and_prose_notes() -> None:
    tables = (
        "Other $116 $77 51% Total Operating Expenses $6,540 $6,523 0% "
        "Operating Margin Operating income as % of product sales 36.8% 30.3% 6.5 pts.",
        "Quarterly Operating Statistics 2Q 2025 3Q 2025 4Q 2025 1Q 2026 2Q 2026 "
        "Quarterly Average Daily Volume Product Line Interest rates 15,472 13,378 "
        "13,010 18,674 14,532 Equity indexes 7,661 6,278 7,738 8,655 8,633",
        "$ (in millions) 2Q26 2Q25 % Chg Segment Revenues $557 $531 5% "
        "Recurring Revenues $406 $395 3% Transaction Revenues $151 $136 11% "
        "Operating expenses $1,298 $1,308 Capital expenditures $850 million",
    )
    for text in tables:
        assert any(
            route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
            for route in route_document_blocks_v269(_document(text))
        )
    prose = (
        "Product sales decreased 20% year-over-year to $153 million, driven by "
        "16% lower net selling price and lower volume."
    )
    assert all(route.route is BlockRoute.PROSE for route in route_document_blocks_v269(_document(prose)))
