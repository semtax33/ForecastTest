from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v273 import (
    V273_RULES,
    extract_text_kpis_v273,
    route_document_blocks_v273,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body>{text}</body></html>".encode(),
                "test://v273-semantic-laws",
                "V273_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


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
        for frame in extract_text_kpis_v273(_document(f"<p>{text}</p>")).extraction.frames
    }


def test_v273_rules_are_spacy_dsl_and_issuer_neutral() -> None:
    assert V273_RULES
    assert all(rule.pattern and rule.rule_id.startswith("v273.") for rule in V273_RULES)
    assert all("issuer_callback" not in rule.operations for rule in V273_RULES)


def test_v273_parallel_income_and_value_growth_currency_ownership() -> None:
    income = _signatures(
        "GAAP operating income in the second quarter was $2.24 billion and "
        "non-GAAP operating income was $2.95 billion."
    )
    assert ("OPERATING_INCOME", "ABSOLUTE_VALUE", 2_240_000_000.0, None, None, None, True) in income
    assert ("OPERATING_INCOME", "ABSOLUTE_VALUE", 2_950_000_000.0, None, None, None, True) in income

    revenue = _signatures(
        "Subscription revenue was $1.85 billion, which represents 16% year-over-year "
        "growth, or 15% in constant currency."
    )
    assert ("REVENUE", "CHANGE_TO", 1_850_000_000.0, 16.0, None, None, True) in revenue
    assert ("REVENUE", "CHANGE_BY", 15.0, None, None, None, True) in revenue
    assert not any(frame == "ABSOLUTE_VALUE" and value == 1_850_000_000.0 for _, frame, value, *_ in revenue)


def test_v273_income_money_change_and_margin_comparatives() -> None:
    income = _signatures(
        "Operating income of $47 million increased $48 million year over year."
    )
    assert ("OPERATING_INCOME", "CHANGE_TO", 47_000_000.0, 48_000_000.0, None, None, True) in income

    increased = _signatures(
        "Adjusted gross margin increased to 53.4% from 51.1% a year ago and "
        "50.4% in the prior quarter."
    )
    assert ("GROSS_MARGIN", "COMPARATIVE", 53.4, None, None, None, True) in increased
    assert ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 51.1, None, None, None, True) in increased
    assert not any(value == 50.4 for _, _, value, *_ in increased)

    decreased = _signatures(
        "Adjusted gross margin of 75.1% decreased from 78.9%."
    )
    assert ("GROSS_MARGIN", "COMPARATIVE", 75.1, None, None, None, False) in decreased
    assert ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 78.9, None, None, None, False) in decreased


