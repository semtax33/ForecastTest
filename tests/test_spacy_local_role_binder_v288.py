from __future__ import annotations

from equity_platform.documents import DocumentMetadata, HtmlFragment, adapt_html_fragments
from equity_platform.text_ie.v26 import BlockRoute
from equity_platform.text_ie.v288 import extract_text_kpis_v288, route_document_blocks_v288


def _doc(text: str):
    return adapt_html_fragments(
        fragments=(HtmlFragment(f"<p>{text}</p>".encode(), "test://v288", "V288", numeric_rows_only=False),),
        metadata=DocumentMetadata("TEST", "TEST", "TEXT_IE", "2026-09-05", "2026Q2"),
    )


def _frames(text: str):
    result = extract_text_kpis_v288(_doc(text))
    return {
        (f.concept, f.frame.value, f.value, f.change, f.lower_value, f.upper_value, f.polarity.positive)
        for f in result.extraction.frames
    }, {candidate.metric.concept for candidate in result.candidates}


def test_v288_banking_revenue_and_promissory_debt_roles() -> None:
    component, _ = _frames("This was offset by a $1.4 million increase in net interest income and a $3.3 million decrease in tax expense.")
    assert component == {("REVENUE", "CHANGE_BY", 1_400_000.0, None, None, None, True)}
    revenue, _ = _frames("Net interest income increased $15.4 million, or 5.5%, to $297.8 million.")
    assert revenue == {("REVENUE", "CHANGE_TO", 297_800_000.0, 5.5, None, None, True)}
    debt, candidates = _frames("The Company had borrowed $134,056 under the promissory note which is still outstanding.")
    assert "DEBT" in candidates
    assert debt == {("DEBT", "ABSOLUTE_VALUE", 134_056.0, None, None, None, True)}


def test_v288_result_level_change_and_margin_comparison_grammar() -> None:
    revenue, _ = _frames("Revenue for the quarter was $100.4 million, up 16.9% from $85.9 million.")
    assert revenue == {("REVENUE", "CHANGE_TO", 100_400_000.0, 16.9, None, None, True)}
    margin, _ = _frames("Gross margin was 59.9%, compared with 62.0% for the same period.")
    assert margin == {
        ("GROSS_MARGIN", "COMPARATIVE", 59.9, None, None, None, True),
        ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 62.0, None, None, None, True),
    }
    improving, _ = _frames("Delivered GAAP gross margin of 27%, improving from 20% in the prior quarter.")
    assert improving == {
        ("GROSS_MARGIN", "COMPARATIVE", 27.0, None, None, None, True),
        ("PRIOR_YEAR_GROSS_MARGIN", "COMPARATIVE", 20.0, None, None, None, True),
    }


def test_v288_net_sales_growth_and_forward_ranges() -> None:
    growth, _ = _frames("Net sales increased approximately 90% year-over-year, driven by demand.")
    assert growth == {("REVENUE", "CHANGE_BY", 90.0, None, None, None, True)}
    margin, _ = _frames("Outlook: non-GAAP gross margin between 46.5% and 47.5%.")
    assert margin == {("GROSS_MARGIN_GUIDANCE", "RANGE_GUIDANCE", 47.0, None, 46.5, 47.5, True)}
    headline, _ = _frames("Record quarterly net sales increased 90% year-over-year. Expect third quarter net sales of $36.0 million to $37.0 million.")
    assert headline == {
        ("REVENUE", "CHANGE_BY", 90.0, None, None, None, True),
        ("REVENUE_GUIDANCE", "RANGE_GUIDANCE", 36_500_000.0, None, 36_000_000.0, 37_000_000.0, True),
    }


