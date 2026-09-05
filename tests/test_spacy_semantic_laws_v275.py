from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v275 import (
    extract_text_kpis_v275,
    route_document_blocks_v275,
)


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body>{text}</body></html>".encode(),
                "test://v275-semantic-laws",
                "V275_SEMANTIC_LAW_TEST",
                numeric_rows_only=False,
            ),
        ),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    return extract_text_kpis_v275(_document(f"<p>{text}</p>")).extraction.frames


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


def test_v275_candidate_aliases_cover_bridge_anchors() -> None:
    result = extract_text_kpis_v275(
        _document(
            "<p>Operating loss for the segment was $13 million after a price/mix increase of 4%.</p>"
            "<p>Residential sales were 2.8 percent higher.</p>"
            "<p>Investment in property and equipment was $60.5 million.</p>"
            "<p>Our goal for device signings is between 27,000 and 29,000 units.</p>"
        )
    )
    concepts = {candidate.metric.concept for candidate in result.candidates}
    assert {
        "OPERATING_INCOME",
        "PRICE_REALIZATION",
        "ACTIVITY_VOLUME",
        "CAPEX",
    }.issubset(concepts)


def test_v275_routes_compact_grids_and_long_risk_prose() -> None:
    document = _document(
        "<p>EBIT ($B) 2.1 2.5 0.4 3.2 6.0 2.8 Company Adj.</p>"
        "<p>Global Net Sales $M YoY % Ex-FX % $735 +29% +29% $484 +41% +41% "
        "$425 (49%) (49%) $204 (71%) (71%).</p>"
        "<p>Risks include tariff policy; macroeconomic volatility; geopolitical "
        "conflicts; trade restrictions; changes in tax laws; supply chain disruption; "
        "vendor compliance; technology failures; litigation; and climate change.</p>"
    )
    routes = route_document_blocks_v275(document)
    assert routes[0].route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    assert routes[1].route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
    assert routes[2].route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}


def test_v275_routes_earnings_release_headline_as_prose() -> None:
    document = _document(
        "<p>Company provides fiscal year 2027 non-GAAP EPS guidance 2 of 13% to "
        "15% growth 3 ($12.40 to $12.60), above the Company's long-term EPS "
        "guidance. Today the company reported fourth quarter fiscal year 2026 "
        "revenues of $63.7 billion, an increase of 6% from the prior year.</p>"
    )
    assert route_document_blocks_v275(document)[0].route not in {
        BlockRoute.FLATTENED_TABLE,
        BlockRoute.MIXED,
    }


def test_v275_compact_product_sales_and_reported_revenue() -> None:
    product = _signatures("Abraxane: Q2 2026 WW Sales $55M - YoY% (47%), (47%) Ex-FX.")
    assert (
        "REVENUE",
        "CHANGE_TO",
        55_000_000.0,
        47.0,
        None,
        None,
        False,
    ) in product

    reported = _signatures(
        "The company today reported fourth quarter revenues of $63.7 billion, "
        "an increase of 6% from the prior year."
    )
    assert (
        "REVENUE",
        "CHANGE_TO",
        63_700_000_000.0,
        6.0,
        None,
        None,
        True,
    ) in reported


def test_v275_revenue_decomposition_and_local_polarity() -> None:
    frames = _signatures(
        "Reported net sales increased 3.6% to $2.9 billion reflecting a 0.5% "
        "increase from foreign exchange, a 4.6% decrease from M&A, and a 7.7% "
        "increase from the 53rd week."
    )
    assert ("REVENUE", "CHANGE_TO", 2_900_000_000.0, 3.6, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 0.5, None, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 4.6, None, None, None, False) in frames
    assert ("REVENUE", "CHANGE_BY", 7.7, None, None, None, True) in frames

    comparable = _signatures(
        "Comparable sales increased 1%, or decreased 2% on a constant dollar basis."
    )
    assert ("REVENUE", "CHANGE_BY", 2.0, None, None, None, False) in comparable
    assert not any(
        concept == "REVENUE" and frame == "CHANGE_BY" and value == 2.0 and positive
        for concept, frame, value, _, _, _, positive in comparable
    )


def test_v275_margin_and_income_ownership_is_clause_local() -> None:
    frames = _signatures(
        "Income from operations decreased 37% to $276.9 million and operating "
        "margin decreased 730 basis points to 11.2%."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_TO",
        276_900_000.0,
        37.0,
        None,
        None,
        False,
    ) in frames
    assert (
        "OPERATING_MARGIN",
        "CHANGE_TO",
        11.2,
        730.0,
        None,
        None,
        False,
    ) in frames
    assert not any(
        concept == "OPERATING_INCOME" and change in {730.0, 11.2}
        for concept, _, _, change, *_ in frames
    )

    gross = _signatures(
        "Gross margin decreased 99 basis points to 24.4%, and adjusted gross margin "
        "decreased 130 basis points to 24.5%. SG&A increased 20.4% to $401 million."
    )
    assert not any(
        concept == "GROSS_MARGIN" and value == 24.5 and change == 20.4
        for concept, _, value, change, *_ in gross
    )


