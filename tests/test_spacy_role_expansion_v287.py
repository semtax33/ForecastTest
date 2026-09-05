from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v287 import extract_text_kpis_v287, route_document_blocks_v287


def _doc(text: str):
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "test://v287", "V287", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    result = extract_text_kpis_v287(_doc(text))
    frames = {
        (f.concept, f.frame.value, f.value, f.change, f.lower_value, f.upper_value, f.polarity.positive)
        for f in result.extraction.frames
    }
    return frames, {candidate.metric.concept for candidate in result.candidates}


def test_v287_respective_debt_and_adjusted_ebitda_pairs() -> None:
    debt, _ = _frames(
        "Total debt was $85.4 million and net debt was $29.8 million, compared to $85.5 million "
        "and $47.4 million, respectively."
    )
    assert debt == {
        ("DEBT", "COMPARATIVE", 85_400_000.0, None, None, None, True),
        ("DEBT", "COMPARATIVE", 29_800_000.0, None, None, None, True),
        ("PRIOR_YEAR_DEBT", "COMPARATIVE", 85_500_000.0, None, None, None, True),
        ("PRIOR_YEAR_DEBT", "COMPARATIVE", 47_400_000.0, None, None, None, True),
    }
    ebitda, _ = _frames(
        "The Company had EBITDA of $4.6 million and $19.2 million, respectively, and Adjusted EBITDA "
        "of $4.6 million and $19.3 million, respectively."
    )
    assert ebitda == {
        ("ADJUSTED_EBITDA", "COMPARATIVE", 4_600_000.0, None, None, None, True),
        ("PRIOR_YEAR_ADJUSTED_EBITDA", "COMPARATIVE", 19_300_000.0, None, None, None, True),
    }


def test_v287_fused_sales_headline_and_two_growth_comparators() -> None:
    headline, _ = _frames("First Quarter Sales Increased by 27% Year-over-Year to $259 Million Manchester, NH.")
    assert headline == {("REVENUE", "CHANGE_TO", 259_000_000.0, 27.0, None, None, True)}
    result, _ = _frames("Q2 total revenues were $1,056.2 million, up 1.5% sequentially and up 4.3% year-over-year.")
    assert result == {
        ("REVENUE", "CHANGE_TO", 1_056_200_000.0, 1.5, None, None, True),
        ("REVENUE", "CHANGE_BY", 4.3, None, None, None, True),
    }