def test_v273_guidance_ranges_are_single_conditional_frames() -> None:
    revenue = _signatures(
        "2026 Revenue: We expect full-year 2026 revenue growth in a range of "
        "32% to 34%, an increase from 30% to 32% previously."
    )
    assert ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 33.0, None, 32.0, 34.0, True) in revenue
    assert not any(concept == "REVENUE_CHANGE_GUIDANCE" and frame == "ABSOLUTE_VALUE" for concept, frame, *_ in revenue)

    gross = _signatures("Non-GAAP gross margin in the range of 79.0% to 81.0%.")
    assert ("GROSS_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 80.0, None, 79.0, 81.0, True) in gross

    operating = _signatures("Operating margin of approximately 12.4% to 12.6%.")
    assert ("OPERATING_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 12.5, None, 12.4, 12.6, True) in operating


def test_v273_recurring_revenue_does_not_become_gaap_revenue() -> None:
    frames = _signatures(
        "Annual Recurring Revenue (ARR) grew 25% year-over-year to $5.84 billion."
    )
    assert not any(concept == "REVENUE" for concept, *_ in frames)


def test_v273_repeated_revenue_and_income_pairs_keep_local_ownership() -> None:
    revenue = _signatures(
        "Total Cloud Revenues $9.9 billion, up 47% USD, and up 46% constant currency; "
        "Cloud Infra Revenue $5.8 billion, up 93% USD, and up 92% constant currency; "
        "Cloud Apps Revenue $4.1 billion, up 10% USD, and up 9% constant currency."
    )
    for level, reported, constant_currency in (
        (9_900_000_000.0, 47.0, 46.0),
        (5_800_000_000.0, 93.0, 92.0),
        (4_100_000_000.0, 10.0, 9.0),
    ):
        assert ("REVENUE", "CHANGE_TO", level, reported, None, None, True) in revenue
        assert ("REVENUE", "CHANGE_BY", constant_currency, None, None, None, True) in revenue

    income = _signatures(
        "GAAP operating income was $20.6 billion, up 17%, and non-GAAP operating "
        "income rose to $28.9 billion, up 16%."
    )
    assert ("OPERATING_INCOME", "CHANGE_TO", 20_600_000_000.0, 17.0, None, None, True) in income
    assert ("OPERATING_INCOME", "CHANGE_TO", 28_900_000_000.0, 16.0, None, None, True) in income
    assert not any(value == 28_900_000_000.0 and change == 17.0 for _, _, value, change, *_ in income)


def test_v273_growth_guidance_from_to_and_bps_margin_clauses() -> None:
    guidance = _signatures("Total Revenues are expected to grow from 27% to 29% in USD.")
    assert ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 28.0, None, 27.0, 29.0, True) in guidance

    margins = _signatures(
        "GAAP operating margin contracted 171 basis points to 16.4%; "
        "non-GAAP operating margin contracted 248 basis points to 17.4%."
    )
    assert ("OPERATING_MARGIN", "CHANGE_TO", 16.4, 171.0, None, None, False) in margins
    assert ("OPERATING_MARGIN", "CHANGE_TO", 17.4, 248.0, None, None, False) in margins


def test_v273_operating_income_aliases_and_colon_levels_reach_candidates() -> None:
    aliases = _signatures(
        "Second quarter revenues of $112.0 billion; Earnings from Operations of $8.0 billion."
    )
    assert ("REVENUE", "ABSOLUTE_VALUE", 112_000_000_000.0, None, None, None, True) in aliases
    assert ("OPERATING_INCOME", "ABSOLUTE_VALUE", 8_000_000_000.0, None, None, None, True) in aliases

    reverse = _signatures(
        "Earnings from operations were $1.2 billion, representing a 5.1% operating margin."
    )
    assert ("OPERATING_INCOME", "ABSOLUTE_VALUE", 1_200_000_000.0, None, None, None, True) in reverse
    assert ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 5.1, None, None, None, True) in reverse

    colon = _signatures(
        "The guidance baseline uses Net sales: $177.8 billion, adjusted operating "
        "income1: $7.3 billion, and adjusted EPS1: $0.62."
    )
    assert ("REVENUE", "ABSOLUTE_VALUE", 177_800_000_000.0, None, None, None, True) in colon
    assert ("OPERATING_INCOME", "ABSOLUTE_VALUE", 7_300_000_000.0, None, None, None, True) in colon
    assert not any(concept == "REVENUE" and value == 0.62 for concept, _, value, *_ in colon)


def test_v273_revenue_composition_is_not_growth() -> None:
    frames = _signatures("Global eCommerce net sales grew 23%; representing 24% of total net sales.")
    assert ("REVENUE", "CHANGE_BY", 23.0, None, None, None, True) in frames
    assert ("REVENUE", "COMPOSITION", 24.0, None, None, None, True) in frames
    assert not any(frame == "CHANGE_BY" and value == 24.0 for _, frame, value, *_ in frames)


def test_v273_router_separates_repeated_prose_or_orphan_headers_from_grids() -> None:
    prose = _document(
        "<p>Total Cloud Revenues $9.9 billion, up 47% USD, and up 46% constant currency "
        "o Cloud Infra Revenue $5.8 billion, up 93% USD, and up 92% constant currency "
        "o Cloud Apps Revenue $4.1 billion, up 10% USD, and up 9% constant currency.</p>"
        "<p>GAAP operating margin contracted 171 basis points to 16.4%; non-GAAP "
        "operating margin contracted 248 basis points to 17.4%.</p>"
        "<p>June 30, 2025 Mar 31, 2026 June 30, 2026 Revenues June 30, 2025 "
        "Mar 31, 2026 June 30, 2026 Earnings from Operations UnitedHealthcare.</p>"
    )
    assert all(
        route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in route_document_blocks_v273(prose)
    )

    grids = _document(
        "<p>$28,585 $28,596 12 UNITEDHEALTH GROUP REVENUES BY BUSINESS - SUPPLEMENTAL "
        "FINANCIAL INFORMATION (in millions; unaudited) UnitedHealthcare Optum Health "
        "Three Months Ended June 30, 2026 Total revenues.</p>"
        "<p>Consolidated metric Original from 2.19.2026 As of 5.21.2026 As of 8.20.2026 "
        "Net sales (cc) Increase 3.5% to 4.5% Unchanged Increase 4.0% to 5.0% "
        "Adj. operating income (cc) Increase 6.0% to 8.0% Unchanged Increase 7.0% to 8.5%.</p>"
    )
    assert all(
        route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in route_document_blocks_v273(grids)
    )
