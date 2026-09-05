from __future__ import annotations

import pytest

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v277 import extract_text_kpis_v277, route_document_blocks_v277


def _document(text: str):
    return adapt_html_fragments(
        fragments=(
            HtmlFragment(
                f"<html><body>{text}</body></html>".encode(),
                "test://v277-semantic-laws",
                "V277_SEMANTIC_LAW_TEST",
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
        for frame in extract_text_kpis_v277(_document(f"<p>{text}</p>")).extraction.frames
    }


def test_v277_consolidated_and_organic_revenue_growth() -> None:
    frames = _signatures(
        "Our combined Brokerage and Risk Management segments delivered revenue "
        "growth of 24%, including organic growth of 6%."
    )
    assert ("REVENUE", "CHANGE_BY", 24.0, None, None, None, True) in frames
    assert ("REVENUE", "CHANGE_BY", 6.0, None, None, None, True) in frames


def test_v277_operating_income_level_and_changes() -> None:
    segment = _signatures(
        "Nutrition segment operating profit was $172 million for the second quarter "
        "of 2026, representing a 51% increase compared to the prior year quarter."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_TO",
        172_000_000.0,
        51.0,
        None,
        None,
        True,
    ) in segment

    decline = _signatures(
        "Refined Products and Other subsegment operating profit was 3% lower "
        "compared to the prior year quarter."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_BY",
        3.0,
        None,
        None,
        None,
        False,
    ) in decline

    dual_delta = _signatures(
        "Second-quarter operating income was $254.7 million, an increase of "
        "$35.0 million or 15.9%."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_TO",
        254_700_000.0,
        35_000_000.0,
        None,
        None,
        True,
    ) in dual_delta
    assert (
        "OPERATING_INCOME",
        "CHANGE_BY",
        15.9,
        None,
        None,
        None,
        True,
    ) in dual_delta


def test_v277_footnote_between_operating_profit_and_copula() -> None:
    frames = _signatures(
        "Total second quarter segment operating profit 1 was $1.5 billion, an "
        "increase of 75% compared to the prior year quarter."
    )
    assert (
        "OPERATING_INCOME",
        "CHANGE_TO",
        1_500_000_000.0,
        75.0,
        None,
        None,
        True,
    ) in frames


def test_v277_routes_flattened_tables_and_dense_segment_guidance() -> None:
    insurance_table = _document(
        "<p>Dollars in millions) 2026 2025 % Change Gross premiums written $324 "
        "$323 0.3 Net premiums written 272 253 7.5 Net premiums earned 285 281 1.4 "
        "Underwriting income $220 $238 (7.6) Underwriting Ratios % Point Change "
        "Loss ratio 6.5% (1.2)% 7.7 Combined ratio 22.8% 15.2% 7.6</p>"
    )
    constant_currency_table = _document(
        "<p>(UNAUDITED) Constant Currency 2Q 2026 Percentage change in GAAP net "
        "income, including FX impact 26.9% Percentage change in Adjusted EBITDA, "
        "including FX impact 24.1% Excluding reportable catastrophes 18.2% FX "
        "impact 0.1% Excluding FX impact 18.1%</p>"
    )
    mixed_segment_table = _document(
        "<p>Net earned premiums, fees and other income totaled $3.32 billion, up "
        "9 percent. Global Lifestyle $ in millions Q2'26 Q2'25 Change 6M'26 "
        "6M'25 Change Adjusted EBITDA 244.4 201.4 21% 481.1 399.2 21% Net "
        "earned premiums 2,572.9 2,350.8 9% 5,123.9 4,657.4 10%</p>"
    )
    for document in (insurance_table, constant_currency_table, mixed_segment_table):
        assert any(
            route.route in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
            for route in route_document_blocks_v277(document)
        )

    guidance = _document(
        "<p>U.S. & Canada segment property revenue of $5,060 million to $5,120 "
        "million, Latin America property revenue of $1,790 million to $1,810 "
        "million, and Europe property revenue of $1,025 million to $1,055 "
        "million, reflecting midpoint growth rates of (3.0)%, 9.6% and 10.9%, "
        "respectively.</p>"
    )
    assert all(
        route.route not in {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
        for route in route_document_blocks_v277(guidance)
    )


def test_v277_local_clause_ownership_for_revenue_and_margin_components() -> None:
    organic = _signatures(
        "The International segment revenues were up 16.2% (down 1.2% on an "
        "organic basis)."
    )
    assert ("REVENUE", "CHANGE_BY", 16.2, None, None, None, True) in organic
    assert ("REVENUE", "CHANGE_BY", 1.2, None, None, None, False) in organic

    attribution = _signatures(
        "Reported revenue reflects a 14.3% net positive impact from acquisitions "
        "and divestitures, as well as a 3.1% tailwind from foreign currency."
    )
    assert ("REVENUE", "CHANGE_BY", 14.3, None, None, None, True) in attribution
    assert ("REVENUE", "CHANGE_BY", 3.1, None, None, None, True) in attribution

    margin = _signatures(
        "The gross margin of 38.2% increased 860 basis points to last year. "
        "o Merchandise margins improved 710 basis points, driven by a prior "
        "inventory writedown. o Buying, Occupancy and Warehousing expenses "
        "leveraged 150 basis points due to increased sales."
    )
    gross_margin_frames = {
        signature for signature in margin if signature[0] == "GROSS_MARGIN"
    }
    assert gross_margin_frames == {
        ("GROSS_MARGIN", "CHANGE_TO", 38.2, 860.0, None, None, True)
    }


def test_v277_prior_comparison_is_not_a_second_current_margin() -> None:
    frames = _signatures(
        "The adjusted operating margin in second-quarter 2026 was 24.2%, "
        "compared with 23.7%."
    )
    margin_frames = {frame for frame in frames if frame[0] == "OPERATING_MARGIN"}
    assert margin_frames == {
        ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 24.2, None, None, None, True)
    }


def test_v277_sales_growth_guidance_does_not_own_eps_or_buyback_values() -> None:
    frames = _signatures(
        "Updates full-year outlook to net sales growth of around 5%, net income per "
        "diluted share of $13.10 to $13.60, share repurchases increased to at least "
        "$500 million."
    )
    revenue_frames = {
        frame
        for frame in frames
        if frame[0].removesuffix("_GUIDANCE").removesuffix("_CHANGE") == "REVENUE"
    }
    assert revenue_frames == {
        (
            "REVENUE_CHANGE_GUIDANCE",
            "ABSOLUTE_VALUE",
            5.0,
            None,
            None,
            None,
            True,
        )
    }


def test_v277_parallel_segment_revenue_guidance_ranges_and_growths() -> None:
    frames = _signatures(
        "U.S. & Canada segment property revenue of $5,060 million to $5,120 "
        "million, Latin America property revenue of $1,790 million to $1,810 "
        "million, Africa & APAC property revenue of $1,620 million to $1,640 "
        "million, Europe property revenue of $1,025 million to $1,055 million and "
        "Data Centers segment property revenue of $1,200 million to $1,220 million, "
        "reflecting midpoint growth rates of (3.0)%, 9.6%, 14.6%, 10.9% and 14.9%, "
        "respectively."
    )
    ranges = {
        (5_090_000_000.0, 5_060_000_000.0, 5_120_000_000.0),
        (1_800_000_000.0, 1_790_000_000.0, 1_810_000_000.0),
        (1_630_000_000.0, 1_620_000_000.0, 1_640_000_000.0),
        (1_040_000_000.0, 1_025_000_000.0, 1_055_000_000.0),
        (1_210_000_000.0, 1_200_000_000.0, 1_220_000_000.0),
    }
    assert {
        (frame[2], frame[4], frame[5])
        for frame in frames
        if frame[0] == "REVENUE_GUIDANCE" and frame[1] == "RANGE_GUIDANCE"
    } == ranges
    growths = {
        (3.0, False),
        (9.6, True),
        (14.6, True),
        (10.9, True),
        (14.9, True),
    }
    assert {
        (frame[2], frame[6])
        for frame in frames
        if frame[0] == "REVENUE_GUIDANCE" and frame[1] == "CHANGE_BY"
    } == growths


def test_v277_reported_and_constant_currency_growth_share_reported_level() -> None:
    frames = _signatures(
        "Second quarter revenue grew 16 percent year over year as reported, 14 "
        "percent on a constant currency basis, to $2.05 billion."
    )
    revenue_frames = [frame for frame in frames if frame[0] == "REVENUE"]
    assert len(revenue_frames) == 2
    assert {frame[3] for frame in revenue_frames} == {16.0, 14.0}
    assert all(frame[1] == "CHANGE_TO" for frame in revenue_frames)
    assert all(frame[2] == pytest.approx(2_050_000_000.0) for frame in revenue_frames)