def test_v288_midpoint_growth_and_parallel_profitability() -> None:
    growth, _ = _frames("The midpoint of the revenue range represents year-over-year growth of 41% and a sequential increase of 13%.")
    assert growth == {
        ("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 41.0, None, None, None, True),
        ("REVENUE_CHANGE_GUIDANCE", "CHANGE_BY", 13.0, None, None, None, True),
    }
    profit, _ = _frames("Gross margin was 56%, operating income was $3.1 billion, and net income was $2.8 billion.")
    assert profit == {
        ("GROSS_MARGIN", "ABSOLUTE_VALUE", 56.0, None, None, None, True),
        ("OPERATING_INCOME", "ABSOLUTE_VALUE", 3_100_000_000.0, None, None, None, True),
    }


def test_v288_multiple_locally_owned_sales_and_arr_changes() -> None:
    sales, _ = _frames("Unit volumes contributed $6.9 million in sales. Annual net sales reached $175.0 million for the contract year.")
    assert sales == {
        ("REVENUE", "ABSOLUTE_VALUE", 6_900_000.0, None, None, None, True),
        ("REVENUE", "ABSOLUTE_VALUE", 175_000_000.0, None, None, None, True),
    }
    arr, _ = _frames("Annual Recurring Revenue was $410 million, an increase of 22% year-over-year and an increase of $75 million.")
    assert arr == {
        ("REVENUE", "CHANGE_TO", 410_000_000.0, 22.0, None, None, True),
        ("REVENUE", "CHANGE_BY", 75_000_000.0, None, None, None, True),
    }


def test_v288_share_comparison_and_current_share_count() -> None:
    comparison, _ = _frames("Based on 129.4 million basic shares, compared to 140.2 million diluted shares in the prior year.")
    assert comparison == {
        ("SHARES", "COMPARATIVE", 129_400_000.0, None, None, None, True),
        ("PRIOR_YEAR_SHARES", "COMPARATIVE", 140_200_000.0, None, None, None, True),
    }
    current, _ = _frames("The number of common stock shares outstanding was 12,679,045.")
    assert current == {("SHARES", "ABSOLUTE_VALUE", 12_679_045.0, None, None, None, True)}


def test_v288_point_guidance_and_parallel_targets() -> None:
    ebitda, _ = _frames("Adjusted EBITDA is expected to be at least $4.0 million.")
    assert ebitda == {("ADJUSTED_EBITDA_GUIDANCE", "ABSOLUTE_VALUE", 4_000_000.0, None, None, None, True)}
    targets, _ = _frames("Increasing revenue outlook to at least $140 million and positive Adjusted EBITDA of at least $4 million.")
    assert targets == {
        ("REVENUE_GUIDANCE", "ABSOLUTE_VALUE", 140_000_000.0, None, None, None, True),
        ("ADJUSTED_EBITDA_GUIDANCE", "ABSOLUTE_VALUE", 4_000_000.0, None, None, None, True),
    }
    level, _ = _frames("Quarterly revenue more than doubled year-over-year to $34.0 million.")
    assert level == {("REVENUE", "ABSOLUTE_VALUE", 34_000_000.0, None, None, None, True)}


def test_v288_capex_shares_cash_and_ebitda_local_ownership() -> None:
    outlook, _ = _frames("Capital expenditure is expected under $10.0 million and weighted average shares outstanding of 136.9 million for the full year.")
    assert outlook == {
        ("CAPEX_GUIDANCE", "ABSOLUTE_VALUE", 10_000_000.0, None, None, None, True),
        ("SHARES_GUIDANCE", "ABSOLUTE_VALUE", 136_900_000.0, None, None, None, True),
    }
    cash, _ = _frames("Total liquidity was $447.8 million, including cash and cash equivalents of $307.6 million and investments of $30.9 million.")
    assert cash == {("CASH", "ABSOLUTE_VALUE", 307_600_000.0, None, None, None, True)}
    ebitda, _ = _frames("Reports net loss of $12.3 million and Adjusted EBITDA of $25.6 million.")
    assert ebitda == {("ADJUSTED_EBITDA", "ABSOLUTE_VALUE", 25_600_000.0, None, None, None, True)}


def test_v288_release_headline_and_short_grids_route_correctly() -> None:
    headline = "Reports Financial Results - Net revenues of $183.9 million - net income of $30.3 million - Company to hold a conference call."
    routes = {route.route for route in route_document_blocks_v288(_doc(headline)) if route.char_start is not None}
    assert routes.isdisjoint({BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED})
    assert _frames(headline)[0] == {("REVENUE", "ABSOLUTE_VALUE", 183_900_000.0, None, None, None, True)}

    grids = (
        "Coal Sales Realization per ton Three months ended 2026 2025 Met segment $118.71 $124.39",
        "EBITDA Projects $380,903 $4,746 $17,500 Energy Assets $75,904 $2,751 $34,831 O&M $36,193 $8,299 $9,795 Total $515,464 $9,718 $62,809",
        "Second Quarter Financial Results in thousands Q2 2026 Q2 2025 Revenue Net Income Loss Adj.",
    )
    for grid in grids:
        routes = {route.route for route in route_document_blocks_v288(_doc(grid)) if route.char_start is not None}
        assert routes & {BlockRoute.FLATTENED_TABLE, BlockRoute.MIXED}