def test_v287_growth_and_margin_change_guidance_roles() -> None:
    revenue, _ = _frames("We now expect revenue growth to be down 6% to 8% year-over-year.")
    assert revenue == {
        ("REVENUE_CHANGE_GUIDANCE", "RANGE_GUIDANCE", 7.0, None, 6.0, 8.0, False),
    }
    gross, _ = _frames("We expect 2026 non-GAAP Gross Margin to be up approximately 100 basis points over 2025.")
    assert gross == {
        ("GROSS_MARGIN_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 100.0, None, None, None, True),
    }
    volume, _ = _frames("We now expect Clear Aligner volume growth to be up approximately 6% year-over-year.")
    assert volume == {
        ("ACTIVITY_VOLUME_CHANGE_GUIDANCE", "ABSOLUTE_VALUE", 6.0, None, None, None, True),
    }


def test_v287_parallel_profitability_roles() -> None:
    operating, _ = _frames("Adjusted operating income of $87.1M, yielding an adjusted operating margin of 9.2 percent.")
    assert operating == {
        ("OPERATING_INCOME", "ABSOLUTE_VALUE", 87_100_000.0, None, None, None, True),
        ("OPERATING_MARGIN", "ABSOLUTE_VALUE", 9.2, None, None, None, True),
    }
    ebitda, _ = _frames("Adjusted EBITDA of $157.7M, yielding an adjusted EBITDA margin of 16.7 percent.")
    assert ebitda == {
        ("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 157_700_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 16.7, None, None, None, True),
    }


def test_v287_fused_healthcare_highlights_are_prose() -> None:
    text = (
        "Health plan membership at the end of the quarter was approximately 294,100, up 31.5% year-over-year "
        "Total revenue was $1,335.6 million, up 31.6% year-over-year Adjusted gross profit was $182.9 million, "
        "up 35.3% year-over-year, and income from operations was $42.1 million Adjusted gross profit excludes "
        "$7.9 million of depreciation and $131.0 million of administrative expenses."
    )
    routes = {route.route for route in route_document_blocks_v287(_doc(text)) if route.char_start is not None}
    assert routes.isdisjoint({BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED})
    frames, candidates = _frames(text)
    assert "ACTIVITY_VOLUME" in candidates
    assert frames == {
        ("ACTIVITY_VOLUME", "CHANGE_TO", 294_100.0, 31.5, None, None, True),
        ("REVENUE", "CHANGE_TO", 1_335_600_000.0, 31.6, None, None, True),
        ("OPERATING_INCOME", "ABSOLUTE_VALUE", 42_100_000.0, None, None, None, True),
    }


def test_v287_ebitda_growth_does_not_bind_net_income_comparator() -> None:
    text = (
        "Adjusted gross profit excludes $1.9 million. Adjusted EBITDA of $68.1 million represented an adjusted "
        "EBITDA margin of 5.1% and grew 48.4% year-over-year, while net income was $36.6 million, compared to "
        "$15.7 million the year prior."
    )
    frames, _ = _frames(text)
    assert frames == {
        ("ADJUSTED_EBITDA", "CHANGE_TO", 68_100_000.0, 48.4, None, None, True),
        ("ADJUSTED_EBITDA_MARGIN", "ABSOLUTE_VALUE", 5.1, None, None, None, True),
    }


def test_v287_ranges_quarter_revenue_and_two_share_counts() -> None:
    ebitda, _ = _frames("Adjusted EBITDA in the range of $55 million to $61 million Full Year.")
    assert ebitda == {
        ("ADJUSTED_EBITDA_GUIDANCE", "RANGE_GUIDANCE", 58_000_000.0, None, 55_000_000.0, 61_000_000.0, True),
    }
    revenue, _ = _frames("Royalty revenue for the quarter were $27.5 million.")
    assert revenue == {("REVENUE", "ABSOLUTE_VALUE", 27_500_000.0, None, None, None, True)}
    shares, _ = _frames(
        "Expected weighted average basic share count of approximately 169.1 million shares outstanding and a "
        "weighted average diluted share count of approximately 172.8 million shares outstanding."
    )
    assert shares == {
        ("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 169_100_000.0, None, None, None, True),
        ("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 172_800_000.0, None, None, None, True),
    }


def test_v287_revenue_range_and_gross_margin_comparison() -> None:
    revenue, _ = _frames("GAAP total revenue in the range of $132.7 million to $134.2 million Full Year outlook.")
    assert revenue == {
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 133_450_000.0, None, 132_700_000.0, 134_200_000.0, True),
    }
    margin, _ = _frames("Non-GAAP gross margin of 63.0%, compared to 65.1% in the year-ago quarter.")
    assert margin == {
        ("GROSS_MARGIN", "COMPARATIVE", 63.0, None, None, None, True),
        ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 65.1, None, None, None, True),
    }


def test_v287_activity_composition_and_monetary_change() -> None:
    originations, _ = _frames(
        "Consumer auto originations of $13.3 billion included $8.3 billion of used retail volume, or 63% of total "
        "originations, $4.2 billion of new retail volume, and $739 million of lease."
    )
    assert originations == {
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 13_300_000_000.0, None, None, None, True),
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 8_300_000_000.0, None, None, None, True),
        ("ACTIVITY_VOLUME", "COMPOSITION", 63.0, None, None, None, True),
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 4_200_000_000.0, None, None, None, True),
        ("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 739_000_000.0, None, None, None, True),
    }
    revenue, _ = _frames("Net financing revenue of $1.3 billion was up $22 million year over year.")
    assert revenue == {("REVENUE", "CHANGE_TO", 1_300_000_000.0, 22_000_000.0, None, None, True)}
    volume, _ = _frames("Record application volume supporting more than $13 billion in originations, up 21% year-over-year.")
    assert volume == {("ACTIVITY_VOLUME", "CHANGE_TO", 13_000_000_000.0, 21.0, None, None, True)}


def test_v287_guidance_revision_and_demand_event_anchor() -> None:
    guidance, _ = _frames(
        "SaaS and license revenue is now expected to be in the range of $754.0 million to $754.4 million, up "
        "$10.2 million from the midpoint of prior full-year revenue guidance."
    )
    assert guidance == {
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 754_200_000.0, None, 754_000_000.0, 754_400_000.0, True),
        ("REVENUE_GUIDANCE", "CHANGE_BY", 10_200_000.0, None, None, None, True),
    }
    events, candidates = _frames("Utilities dispatched 304 demand response events through the platform.")
    assert "ACTIVITY_VOLUME" in candidates
    assert events == {("ACTIVITY_VOLUME", "ABSOLUTE_VALUE", 304.0, None, None, None, True)}


def test_v287_dense_expectations_and_cash_flow_rows_route_to_table() -> None:
    expectations = (
        "Financial Expectations Previous Updated Total Revenues $1,730 – $1,840 $1,730 – $1,840 "
        "Net Sales $460 – $480 $460 – $480 R&D Expenses $445 – $485 $445 – $485."
    )
    cash_flow = (
        "Six Months Ended 2026 2025 Net cash used in operating activities $17,220 $(4,507) Purchases of property "
        "and equipment (772) (882) Capitalized software development costs (4,065) (3,208) Free cash flow $12,383 $(8,597)."
    )
    for text in (expectations, cash_flow):
        routes = {route.route for route in route_document_blocks_v287(_doc(text)) if route.char_start is not None}
        assert routes & {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
