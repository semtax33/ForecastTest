from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v271 import V271_RULES, extract_text_kpis_v271, route_document_blocks_v271


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body><p>{text}</p></body></html>".encode(),
                "test://v271-semantic-laws",
                "V271_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _signatures(text: str):
    return {
        (frame.concept, frame.frame.value, frame.value, frame.change, frame.lower_value, frame.upper_value)
        for frame in extract_text_kpis_v271(_document(text)).extraction.frames
    }


def test_v271_laws_are_spacy_dsl_and_issuer_neutral() -> None:
    assert len(V271_RULES) == 15
    assert all(rule.pattern and rule.rule_id.startswith("v271.") for rule in V271_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V271_RULES)


def test_v271_money_plus_minus_guidance() -> None:
    explicit = _signatures(
        "We are forecasting revenue of $4.3 billion, +/- $100 million."
    )
    assert (
        "REVENUE_GUIDANCE", "RANGE_GUIDANCE", 4_300_000_000.0, None,
        4_200_000_000.0, 4_400_000_000.0,
    ) in explicit
    contextual = _signatures(
        "Business Outlook (In millions) Total revenue $10,250 +/- $500."
    )
    assert (
        "REVENUE_GUIDANCE", "RANGE_GUIDANCE", 10_250_000_000.0, None,
        9_750_000_000.0, 10_750_000_000.0,
    ) in contextual


def test_v271_margin_compact_range_and_relative_guidance() -> None:
    assert (
        "OPERATING_MARGIN", "ABSOLUTE_VALUE", 45.5, None, None, None
    ) in _signatures("Non-GAAP operating margin: 45.5%.")
    assert (
        "OPERATING_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 44.25, None, 43.75, 44.75
    ) in _signatures("Non-GAAP operating margin: 43.75% - 44.75%.")
    assert (
        "GROSS_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 62.5, None, 61.5, 63.5
    ) in _signatures("Non-GAAP gross margin is expected in a range of 62.5% +/- 1.0%.")


def test_v271_operating_income_and_implied_margin_ownership() -> None:
    frames = _signatures(
        "The company reported gross margin of 50.4 percent, record operating income "
        "of $3.10 billion or 34.0 percent of revenue, and record EPS of $3.50."
    )
    assert ("GROSS_MARGIN", "ABSOLUTE_VALUE", 50.4, None, None, None) in frames
    assert ("OPERATING_INCOME", "ABSOLUTE_VALUE", 3_100_000_000.0, None, None, None) in frames
    assert ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 34.0, None, None, None) in frames
    assert not any(concept == "REVENUE" and value == 3.5 for concept, _, value, *_ in frames)


def test_v271_change_to_ownership() -> None:
    percent = _signatures(
        "Health Benefits operating revenue was $42.7 billion, an increase of $1.1 "
        "billion, or 3 percent compared to the prior year quarter."
    )
    assert ("REVENUE", "CHANGE_TO", 42_700_000_000.0, 3.0, None, None) in percent
    money = _signatures(
        "Operating revenue was $49.8 billion, an increase of $0.4 billion compared to last year."
    )
    assert ("REVENUE", "CHANGE_TO", 49_800_000_000.0, 400_000_000.0, None, None) in money
    income = _signatures("Operating Income $665 million, a 35% increase over last year.")
    assert ("OPERATING_INCOME", "CHANGE_TO", 665_000_000.0, 35.0, None, None) in income


def test_v271_capex_between_range() -> None:
    frames = _signatures(
        "Total capital expenditures are expected to range between $5.000 and $6.000 billion."
    )
    assert (
        "CAPEX_GUIDANCE", "RANGE_GUIDANCE", 5_500_000_000.0, None,
        5_000_000_000.0, 6_000_000_000.0,
    ) in frames


def test_v271_growth_level_and_asset_flow() -> None:
    revenue = _signatures("Revenue growth of 21% to a record $7.1 billion.")
    assert ("REVENUE", "CHANGE_TO", 7_100_000_000.0, 21.0, None, None) in revenue
    assets = _signatures(
        "Core Net New Assets Grew 47% Year-Over-Year to $62.7 Billion."
    )
    assert (
        "ACTIVITY_VOLUME", "CHANGE_TO", 62_700_000_000.0, 47.0, None, None
    ) in assets


def test_v271_cash_total_and_false_cash_firewall() -> None:
    issuer_cash = _signatures(
        "Cash and investments at the parent company totaled approximately $2.1 billion."
    )
    assert ("CASH", "ABSOLUTE_VALUE", 2_100_000_000.0, None, None, None) in issuer_cash
    client_cash = _signatures(
        "Client transactional sweep cash balances ended June at $485.7 billion."
    )
    assert not any(concept == "CASH" for concept, *_ in client_cash)


def test_v271_router_recovers_bullet_and_narrative_prose() -> None:
    for text in (
        "S. net sales increased 52% to a new all-time high of $596 million •",
        "S. manufacturing, while returning capital to shareholders, reflected by the "
        "$3.0 billion deployed to dividends and capital expenditures. Business Highlights.",
    ):
        assert all(
            route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
            for route in route_document_blocks_v271(_document(text))
        )