def test_v275_ebit_loss_levels_and_money_changes() -> None:
    loss = _signatures(
        "Ford Model e reported an EBIT loss of $919 million on $1.0 billion of revenue."
    )
    assert ("EBIT", "ABSOLUTE_VALUE", 919_000_000.0, None, None, None, False) in loss
    assert ("REVENUE", "ABSOLUTE_VALUE", 1_000_000_000.0, None, None, None, True) in loss

    changed = _signatures(
        "Adjusted EBIT was $2.5 billion, an increase of $0.4 billion year-over-year."
    )
    assert (
        "EBIT",
        "CHANGE_TO",
        2_500_000_000.0,
        400_000_000.0,
        None,
        None,
        True,
    ) in changed
    assert not any(
        concept == "EBIT" and frame == "CHANGE_BY" and value == 400_000_000.0
        for concept, frame, value, *_ in changed
    )


def test_v275_volume_price_and_operating_loss_bridge_facts() -> None:
    frames = _signatures(
        "Organic net sales were driven by a price/mix increase of 4.0% and a volume "
        "decrease of 3.5%. Operating loss for the segment was $13 million."
    )
    assert ("PRICE_REALIZATION", "CHANGE_BY", 4.0, None, None, None, True) in frames
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 3.5, None, None, None, False) in frames
    assert (
        "OPERATING_INCOME",
        "ABSOLUTE_VALUE",
        13_000_000.0,
        None,
        None,
        None,
        False,
    ) in frames

    volume = _signatures(
        "The volume impact of the acquisition was 25% and 10% for two segments, respectively."
    )
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 25.0, None, None, None, True) in volume
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 10.0, None, None, None, True) in volume


def test_v275_utility_volume_phrasings() -> None:
    residential = _signatures("Residential sales were 2.8 percent higher.")
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 2.8, None, None, None, True) in residential

    industrial = _signatures(
        "The increase was due to a 9.9 percent increase in industrial volume."
    )
    assert ("ACTIVITY_VOLUME", "CHANGE_BY", 9.9, None, None, None, True) in industrial


def test_v275_guidance_ranges_and_revenue_secondary_change() -> None:
    revenue = _signatures(
        "Revenue increased 4% to $2.5 billion, or increased 2% on a constant dollar basis."
    )
    assert ("REVENUE", "CHANGE_TO", 2_500_000_000.0, 4.0, None, None, True) in revenue
    assert ("REVENUE", "CHANGE_BY", 2.0, None, None, None, True) in revenue

    guidance = _signatures(
        "The Company expects net revenue in the range of $11.000 billion to $11.150 "
        "billion, representing a decline of 1% to 0%."
    )
    assert (
        "REVENUE_CHANGE_GUIDANCE",
        "RANGE_GUIDANCE",
        0.5,
        None,
        0.0,
        1.0,
        False,
    ) in guidance


def test_v275_parent_scale_normalizes_bare_dollar_values() -> None:
    document = _document(
        "<p>Except for per-share information, amounts are stated in millions.</p>"
        "<h2>Quarterly Results</h2>"
        "<p>Net sales increased $306.6, or 14.7%, compared to last year.</p>"
        "<p>Investment in property and equipment was $60.5, a decrease from $64.3.</p>"
    )
    signatures = {
        (
            frame.concept,
            frame.frame.value,
            frame.value,
            frame.change,
            frame.lower_value,
            frame.upper_value,
        )
        for frame in extract_text_kpis_v275(document).extraction.frames
    }
    assert ("REVENUE", "CHANGE_BY", 306_600_000.0, None, None, None) in signatures
    assert ("REVENUE", "CHANGE_BY", 14.7, None, None, None) in signatures
    assert ("CAPEX", "COMPARATIVE", 60_500_000.0, None, None, None) in signatures
    assert ("PRIOR_YEAR_CAPEX", "COMPARATIVE", 64_300_000.0, None, None, None) in signatures
    assert not any(concept == "REVENUE" and value in {64.3, 3.1} for concept, _, value, *_ in signatures)


def test_v275_activity_goal_range_is_guidance() -> None:
    frames = _signatures(
        "Our goal for weighted device signings in 2026 is between 27,000 and 29,000 units."
    )
    assert (
        "ACTIVITY_VOLUME_GUIDANCE",
        "RANGE_GUIDANCE",
        28_000.0,
        None,
        27_000.0,
        29_000.0,
        True,
    ) in frames


def test_v275_disclosed_bullet_decomposition_binds_every_revenue_component() -> None:
    frames = _signatures(
        "Net sales for the Grocery & Snacks segment increased 0.3% to $1.2 billion "
        "in the quarter, reflecting: an 8.0% decrease from the impact of M&A, a "
        "7.8% increase from the impact of the 53rd week, and a 0.5% increase in "
        "organic net sales. The increase in organic net sales was driven by a "
        "price/mix increase of 4.0% and a volume decrease of 3.5%."
    )
    assert ("REVENUE", "CHANGE_TO", 1_200_000_000.0, 0.3, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 8.0, None, None, None, False) in frames
    assert ("REVENUE", "CHANGE_BY", 7.8, None, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 0.5, None, None, None, True) in frames
    assert {
        value
        for concept, frame, value, *_ in frames
        if concept == "REVENUE" and frame == "CHANGE_BY"
    } == {8.0, 7.8, 0.5}


def test_v275_disclosed_long_form_ebit_keeps_level_and_change_together() -> None:
    frames = _signatures(
        "Adjusted earnings before interest and taxes (EBIT) was $2.5 billion, "
        "an increase of $0.4 billion year-over-year."
    )
    assert (
        "EBIT",
        "CHANGE_TO",
        2_500_000_000.0,
        400_000_000.0,
        None,
        None,
        True,
    ) in frames
    assert not any(
        concept == "EBIT" and frame == "CHANGE_BY" and value == 400_000_000.0
        for concept, frame, value, *_ in frames
    )


def test_v275_disclosed_capex_parentheticals_do_not_become_revenue() -> None:
    document = _document(
        "<p>Except for per-share information, amounts are stated in millions.</p>"
        "<p>During the second quarter, our investment in property and equipment, "
        "net of proceeds from sales, was $60.5 (2.5% of net sales) which was a "
        "slight decrease from $64.3 (3.1% of net sales) in the prior-year quarter.</p>"
    )
    frames = extract_text_kpis_v275(document).extraction.frames
    signatures = {
        (frame.concept, frame.frame.value, frame.value) for frame in frames
    }
    assert ("CAPEX", "COMPARATIVE", 60_500_000.0) in signatures
    assert ("PRIOR_YEAR_CAPEX", "COMPARATIVE", 64_300_000.0) in signatures
    assert not any(
        concept == "REVENUE" and value in {64.3, 3.1}
        for concept, _, value in signatures
    )


def test_v275_disclosed_activity_goal_uses_current_not_parenthetical_prior_range() -> None:
    frames = _signatures(
        "Our goal for weighted FASTBin and FASTVend device signings in 2026 is "
        "between 27,000 and 29,000 MEUs (our previous goal was between 28,000 "
        "and 30,000 MEUs)."
    )
    assert (
        "ACTIVITY_VOLUME_GUIDANCE",
        "RANGE_GUIDANCE",
        28_000.0,
        None,
        27_000.0,
        29_000.0,
        True,
    ) in frames


def test_v275_disclosed_mix_impact_emits_base_revenue_concept() -> None:
    frames = _signatures(
        "The impact from acquisition and divestiture mix was 1% for both Health "
        "and Wellness and Total Company."
    )
    assert ("REVENUE", "CHANGE_BY", 1.0, None, None, None, True) in frames
    assert not any(concept == "REVENUE_CHANGE" for concept, *_ in frames)


def test_v275_disclosed_table_routes_resist_prose_override() -> None:
    document = _document(
        "<p>Growth reflects strong demand. Q2 Results Global Net Sales $M YoY % "
        "Ex-FX % $735 +29% +29% $484 +41% +41% $425 (49%) (49%) $204 "
        "(71%) (71%) Q2 product summary.</p>"
        "<p>Condensed Consolidated Statements (In millions) Net sales 3,133 "
        "2,765 13% Gross margin 52.0% 51.3% Operating earnings 809 692 "
        "Balance Sheets Cash 710 1,165 Accounts receivable 2,160 2,200 "
        "Statements of Cash Flows Net cash 469 272 Capital expenditures 55 48 "
        "Free cash flow 414 224.</p>"
    )
    routes = route_document_blocks_v275(document)
    assert all(
        route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in routes
        if any(character.isdigit() for character in route.text)
    )


def test_v275_revenue_acquisition_and_fx_amounts() -> None:
    frames = _signatures(
        "Revenue from acquisitions was $243 million and foreign currency tailwinds "
        "were $35 million in the quarter."
    )
    assert ("REVENUE", "ABSOLUTE_VALUE", 243_000_000.0, None, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 35_000_000.0, None, None, None, True) in frames


def test_v275_diluted_share_outlook() -> None:
    frames = _signatures(
        "This outlook assumes approximately 168 million of fully diluted shares."
    )
    assert (
        "SHARES_GUIDANCE",
        "ABSOLUTE_VALUE",
        168_000_000.0,
        None,
        None,
        None,
        True,
    ) in frames
